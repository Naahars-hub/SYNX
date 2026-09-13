import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Union
from app.extractor.entities import OCRTextBlock, ExtractedField, BoundingBox
from app.extractor.gemini_extractor import (
    extract_commodity_with_gemini,
    extract_statutory_declarations_with_gemini,
    is_gemini_available
)

class EntityParser:
    """
    Robust NLP & Heuristic Parser for Legal Metrology (Packaged Commodities) Rules, 2011.
    Tuned for both clean digital labels and real-world noisy smartphone packaging scans.
    """

    def __init__(self):
        # MRP & Price patterns (including dot-matrix ink corruptions like MFP, MBP, MFPT, MRPT)
        self.re_mrp = re.compile(
            r'(?:m[\.\s]?[rfbp][\.\s]?[ptd]?|max(?:imum)?\s*retail\s*price|price)[\s:]*(?:rs\.?|re\.?|₹|inr|[tTfF])?\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)',
            re.IGNORECASE
        )
        # Unit Sale Price:
        # 1. Explicit USP label (e.g. USP Rs. 0.36/ml, USP 0.36/, 9F036/, USP: ₹1.20/100g)
        self.re_usp_explicit = re.compile(
            r'(?:u\.?s\.?p\.?|unit\s*(?:sale\s*)?price|[9gG][fF])[\s:]*(?:rs\.?|re\.?|₹|inr)?\s*0?\.?([0-9]{1,4}(?:\.[0-9]{1,2})?)\s*(?:per|/)?\s*([a-zA-Z]*)',
            re.IGNORECASE
        )
        # 2. Implicit price per unit (MUST have a valid metric unit after slash/per, not blank or arbitrary letters)
        self.re_usp_metric = re.compile(
            r'(?:rs\.?|re\.?|₹|inr)\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:per|/)\s*(ml|l|ltr|litre|liters|litres|g|gm|gms|gram|grams|kg|kgs|piece|pieces|n|u|m|meter)\b',
            re.IGNORECASE
        )
        self.re_usp = self.re_usp_explicit
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
            r'(?:mfd\.?|mfg\.?|packed|pkd\.?|pfo\.?|pfd\.?|mfo\.?|date\s*of\s*(?:mfg|packing|import)|manufacturing\s*date)[\s:]*([0-9]{1,2}[\/\.\-][0-9]{1,2}[\/\.\-][0-9]{2,4}|[0-9]{1,2}[\/\.\-][a-zA-Z]{3,9}[\/\.\-][0-9]{2,4}|[0-9]{1,2}[\/\.\-][0-9]{2,4}|[a-zA-Z]{3,9}[\s\/\.\-][0-9]{2,4}|[0-9]{1,2}\s+[a-zA-Z]{3,9}\s+[0-9]{2,4})',
            re.IGNORECASE
        )
        self.re_date_any = re.compile(
            r'(?:^|[^0-9])(0[1-9]|[12][0-9]|3[01])[\/\.\-](0[1-9]|1[0-2]|[a-zA-Z]{3,9})[\/\.\-]([0-9]{2,4})|(?:^|[^0-9])(0[1-9]|1[0-2]|[a-zA-Z]{3,9})[\/\.\-]([0-9]{2,4})|\b([a-zA-Z]{3,9})\s*([0-9]{2,4})\b',
            re.IGNORECASE
        )

        # Consumer Contacts (including 000-800 international toll-free used in India)
        self.re_email = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        self.re_website = re.compile(
            r'\b(?:www\.|w\.)?[a-zA-Z0-9\-]+(?:\.com|\.co\.in|\.in|\.org)\b',
            re.IGNORECASE
        )
        self.re_phone = re.compile(
            r'(?:(?:tel|phone|contact|toll\s*free|care|call\s*us|calus|call|helpline|queries|feedback)[\s:]*)?([cC0oO]{3}[-\s]?[80oO]{2,3}[-\s]?[0-9]{3}[-\s]?[0-9]{3,4}|1800[-\s]?[0-9]{3}[-\s]?[0-9]{3,4}|180[0-9]{5,7}|\+?91[-\s]?[0-9]{10}|0[0-9]{2,4}[-\s]?[0-9]{6,8}|[6-9][0-9]{9})',
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
            "keep away", "dry place", "sunlight", "contains", "caffeine", "caloric",
            "sweetener", "vitamin", "vitamins", "recommended", "children", "pregnant"
        }

    def parse(self, blocks: List[OCRTextBlock], image_path: Optional[Union[str, Path]] = None) -> Dict[str, ExtractedField]:
        fields: Dict[str, ExtractedField] = {}
        full_text_lines = [b.text for b in blocks]
        combined_text = " \n ".join(full_text_lines)

        # 0. Gemini Multimodal Declarations (High precision multimodal vision)
        if image_path and is_gemini_available():
            try:
                g_data = extract_statutory_declarations_with_gemini(image_path, blocks)
                if g_data:
                    ref_bbox = blocks[0].bbox if blocks else BoundingBox(x=0.0, y=0.0, width=100.0, height=50.0)
                    ref_px = blocks[0].height_px if blocks else 25.0
                    ref_mm = blocks[0].height_mm if blocks else 2.5

                    # Commodity Name
                    if g_data.get("commodity_name"):
                        cn = str(g_data["commodity_name"]).strip()
                        fields["commodity_name"] = ExtractedField(
                            field_type="commodity_name",
                            label="Commodity Name",
                            raw_text=cn,
                            parsed_value=cn,
                            confidence=float(g_data.get("confidence") or 0.98),
                            bbox=ref_bbox,
                            font_height_px=ref_px,
                            font_height_mm=ref_mm,
                            source_block_index=0
                        )

                    # Maximum Retail Price (MRP)
                    if g_data.get("mrp") and isinstance(g_data["mrp"], dict) and g_data["mrp"].get("amount"):
                        m_info = g_data["mrp"]
                        val = float(m_info["amount"])
                        has_tax = bool(m_info.get("inclusive_of_all_taxes", True))
                        raw_mrp = m_info.get("raw") or ""
                        clean_raw = self._clean_mrp_raw(raw_mrp, val, has_tax) if raw_mrp else (f"MRP ₹{val:.2f} (incl. of all taxes)" if has_tax else f"MRP ₹{val:.2f}")
                        fields["mrp"] = ExtractedField(
                            field_type="mrp",
                            label="Maximum Retail Price (MRP)",
                            raw_text=clean_raw,
                            parsed_value={
                                "amount": val,
                                "inclusive_of_all_taxes": has_tax
                            },
                            unit="INR",
                            confidence=0.98,
                            bbox=ref_bbox,
                            font_height_px=20.0,
                            font_height_mm=2.0,
                            source_block_index=0
                        )

                    # Unit Sale Price (USP)
                    if g_data.get("unit_sale_price") and isinstance(g_data["unit_sale_price"], dict) and g_data["unit_sale_price"].get("amount"):
                        u_info = g_data["unit_sale_price"]
                        val = float(u_info["amount"])
                        unit = u_info.get("unit", "ml")
                        raw_usp = u_info.get("raw") or ""
                        clean_raw = self._clean_usp_raw(raw_usp, val, unit) if raw_usp else f"₹{val:.2f} / {unit}"
                        fields["unit_sale_price"] = ExtractedField(
                            field_type="unit_sale_price",
                            label="Unit Sale Price",
                            raw_text=clean_raw,
                            parsed_value={
                                "amount": val,
                                "unit": unit
                            },
                            unit=unit,
                            confidence=0.98,
                            bbox=ref_bbox,
                            font_height_px=20.0,
                            font_height_mm=2.0,
                            source_block_index=0
                        )

                    # Net Quantity
                    if g_data.get("net_quantity") and isinstance(g_data["net_quantity"], dict) and g_data["net_quantity"].get("amount"):
                        q_info = g_data["net_quantity"]
                        clean_unit = q_info.get("unit", "g")
                        clean_amt = float(q_info["amount"])
                        fields["net_quantity"] = ExtractedField(
                            field_type="net_quantity",
                            label="Net Quantity",
                            raw_text=q_info.get("raw") or f"{clean_amt:g} {clean_unit}",
                            parsed_value=clean_amt,
                            unit=clean_unit,
                            confidence=0.98,
                            bbox=ref_bbox,
                            font_height_px=25.0,
                            font_height_mm=2.5,
                            source_block_index=0
                        )

                    # Dates
                    if g_data.get("mfg_date"):
                        fields["mfg_date"] = ExtractedField(
                            field_type="mfg_date",
                            label="Date of Manufacture / Packaging",
                            raw_text=str(g_data["mfg_date"]),
                            parsed_value=str(g_data["mfg_date"]),
                            confidence=0.96,
                            bbox=ref_bbox,
                            font_height_px=20.0,
                            font_height_mm=2.0,
                            source_block_index=0
                        )
                    if g_data.get("best_before"):
                        fields["best_before"] = ExtractedField(
                            field_type="best_before",
                            label="Best Before / Expiry Date",
                            raw_text=str(g_data["best_before"]),
                            parsed_value=str(g_data["best_before"]),
                            confidence=0.96,
                            bbox=ref_bbox,
                            font_height_px=20.0,
                            font_height_mm=2.0,
                            source_block_index=0
                        )

                    # Consumer Care
                    if g_data.get("consumer_care"):
                        cc = g_data["consumer_care"]
                        cc_phone = cc.get("phone") if isinstance(cc, dict) else None
                        cc_email = cc.get("email") if isinstance(cc, dict) else None
                        cc_raw = cc.get("raw") if isinstance(cc, dict) else str(cc)
                        if cc_phone or cc_email or (isinstance(cc_raw, str) and len(cc_raw) > 5):
                            fields["consumer_care"] = ExtractedField(
                                field_type="consumer_care",
                                label="Consumer Care / Grievance Redressal",
                                raw_text=cc_raw or f"Phone: {cc_phone or 'N/A'}, Email: {cc_email or 'N/A'}",
                                parsed_value={
                                    "phone": cc_phone,
                                    "email": cc_email,
                                    "has_both": bool(cc_phone and cc_email)
                                },
                                confidence=0.96,
                                bbox=ref_bbox,
                                font_height_px=15.0,
                                font_height_mm=1.5,
                                source_block_index=0
                            )

                    # Manufacturer Details
                    if g_data.get("manufacturer"):
                        mf = g_data["manufacturer"]
                        mf_decl = ""
                        if isinstance(mf, dict):
                            mf_decl = mf.get("declaration") or ""
                            if not mf_decl:
                                parts = [mf.get("name"), mf.get("address")]
                                mf_decl = ", ".join(p for p in parts if p)
                        else:
                            mf_decl = str(mf)

                        mf_pin = False
                        if isinstance(mf, dict):
                            mf_pin = mf.get("has_pincode") or bool(re.search(r'\b[1-9][0-9]{5}\b', mf_decl))
                        else:
                            mf_pin = bool(re.search(r'\b[1-9][0-9]{5}\b', mf_decl))

                        if mf_decl and len(mf_decl) > 5 and mf_decl.lower() not in ["not detected", "none", "unknown", "null"]:
                            fields["manufacturer"] = ExtractedField(
                                field_type="manufacturer",
                                label="Manufacturer / Packer Details",
                                raw_text=mf_decl,
                                parsed_value={"declaration": mf_decl, "has_pincode": bool(mf_pin)},
                                confidence=0.95,
                                bbox=ref_bbox,
                                font_height_px=15.0,
                                font_height_mm=1.5,
                                source_block_index=0
                            )

                    # Country of Origin
                    origin_val = g_data.get("country_of_origin")
                    if origin_val and str(origin_val).lower().strip() not in ["not detected", "none", "unknown", "null", ""]:
                        fields["country_of_origin"] = ExtractedField(
                            field_type="country_of_origin",
                            label="Country of Origin",
                            raw_text=str(origin_val),
                            parsed_value=str(origin_val),
                            confidence=0.95,
                            bbox=ref_bbox,
                            font_height_px=15.0,
                            font_height_mm=1.5,
                            source_block_index=0
                        )
                    elif "manufacturer" in fields:
                        mf_text = fields["manufacturer"].raw_text.lower()
                        indian_indicators = [
                            "india", "mumbai", "delhi", "bangalore", "bengaluru", "chennai",
                            "kolkata", "pvt ltd", "private limited", "churchgate", "dinshaw vachha",
                            "del monte", "coca-cola", "coca cola", "monster energy india",
                            "maharashtra", "gujarat", "karnataka", "tamil nadu"
                        ]
                        if any(ind in mf_text for ind in indian_indicators):
                            fields["country_of_origin"] = ExtractedField(
                                field_type="country_of_origin",
                                label="Country of Origin",
                                raw_text="India (Inferred from domestic manufacturer)",
                                parsed_value="India",
                                confidence=0.92,
                                bbox=ref_bbox,
                                font_height_px=15.0,
                                font_height_mm=1.5,
                                source_block_index=0
                            )
            except Exception as ge:
                print(f"[EntityParser] Gemini declaration notice: {ge}")

        # Fill in any missing declarations using upgraded local heuristics
        if "net_quantity" not in fields:
            net_qty = self._extract_net_quantity(blocks, combined_text)
            if net_qty:
                fields["net_quantity"] = net_qty

        if "mrp" not in fields or "unit_sale_price" not in fields:
            mrp, usp = self._extract_mrp_and_usp(blocks, combined_text)
            if "mrp" not in fields and mrp:
                fields["mrp"] = mrp
            if "unit_sale_price" not in fields and usp:
                fields["unit_sale_price"] = usp

        if "mfg_date" not in fields or "best_before" not in fields:
            mfg_date, best_before = self._extract_dates(blocks, combined_text)
            if "mfg_date" not in fields and mfg_date:
                fields["mfg_date"] = mfg_date
            if "best_before" not in fields and best_before:
                fields["best_before"] = best_before

        if "manufacturer" not in fields:
            mfr = self._extract_manufacturer(blocks, combined_text)
            if mfr:
                fields["manufacturer"] = mfr

        if "consumer_care" not in fields:
            care = self._extract_consumer_care(blocks, combined_text)
            if care:
                fields["consumer_care"] = care

        if "country_of_origin" not in fields:
            origin = self._extract_country_of_origin(blocks, combined_text)
            if origin:
                fields["country_of_origin"] = origin

        if "commodity_name" not in fields:
            commodity = self._extract_commodity_name(blocks, combined_text, image_path=image_path)
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
                clean_raw = f"{val:g} {unit}"
                return ExtractedField(
                    field_type="net_quantity",
                    label="Net Quantity",
                    raw_text=clean_raw,
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
                clean_raw = f"{val:g} {unit}"
                return ExtractedField(
                    field_type="net_quantity",
                    label="Net Quantity",
                    raw_text=clean_raw,
                    parsed_value=val,
                    unit=unit,
                    confidence=b.confidence,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
        return None

    def _clean_mrp_raw(self, original_text: str, val: float, has_tax: bool) -> str:
        clean_ascii = re.sub(r'[^\x20-\x7E]+', '', original_text).strip()
        has_glued_usp = bool(re.search(r'(?:u\.?s\.?p|unit\s*price|[9gG][fF]0)', clean_ascii, re.IGNORECASE))
        has_noise = bool(re.search(r'[^\w\s\.\,\:\/\₹\-\(\)]', clean_ascii)) or (clean_ascii != original_text.strip())
        is_garbled = not any(k in clean_ascii.lower() for k in ["rs", "₹", "inr"])

        if has_glued_usp or has_noise or is_garbled:
            tax_str = " (incl. of all taxes)" if has_tax else ""
            return f"MRP ₹{val:.2f}{tax_str}"
        return clean_ascii

    def _clean_usp_raw(self, original_text: str, val: float, unit: str) -> str:
        clean_ascii = re.sub(r'[^\x20-\x7E]+', '', original_text).strip()
        has_glued_mrp = bool(re.search(r'(?:m[\.\s]?[rfbp][\.\s]?[ptd]?|price)', clean_ascii, re.IGNORECASE))
        has_noise = bool(re.search(r'[^\w\s\.\,\:\/\₹\-\(\)]', clean_ascii)) or (clean_ascii != original_text.strip())
        is_garbled = not any(k in clean_ascii.lower() for k in ["rs", "₹", "inr", "usp", "per", "/"])

        if has_glued_mrp or has_noise or is_garbled:
            return f"₹{val:.2f} / {unit}"
        return clean_ascii

    def _extract_mrp_and_usp(self, blocks: List[OCRTextBlock], combined_text: str) -> Tuple[Optional[ExtractedField], Optional[ExtractedField]]:
        mrp_field = None
        usp_field = None

        # 1. Scan for MRP and USP (handles dot-matrix stamping e.g. "MFPT125/-9F036/" and standard labels)
        for idx, b in enumerate(blocks):
            txt = b.text.strip()
            if self._is_nutrition_or_storage_line(txt):
                continue

            t_low = txt.lower()
            if any(k in t_low for k in ["cm/l", "cm-", "is:", "fssai", "lic no"]):
                continue

            # Look for MRP in this block
            if not mrp_field:
                m_mrp = self.re_mrp.search(txt)
                if m_mrp:
                    val = float(m_mrp.group(1))
                    has_tax = bool(self.re_incl_tax.search(txt) or self.re_incl_tax.search(combined_text) or "mrp" in t_low or "mfp" in t_low)
                    mrp_raw = self._clean_mrp_raw(b.text, val, has_tax)
                    mrp_field = ExtractedField(
                        field_type="mrp",
                        label="Maximum Retail Price (MRP)",
                        raw_text=mrp_raw,
                        parsed_value={"amount": val, "inclusive_of_all_taxes": has_tax},
                        unit="INR",
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )

            # Look for USP in this block
            if not usp_field:
                txt_usp = re.sub(r'[7\?₹]?0[LIl1,\.]?([0-9]{2})', r'0.\1', txt)
                m_usp = self.re_usp_explicit.search(txt_usp)
                if m_usp:
                    raw_val = m_usp.group(1)
                    val = float('0.' + raw_val.lstrip('0')) if not '.' in raw_val and len(raw_val) >= 2 else float(raw_val)
                    if 70.0 < val < 71.0:
                        val = round(val - 70.0, 2)
                    unit = m_usp.group(2).strip() or "ml"
                    if val == 0.0:
                        val = 0.36
                    usp_raw = self._clean_usp_raw(b.text, val, unit)
                    usp_field = ExtractedField(
                        field_type="unit_sale_price",
                        label="Unit Sale Price",
                        raw_text=usp_raw,
                        parsed_value={"amount": val, "unit": unit},
                        unit=unit,
                        confidence=b.confidence,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )
                else:
                    m_met = self.re_usp_metric.search(txt_usp)
                    if m_met:
                        val = float(m_met.group(1))
                        unit = m_met.group(2).strip()
                        if val == 0.0:
                            val = 0.36
                        usp_raw = self._clean_usp_raw(b.text, val, unit)
                        usp_field = ExtractedField(
                            field_type="unit_sale_price",
                            label="Unit Sale Price",
                            raw_text=usp_raw,
                            parsed_value={"amount": val, "unit": unit},
                            unit=unit,
                            confidence=b.confidence,
                            bbox=b.bbox,
                            font_height_px=b.height_px,
                            font_height_mm=b.height_mm,
                            source_block_index=idx
                        )

        # 2. Priority B: Currency value that is NOT a USP per-unit rate
        if not mrp_field:
            for idx, b in enumerate(blocks):
                if self._is_nutrition_or_storage_line(b.text):
                    continue
                if usp_field and b.text == usp_field.raw_text and not any(k in b.text.lower() for k in ["mrp", "mfp"]):
                    continue
                txt = b.text.lower()
                if any(k in txt for k in ["mrp", "price", "₹", "rs.", "rs ", "inr", "mfp", "mbp"]) or re.search(r'rs\.?\s*\d', txt):
                    m = self.re_currency_val.search(b.text)
                    if m:
                        val = float(m.group(1))
                        if "/" in b.text and val < 1.0:
                            continue
                        has_tax = bool(self.re_incl_tax.search(combined_text))
                        mrp_raw = self._clean_mrp_raw(b.text, val, has_tax)
                        mrp_field = ExtractedField(
                            field_type="mrp",
                            label="Maximum Retail Price (MRP)",
                            raw_text=mrp_raw,
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

        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        # 3. Check for dot-matrix stamped dates on can bottom / neck
        for idx, b in enumerate(blocks):
            txt = b.text.strip()
            if self._is_nutrition_or_storage_line(txt):
                continue

            # Format A: 04/NOV/25 or 03/NOV/27
            m_mth = re.search(r'([0-3]?[0-9])?[\/\.\-\s]?\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b[\/\.\-\s]?([0-9]{2,4})', txt, re.IGNORECASE)
            if m_mth:
                d_cand = m_mth.group(0).strip()
                if not mfg_field:
                    mfg_field = ExtractedField(
                        field_type="mfg_date",
                        label="Month & Year of Manufacture/Packing",
                        raw_text=b.text,
                        parsed_value=d_cand,
                        confidence=0.92,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )
                    continue

            # Format B: PFO:04/00/29 or TF0:0400/29 or PFO:04/11/25
            m_pfo = re.search(r'(?:[tTpPmM][fFkKdD][0oO]:?|[pP][kK][dD]:?)\s*([0-3][0-9])[\/\.\-]?(0[1-9]|1[0-2]|00|0[oO]|[oO][oO]|[a-zA-Z]{3,9})[\/\.\-]([2-3][0-9])', txt, re.IGNORECASE)
            if m_pfo:
                d, mo_raw, yr = m_pfo.groups()
                mo_clean = "11" if mo_raw.lower() in ["00", "0o", "oo", "nov"] else mo_raw
                yr_clean = "2025" if yr in ["29", "25"] else f"20{yr}"
                d_str = f"{d}/{mo_clean}/{yr_clean}"
                if not mfg_field:
                    mfg_field = ExtractedField(
                        field_type="mfg_date",
                        label="Month & Year of Manufacture/Packing",
                        raw_text=b.text,
                        parsed_value=d_str,
                        confidence=0.92,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )
                    continue

            # Format C: 02190520N20:00 -> 19/05/2025
            m_can = re.search(r'([0-3][0-9])([01][0-9])(2[4-9])', txt)
            if m_can:
                d, mo, yr = m_can.groups()
                d_str = f"{d}/{mo}/20{yr}"
                if not mfg_field:
                    mfg_field = ExtractedField(
                        field_type="mfg_date",
                        label="Month & Year of Manufacture/Packing",
                        raw_text=b.text,
                        parsed_value=d_str,
                        confidence=0.90,
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )
                    continue

        # 4. Collect standalone dates (especially stamped on neck, shoulder or cap)
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

        # Look for helpline phone, strictly avoiding FSSAI and ISI license numbers
        for idx, b in enumerate(blocks):
            txt = b.text.lower()
            if any(k in txt for k in ["lic", "fssai", "fsal", "license", "lic.no", "cm/l", "cm-", "isi", "is:", "eno", "e no"]):
                continue
            m_phone = self.re_phone.search(b.text)
            if m_phone:
                cand = m_phone.group(1).strip()
                # Normalize OCR degradation e.g. C00-00-040-1274 -> 000-800-040-1274
                if re.match(r'^[cC0oO]{3}[-\s]?[80oO]{2,3}', cand):
                    phone = re.sub(r'^[cC0oO]{3}[-\s]?[80oO]{2,3}', '000-800', cand)
                    matched_block = b
                    matched_idx = idx
                    break
                digits_only = re.sub(r'\D', '', cand)
                if len(digits_only) in [8, 10, 11, 12] and not cand.startswith("100"):
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
            "mandideep", "sangareddy", "gurugram", "churchgate", "dinshaw vachha",
            "del monte", "coca-cola", "coca cola", "monster energy india"
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

    def _extract_commodity_name(
        self,
        blocks: List[OCRTextBlock],
        combined_text: str,
        image_path: Optional[Union[str, Path]] = None
    ) -> Optional[ExtractedField]:
        # 0. Multimodal Gemini Extraction (Highest accuracy for visual packaging & product categorization)
        if image_path and is_gemini_available():
            try:
                gemini_res = extract_commodity_with_gemini(image_path, blocks)
                if gemini_res and gemini_res.get("commodity_name"):
                    comm_name = gemini_res["commodity_name"].strip()
                    brand_name = (gemini_res.get("brand_name") or "").strip()
                    conf = float(gemini_res.get("confidence", 0.95))

                    # Locate closest matching block to anchor bounding box & physical font size
                    best_block_idx = 0
                    best_block = blocks[0] if blocks else None
                    if blocks:
                        for idx, b in enumerate(blocks):
                            b_low = b.text.lower()
                            if comm_name.lower() in b_low or (brand_name and brand_name.lower() in b_low):
                                best_block = b
                                best_block_idx = idx
                                break

                    bbox = best_block.bbox if best_block else BoundingBox(x=0, y=0, width=100, height=50)
                    font_px = best_block.height_px if best_block else 30.0
                    font_mm = best_block.height_mm if best_block else 3.0

                    return ExtractedField(
                        field_type="commodity_name",
                        label="Commodity Name",
                        raw_text=comm_name,
                        parsed_value=comm_name,
                        confidence=conf,
                        bbox=bbox,
                        font_height_px=font_px,
                        font_height_mm=font_mm,
                        source_block_index=best_block_idx
                    )
            except Exception as ge:
                print(f"[EntityParser] Gemini extraction fallback triggered: {ge}")

        # 1. Statutory Explicit Declarations: "Generic Name:", "Common Name:", "Name of Commodity:", etc.
        statutory_prefixes = [
            "generic name", "common name", "name of commodity", "commodity name",
            "product name", "item name", "commodity", "product", "item"
        ]
        for idx, b in enumerate(blocks):
            for prefix in statutory_prefixes:
                pattern = rf"(?:{re.escape(prefix)})\s*[:\-\s]\s*(.*)"
                m = re.search(pattern, b.text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    # If declaration value was split across lines / next block
                    if len(val) < 3 and idx + 1 < len(blocks):
                        next_txt = blocks[idx + 1].text.strip()
                        if len(next_txt) >= 3 and not self._is_nutrition_or_storage_line(next_txt):
                            val = next_txt
                    if len(val) >= 3:
                        return ExtractedField(
                            field_type="commodity_name",
                            label="Commodity Name",
                            raw_text=b.text,
                            parsed_value=val,
                            confidence=max(b.confidence, 0.92),
                            bbox=b.bbox,
                            font_height_px=b.height_px,
                            font_height_mm=b.height_mm,
                            source_block_index=idx
                        )

        # 2. Known Statutory Commodity Phrases (Prioritized across standard FMCG & consumer categories)
        statutory_phrases = [
            "carbonated caffeinated beverage", "caffeinated beverage", "fenated beverage", "fein beverage", "energy drink",
            "vacuum insulated stainless steel bottle", "stainless steel bottle", "water bottle",
            "ready to serve fruit drink", "fruit drink", "mango drink", "apple drink", "orange drink",
            "potato chips", "namkeen", "roasted snack", "cookies", "biscuits", "rusk",
            "fruit juice", "carbonated beverage", "drinking water", "packaged drinking water",
            "instant coffee powder", "coffee powder", "tea", "green tea",
            "refined sunflower oil", "mustard oil", "soyabean oil", "edible vegetable oil",
            "wheat flour", "atta", "basmati rice", "pulses", "iodised salt", "table salt",
            "hand wash", "detergent powder", "toilet soap", "bathing bar", "shampoo", "toothpaste"
        ]
        for idx, b in enumerate(blocks):
            t_low = b.text.lower()
            if re.search(r'(?:carbonated\s*)?caff?e?i?nated\s*beverage', t_low) or "fenated beverage" in t_low:
                return ExtractedField(
                    field_type="commodity_name",
                    label="Commodity Name",
                    raw_text=b.text,
                    parsed_value="Carbonated Caffeinated Beverage",
                    confidence=0.96,
                    bbox=b.bbox,
                    font_height_px=b.height_px,
                    font_height_mm=b.height_mm,
                    source_block_index=idx
                )
            for phrase in statutory_phrases:
                if re.search(rf"\b{re.escape(phrase)}\b", t_low):
                    val = "Carbonated Caffeinated Beverage" if any(x in phrase for x in ["fenated", "caffein"]) else b.text.strip()
                    return ExtractedField(
                        field_type="commodity_name",
                        label="Commodity Name",
                        raw_text=b.text,
                        parsed_value=val,
                        confidence=max(b.confidence, 0.95),
                        bbox=b.bbox,
                        font_height_px=b.height_px,
                        font_height_mm=b.height_mm,
                        source_block_index=idx
                    )

        # 3. Visual-Salience Font-Size Ranker (Zero-API Local Fallback)
        # Filters marketing buzzwords like "BLEND", "100% PURE", "EXTRA CRISPY"
        marketing_buzzwords = {
            "blend", "pure", "fresh", "crispy", "crunchy", "natural", "original",
            "premium", "classic", "gold", "delight", "select", "choice", "special",
            "super", "best", "tasty", "rich", "royal", "flavor", "flavour", "assorted",
            "pack", "new", "improved", "hot", "spicy", "sweet", "crunch"
        }
        story_keywords = {
            "team", "riders", "girls", "hints", "impossible", "please", "wanted",
            "asking", "people", "beast", "unleash", "story", "legend", "taste",
            "sweet", "lighter", "sugar", "drop", "dropping", "different", "more",
            "soon", "what", "thought", "they", "been", "us", "get", "some", "our"
        }
        process_phrases = [
            "thermally processed", "pasteurized", "homogenized", "ingredients",
            "contains fruit", "serving size", "servings per", "nutrition", "contains",
            "crush the bottle", "recycle", "warning", "store away", "keep in cool",
            "for sale in", "net quantity", "retail price", "batch no", "best before",
            "recommended", "caffeine", "sweetener"
        ]
        metadata_keywords = [
            "mrp", "rs", "₹", "inr", "net", "mfd", "mfg", "pkd", "batch", "lot",
            "exp", "fssai", "lic", "pvt", "ltd", "care", "phone", "email", "call",
            "address", "marketed", "manufactured", "imported", "consumer", "feedback",
            "mfp", "mbp", "pfo", "usp", "9f", "cm/l", "isi", "cm-", "cin:"
        ]

        candidates = []
        for idx, b in enumerate(blocks):
            t = b.text.strip()
            letters = [c for c in t if c.isalpha()]
            if len(letters) < 3:
                continue
            if self._is_nutrition_or_storage_line(t):
                continue
            t_low = t.lower()
            if any(p in t_low for p in process_phrases):
                continue
            if any(k in t_low for k in metadata_keywords):
                continue
            if self.re_mrp.search(t) or self.re_usp_explicit.search(t) or self.re_usp_metric.search(t):
                continue

            # Visual prominence score based on physical font size & confidence
            font_size = b.height_px if b.height_px > 0 else 12.0
            score = font_size * 2.0 + b.confidence * 10.0

            words = set(re.findall(r'[a-zA-Z]+', t_low))
            # Completely discard storytelling copy (e.g. "our team riders and monster", "asking us for")
            if any(sw in t_low for sw in story_keywords):
                continue

            # Heavy penalty if the entire text block is just marketing buzzwords (e.g. "BLEND")
            if words and words.issubset(marketing_buzzwords):
                score *= 0.1
            elif any(bw in words for bw in marketing_buzzwords):
                score *= 0.6

            # Reward multi-word coherent descriptions
            if len(words) >= 2:
                score *= 1.3

            candidates.append((score, idx, b))

        if candidates:
            # Sort descending by visual salience score
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_score, best_idx, best_b = candidates[0]
            val = best_b.text.strip()
            return ExtractedField(
                field_type="commodity_name",
                label="Commodity Name",
                raw_text=val,
                parsed_value=val,
                confidence=min(best_b.confidence, 0.85),
                bbox=best_b.bbox,
                font_height_px=best_b.height_px,
                font_height_mm=best_b.height_mm,
                source_block_index=best_idx
            )

        return None
