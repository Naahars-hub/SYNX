import re
from typing import List, Dict, Optional, Any, Tuple
from app.extractor.entities import OCRTextBlock, ExtractedField, BoundingBox

class EntityParser:
    """
    Robust NLP & Heuristic Parser for Legal Metrology (Packaged Commodities) Rules, 2011.
    Tuned for both clean digital labels and real-world noisy smartphone packaging scans.
    """

    def __init__(self):
        # MRP & Price patterns
        self.re_mrp = re.compile(
            r'(?:m\.?r\.?p\.?|max(?:imum)?\s*retail\s*price|price)[\s:]*(?:rs\.?|re\.?|₹|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)',
            re.IGNORECASE
        )
        # Unit Sale Price: price followed by / or per (e.g. Rs.0.075/ml, Rs. 0.80 / g)
        self.re_usp = re.compile(
            r'(?:(?:u\.?s\.?p\.?|unit\s*(?:sale\s*)?price)[\s:]*)?(?:rs\.?|re\.?|₹|inr)\s*([0-9]+(?:\.[0-9]{1,4})?)\s*(?:per|/)\s*([a-zA-Z]*)',
            re.IGNORECASE
        )
        self.re_currency_val = re.compile(
            r'(?:rs\.?|re\.?|₹|inr)\s*([0-9]+(?:\.[0-9]{1,2})?)',
            re.IGNORECASE
        )
        self.re_incl_tax = re.compile(
            r'(?:incl(?:usive)?(?:\s+of)?\s*(?:all)?\s*taxes?|incl\.?\s*taxes?|all\s*taxes|inc[a-z\s]*tax|altxes)',
            re.IGNORECASE
        )

        # Net Quantity (explicitly avoiding nutrition table lines)
        self.re_net_qty_explicit = re.compile(
            r'(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|volume|vol\.?))[\s:]*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)',
            re.IGNORECASE
        )
        self.re_standalone_qty = re.compile(
            r'\b([0-9]+(?:\.[0-9]+)?)\s*(kg|kgs|g|gm|gms|ml|mls|l|ltr|ltrs|liter|liters|litre|litres|n|u)\b',
            re.IGNORECASE
        )

        # Dates & Manufacturing (DD/MM/YYYY, DD/MM/YY, MM/YYYY, MM/YY, Month Year)
        self.re_date_label = re.compile(
            r'(?:mfd\.?|mfg\.?|packed|pkd\.?|date\s*of\s*(?:mfg|packing|import)|manufacturing\s*date)[\s:]*([0-9]{1,2}[\/\.\-][0-9]{1,2}[\/\.\-][0-9]{2,4}|[0-9]{1,2}[\/\.\-][0-9]{2,4}|[a-zA-Z]{3,9}[\s\/\.\-][0-9]{2,4}|[0-9]{1,2}\s+[a-zA-Z]{3,9}\s+[0-9]{2,4})',
            re.IGNORECASE
        )
        self.re_date_any = re.compile(
            r'(?:^|[^0-9])(0[1-9]|[12][0-9]|3[01])[\/\.\-](0[1-9]|1[0-2])[\/\.\-]([0-9]{2,4})|(?:^|[^0-9])(0[1-9]|1[0-2])[\/\.\-]([0-9]{2,4})|\b([a-zA-Z]{3,9})\s*([0-9]{2,4})\b'
        )

        # Consumer Contacts
        self.re_email = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        self.re_website = re.compile(
            r'\b(?:www\.|w\.)?[a-zA-Z0-9\-]+(?:\.com|\.co\.in|\.in|\.org)\b',
            re.IGNORECASE
        )
        self.re_phone = re.compile(
            r'(?:(?:tel|phone|contact|toll\s*free|care|call\s*us|calus|call|helpline|queries|feedback)[\s:]*)?(\+?91[-\s]?[0-9]{10}|1800[-\s]?[0-9]{3}[-\s]?[0-9]{3,4}|180[0-9]{5,7}|0[0-9]{2,4}[-\s]?[0-9]{6,8}|[6-9][0-9]{9})',
            re.IGNORECASE
        )
        self.re_pincode = re.compile(r'\b[1-9][0-9]{5}\b')

        # Country & Best Before
        self.re_origin = re.compile(
            r'(?:country\s*of\s*origin|made\s*in|product\s*of|origin)[\s:]*([a-zA-Z\s]+)',
            re.IGNORECASE
        )
        self.re_best_before = re.compile(
            r'(?:best\s*before|use\s*by|expiry|exp\.?\s*date)[\s:]*([^\n\r,]+)',
            re.IGNORECASE
        )

        # Nutrition / Storage blacklists to prevent false entity matches
        self.nutrition_blacklist = {
            "sugars", "sugar", "fat", "saturated", "trans", "fiber", "fibre",
            "protein", "carbohydrate", "carbohydrates", "energy", "kcal", "kj",
            "sodium", "cholesterol", "nutritional", "nutrition", "per 100g",
            "per serve", "serving size", "servings per pack", "approx", "store in",
            "keep away", "dry place", "sunlight"
        }

    def parse(self, blocks: List[OCRTextBlock]) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}
        full_text_lines = [b.text for b in blocks]
        combined_text = " \n ".join(full_text_lines)

        # 1. Parse Net Quantity
        net_qty = self._extract_net_quantity(blocks, combined_text)
        if net_qty:
            fields["net_quantity"] = net_qty

        # 2. Parse MRP & USP
        mrp, usp = self._extract_mrp_and_usp(blocks, combined_text)
        if mrp:
            fields["mrp"] = mrp
        if usp:
            fields["unit_sale_price"] = usp

        # 3. Parse Mfg Date and Best Before
        mfg_date, best_before = self._extract_dates(blocks, combined_text)
        if mfg_date:
            fields["mfg_date"] = mfg_date
        if best_before:
            fields["best_before"] = best_before

        # 4. Parse Manufacturer / Packer Details
        mfr = self._extract_manufacturer(blocks, combined_text)
        if mfr:
            fields["manufacturer"] = mfr

        # 5. Parse Consumer Care
        care = self._extract_consumer_care(blocks, combined_text)
        if care:
            fields["consumer_care"] = care

        # 6. Parse Country of Origin
        origin = self._extract_country_of_origin(blocks, combined_text)
        if origin:
            fields["country_of_origin"] = origin

        # 7. Parse Common / Generic Commodity Name
        commodity = self._extract_commodity_name(blocks, combined_text)
        if commodity:
            fields["commodity_name"] = commodity

        return fields

    def _is_nutrition_or_storage_line(self, text: str) -> bool:
        t_low = text.lower()
        return any(k in t_low for k in self.nutrition_blacklist)

    def _extract_net_quantity(self, blocks: List[OCRTextBlock], combined_text: str) -> Optional[ExtractedField]:
        # 1. Look for explicit "Net Wt" / "Net Quantity" first
        for idx, b in enumerate(blocks):
            if "serving size" in b.text.lower() or "servings per" in b.text.lower():
                continue
            m = self.re_net_qty_explicit.search(b.text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).strip()
                return ExtractedField(
                    field_type="net_quantity",
                    label="Net Quantity",
                    raw_text=b.text,
                    parsed_value=val,
                    unit=unit,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )

        # 2. Standalone quantity, strictly filtering out nutritional table rows (Sugars (g), Fat (g), etc.)
        for idx, b in enumerate(blocks):
            if self._is_nutrition_or_storage_line(b.text) or "serving" in b.text.lower():
                continue

            m = self.re_standalone_qty.search(b.text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).strip()
                if val <= 0:
                    continue
                return ExtractedField(
                    field_type="net_quantity",
                    label="Net Quantity",
                    raw_text=b.text,
                    parsed_value=val,
                    unit=unit,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
        return None

    def _extract_mrp_and_usp(self, blocks: List[OCRTextBlock], combined_text: str) -> Tuple[Optional[ExtractedField], Optional[ExtractedField]]:
        mrp_field = None
        usp_field = None

        # 1. Find Unit Sale Price (USP)
        # Matches any price with slash or per (e.g. Rs.0.075/ml, Rs.0.075/, Rs. 0.80 / g)
        for idx, b in enumerate(blocks):
            if self._is_nutrition_or_storage_line(b.text):
                continue
            m = self.re_usp.search(b.text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).strip() or "ml"
                usp_field = ExtractedField(
                    field_type="unit_sale_price",
                    label="Unit Sale Price",
                    raw_text=b.text,
                    parsed_value={"amount": val, "unit": unit},
                    unit=unit,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
                break

        # 2. Find Maximum Retail Price (MRP)
        # Priority A: Explicit MRP keyword
        for idx, b in enumerate(blocks):
            if self._is_nutrition_or_storage_line(b.text):
                continue
            if "/" in b.text and usp_field and b.text == usp_field.raw_text:
                continue
            m = self.re_mrp.search(b.text)
            if m:
                val = float(m.group(1))
                has_tax = bool(self.re_incl_tax.search(b.text) or self.re_incl_tax.search(combined_text))
                mrp_field = ExtractedField(
                    field_type="mrp",
                    label="Maximum Retail Price (MRP)",
                    raw_text=b.text,
                    parsed_value={"amount": val, "inclusive_of_all_taxes": has_tax},
                    unit="INR",
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
                break

        # Priority B: Currency value that is NOT a USP per-unit rate (e.g. Rs. 30.00)
        if not mrp_field:
            for idx, b in enumerate(blocks):
                if self._is_nutrition_or_storage_line(b.text):
                    continue
                # Skip if this block is the USP block or has a slash indicating rate
                if usp_field and (b.text == usp_field.raw_text or "/" in b.text):
                    continue
                txt = b.text.lower()
                if any(k in txt for k in ["mrp", "price", "₹", "rs.", "rs ", "inr"]) or re.search(r'rs\.?\s*\d', txt):
                    m = self.re_currency_val.search(b.text)
                    if m:
                        val = float(m.group(1))
                        # Prefer normal package prices over tiny fractional rates
                        if "/" in b.text and val < 1.0:
                            continue
                        has_tax = bool(self.re_incl_tax.search(combined_text))
                        mrp_field = ExtractedField(
                            field_type="mrp",
                            label="Maximum Retail Price (MRP)",
                            raw_text=b.text,
                            parsed_value={"amount": val, "inclusive_of_all_taxes": has_tax},
                            unit="INR",
                            confidence=b.confidence,
                            bbox=b.bbox,
                            font_height_px=b.height_px,
                            font_height_mm=b.height_mm,
                            source_block_index=idx
                        )
                        break

        return mrp_field, usp_field

    def _extract_dates(self, blocks: List[OCRTextBlock], combined_text: str) -> Tuple[Optional[ExtractedField], Optional[ExtractedField]]:
        mfg_field = None
        bb_field = None

        # 1. Look for explicit "Mfg Date" / "Packed Date"
        for idx, b in enumerate(blocks):
            m = self.re_date_label.search(b.text)
            if m:
                date_str = m.group(1).strip()
                mfg_field = ExtractedField(
                    field_type="mfg_date",
                    label="Month & Year of Manufacture/Packing",
                    raw_text=b.text,
                    parsed_value=date_str,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
                break

        # 2. Look for explicit "Best Before" / "Expiry"
        for idx, b in enumerate(blocks):
            m = self.re_best_before.search(b.text)
            if m:
                bb_field = ExtractedField(
                    field_type="best_before",
                    label="Best Before / Expiry",
                    raw_text=b.text,
                    parsed_value=m.group(1).strip(),
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
                break

        # 3. Collect standalone dates (especially stamped on neck, shoulder or cap)
        standalone_dates = []
        for idx, b in enumerate(blocks):
            if self._is_nutrition_or_storage_line(b.text):
                continue
            for m in self.re_date_any.finditer(b.text):
                matched_text = m.group(0).strip()
                nums = re.findall(r'[0-9]+', matched_text)
                if len(nums) >= 2:
                    if len(nums) >= 3:
                        d, mo, yr = nums[:3]
                    else:
                        mo, yr = nums[:2]
                    # Normalize year (e.g. 26 -> 2026, 226 -> 2026)
                    yr_norm = f"20{yr}" if len(yr) == 2 else (f"20{yr[-2:]}" if len(yr) > 2 else yr)
                    try:
                        mo_val = int(mo)
                        if 1 <= mo_val <= 12:
                            d_str = f"{mo_val:02d}/{yr_norm}"
                            standalone_dates.append((d_str, b, idx))
                    except ValueError:
                        pass

        if standalone_dates:
            if not mfg_field and not bb_field:
                if len(standalone_dates) >= 2:
                    d1_str, b1, idx1 = standalone_dates[0]
                    d2_str, b2, idx2 = standalone_dates[1]
                    mfg_field = ExtractedField(
                        field_type="mfg_date",
                        label="Month & Year of Manufacture/Packing",
                        raw_text=b1.text,
                        parsed_value=d1_str,
                        confidence=b1.confidence,
                        bbox=b1.bbox,
                        font_height_px=b1.height_px,
                        font_height_mm=b1.height_mm,
                        source_block_index=idx1
                    )
                    bb_field = ExtractedField(
                        field_type="best_before",
                        label="Best Before / Expiry",
                        raw_text=b2.text,
                        parsed_value=d2_str,
                        confidence=b2.confidence,
                        bbox=b2.bbox,
                        font_height_px=b2.height_px,
                        font_height_mm=b2.height_mm,
                        source_block_index=idx2
                    )
                else:
                    d_str, b, idx = standalone_dates[0]
                    mfg_field = ExtractedField(
                        field_type="mfg_date",
                        label="Month & Year of Manufacture/Packing",
                        raw_text=b.text,
                        parsed_value=d_str,
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )
            elif not mfg_field and standalone_dates:
                d_str, b, idx = standalone_dates[0]
                mfg_field = ExtractedField(
                    field_type="mfg_date",
                    label="Month & Year of Manufacture/Packing",
                    raw_text=b.text,
                    parsed_value=d_str,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
            elif not bb_field and len(standalone_dates) > 1:
                d_str, b, idx = standalone_dates[-1]
                bb_field = ExtractedField(
                    field_type="best_before",
                    label="Best Before / Expiry",
                    raw_text=b.text,
                    parsed_value=d_str,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )

        return mfg_field, bb_field

    def _extract_manufacturer(self, blocks: List[OCRTextBlock], combined_text: str) -> Optional[ExtractedField]:
        mfr_keywords = [
            "manufactured by", "mfg by", "mfd by", "packed by", "pkd by",
            "marketed by", "mfr:", "packer:", "fssai", "fsal", "lic no",
            "pvt ltd", "pveltd", "private limited", "limited", "ltd.", "ltd", "parle agro"
        ]
        
        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(k in txt for k in mfr_keywords):
                start = max(0, idx - 1)
                end = min(len(blocks), idx + 4)
                address_parts = [blocks[i].text for i in range(start, end) if not self._is_nutrition_or_storage_line(blocks[i].text)]
                full_address = " ".join(address_parts)
                has_pincode = bool(self.re_pincode.search(full_address))

                return ExtractedField(
                    field_type="manufacturer",
                    label="Manufacturer / Packer Details",
                    raw_text=b.text if len(b.text) > 15 else full_address,
                    parsed_value={
                        "declaration": full_address,
                        "has_pincode": has_pincode
                    },
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
        return None

    def _extract_consumer_care(self, blocks: List[OCRTextBlock], combined_text: str) -> Optional[ExtractedField]:
        care_keywords = [
            "consumer care", "customer care", "grievance", "helpline", "feedback",
            "contact us", "queries", "call us", "calus", "toll free", "write to us", "wietous"
        ]
        email = None
        phone = None
        website = None
        matched_block = None
        matched_idx = None

        m_email = self.re_email.search(combined_text)
        if m_email:
            email = m_email.group(0)

        m_web = self.re_website.search(combined_text)
        if m_web:
            website = m_web.group(0)

        # Look for helpline phone, strictly avoiding FSSAI 14-digit license numbers
        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(k in txt for k in ["lic", "fssai", "fsal", "license", "lic.no"]):
                continue
            m_phone = self.re_phone.search(b.text)
            if m_phone:
                cand = m_phone.group(1).strip()
                if len(cand) in [8, 10, 11, 12] and not b.text.startswith("100"):
                    phone = cand
                    matched_block = b
                    matched_idx = idx
                    break

        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(k in txt for k in care_keywords) or (email and email in b.text) or (phone and phone in b.text) or (website and website in b.text):
                if not matched_block:
                    matched_block = b
                    matched_idx = idx
                break

        if email or phone or website or matched_block:
            contact_str = email or website or (f"Phone: {phone}" if phone else "Digital Helpline")
            raw = matched_block.text if matched_block else f"Phone: {phone or 'N/A'}, Contact: {contact_str}"
            return ExtractedField(
                field_type="consumer_care",
                label="Consumer Care / Grievance Redressal",
                raw_text=raw,
                parsed_value={
                    "email": email or website,
                    "phone": phone,
                    "has_both": bool((email or website) and phone)
                },
                confidence=matched_block.confidence if matched_block else 0.9,
                bbox=matched_block.bbox if matched_block else None,
                font_height_px=matched_block.height_px if matched_block else None,
                font_height_mm=matched_block.height_mm if matched_block else None,
                source_block_index=matched_idx
            )
        return None

    def _extract_country_of_origin(self, blocks: List[OCRTextBlock], combined_text: str) -> Optional[ExtractedField]:
        # 1. Explicit declaration "Country of Origin: ..." or "Made in India"
        m = self.re_origin.search(combined_text)
        if m:
            country = m.group(1).strip().split("\n")[0].strip()
            for idx, b in enumerate(blocks):
                if country in b.text:
                    return ExtractedField(
                        field_type="country_of_origin",
                        label="Country of Origin",
                        raw_text=b.text,
                        parsed_value=country,
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )

        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if "made in india" in txt or "product of india" in txt or "india" in txt:
                if self._is_nutrition_or_storage_line(b.text):
                    continue
                return ExtractedField(
                    field_type="country_of_origin",
                    label="Country of Origin",
                    raw_text=b.text,
                    parsed_value="India",
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )

        # 2. Inferred domestic origin from manufacturer postal address (Rule 6(10) domestic compliance)
        indian_regions = [
            "maharashtra", "madhya pradesh", "telangana", "gujarat", "karnataka",
            "tamil nadu", "delhi", "haryana", "uttar pradesh", "rajasthan",
            "punjab", "west bengal", "mumbai", "andheri", "patalganga",
            "mandideep", "sangareddy", "gurugram"
        ]
        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(r in txt for r in indian_regions):
                return ExtractedField(
                    field_type="country_of_origin",
                    label="Country of Origin",
                    raw_text=f"India (Manufactured in {b.text.strip()})",
                    parsed_value="India",
                    confidence=0.92,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )

        return None

    def _extract_commodity_name(self, blocks: List[OCRTextBlock], combined_text: str) -> Optional[ExtractedField]:
        # 1. Explicit keyword "Product: ...", "Commodity: ..."
        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(k in txt for k in ["product:", "commodity:", "item:"]):
                name = b.text.split(":")[-1].strip()
                if len(name) > 2:
                    return ExtractedField(
                        field_type="commodity_name",
                        label="Commodity Name",
                        raw_text=b.text,
                        parsed_value=name,
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )

        # 2. Known statutory commodity phrases (prioritized)
        statutory_phrases = [
            "ready to serve fruit drink", "fruit drink", "mango drink",
            "potato chips", "namkeen", "roasted snack", "cookies", "biscuits",
            "fruit juice", "carbonated beverage", "drinking water", "packaged drinking water"
        ]
        for idx, b in enumerate(blocks):
            t_low = b.text.lower()
            for phrase in statutory_phrases:
                if phrase in t_low:
                    return ExtractedField(
                        field_type="commodity_name",
                        label="Commodity Name",
                        raw_text=b.text,
                        parsed_value=b.text.strip(),
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )

        # 3. Clean title heuristic
        process_phrases = [
            "thermally processed", "pasteurized", "homogenized", "ingredients",
            "contains fruit", "serving size", "servings per", "nutrition",
            "crush the bottle", "recycle", "warning", "store away"
        ]
        for idx, b in enumerate(blocks[:8]):
            t = b.text.strip()
            if sum(c.isalpha() for c in t) < 4:
                continue
            if self._is_nutrition_or_storage_line(t):
                continue
            t_low = t.lower()
            if any(p in t_low for p in process_phrases):
                continue
            if any(k in t_low for k in ["mrp", "rs", "₹", "net", "mfd", "batch", "exp", "pkd", "fssai", "lic"]):
                continue

            return ExtractedField(
                field_type="commodity_name",
                label="Commodity Name",
                raw_text=t,
                parsed_value=t,
                confidence=b.confidence,
                bbox=b.bbox,
                font_height_px=b.height_px,
                font_height_mm=b.height_mm,
                source_block_index=idx
            )

        return None
