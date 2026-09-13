import os
import io
import re
import json
import base64
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
import httpx
from PIL import Image

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.extractor.entities import OCRTextBlock

GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

STATUTORY_SYSTEM_PROMPT = """You are an expert Statutory Legal Metrology (Packaged Commodities) Rules, 2011 Inspector.
Analyze this packaged commodity label/image and its recognized text.

Extract any visible mandatory declarations accurately:
1. "commodity_name": The official, common or generic commodity name under Rule 6(1)(b) of PCR 2011 (e.g. 'Carbonated Caffeinated Beverage', 'Energy Drink', 'Vacuum Insulated Stainless Steel Bottle', 'Potato Chips', 'Packaged Drinking Water', 'Ready to Serve Fruit Drink', 'Instant Coffee Powder', 'Biscuits').
   - CRITICAL RULES:
     * Do NOT use marketing slogans (e.g. '100% PURE', 'NATURAL', 'UNLEASH THE BEAST') as commodity name.
     * Do NOT use blend or roast descriptors (e.g. 'BLEND', 'DARKROAST') as commodity name.
     * Do NOT use brand name as commodity name.
     * Do NOT use narrative story text (e.g. 'Our team riders and monster') as commodity name.
     * If explicit 'Generic Name:', 'Common Name:', or 'Name of Commodity:' is declared, use that exact commodity.
2. "brand_name": The commercial brand name (e.g. 'Monster Energy', 'Lay\'s', 'Milton', 'Amul').
3. "variant": Flavor, variant, or model designation (e.g. 'Ultra Zero Sugar', 'Classic Salted').
4. "mrp": Maximum Retail Price in rupees. Object with {"amount": float, "inclusive_of_all_taxes": bool, "raw": string}.
5. "unit_sale_price": Unit sale price. Object with {"amount": float, "unit": string, "raw": string}.
6. "mfg_date": Manufacturing / packaging date string (e.g. '04/NOV/25').
7. "best_before": Expiry / best before date string (e.g. '03/NOV/27').
8. "net_quantity": Net quantity. Object with {"amount": float, "unit": string, "raw": string}.
9. "consumer_care": Consumer grievance contact. Object with {"phone": string or null, "email": string or null, "address": string or null, "raw": string}.
10. "manufacturer": Name and postal address with pincode of manufacturer / packer / marketer. Object with {"name": string or null, "address": string or null, "raw": string, "has_pincode": bool}.
11. "country_of_origin": Declared or manufactured country of origin (e.g. 'India').

Respond ONLY with valid JSON conforming to this schema:
{
  "commodity_name": "string or null",
  "brand_name": "string or null",
  "variant": "string or null",
  "mrp": {"amount": 0.0, "inclusive_of_all_taxes": true, "raw": "string"} or null,
  "unit_sale_price": {"amount": 0.0, "unit": "string", "raw": "string"} or null,
  "mfg_date": "string or null",
  "best_before": "string or null",
  "net_quantity": {"amount": 0.0, "unit": "string", "raw": "string"} or null,
  "consumer_care": {"phone": "string or null", "email": "string or null", "address": "string or null", "raw": "string"} or null,
  "manufacturer": {"name": "string or null", "address": "string or null", "raw": "string", "has_pincode": true} or null,
  "country_of_origin": "string or null",
  "confidence": 0.95
}
"""


def is_gemini_available() -> bool:
    """Returns True if a valid Gemini API key is configured."""
    return bool(GEMINI_API_KEY and len(GEMINI_API_KEY.strip()) > 10)


def _prepare_image_base64(image_input: Union[str, Path, bytes, Image.Image], max_dimension: int = 1024) -> str:
    """
    Loads and resizes image to max_dimension to ensure fast cloud roundtrip (< 500ms)
    and returns a base64 encoded JPEG string.
    """
    if isinstance(image_input, Image.Image):
        pil_img = image_input
    elif isinstance(image_input, bytes):
        pil_img = Image.open(io.BytesIO(image_input))
    else:
        pil_img = Image.open(str(image_input))

    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    w, h = pil_img.size
    if max(w, h) > max_dimension:
        scale = max_dimension / max(w, h)
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def extract_statutory_declarations_with_gemini(
    image_input: Union[str, Path, bytes, Image.Image],
    ocr_blocks: Optional[List[OCRTextBlock]] = None,
    timeout_seconds: float = 20.0
) -> Optional[Dict[str, Any]]:
    """
    Calls Google Gemini multimodal vision to extract all statutory Legal Metrology
    declarations (commodity name, MRP, USP, dates, net quantity, manufacturer, consumer care, origin)
    from the packaging photo.

    Returns a dict conforming to the statutory declaration schema, or None on error/timeout.
    """
    if not is_gemini_available():
        return None

    try:
        b64_image = _prepare_image_base64(image_input)

        ocr_context = ""
        if ocr_blocks:
            sample_texts = [b.text.strip() for b in ocr_blocks[:30] if b.text and len(b.text.strip()) > 1]
            if sample_texts:
                ocr_context = "\n\nOCR Recognized Text Snippets:\n" + "\n".join(f"- {xt}" for xt in sample_texts)

        user_prompt = (
            f"Extract all statutory Legal Metrology declarations visible on this packaged product label.{ocr_context}"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image
                            }
                        },
                        {
                            "text": user_prompt
                        }
                    ]
                }
            ],
            "system_instruction": {
                "parts": [
                    {
                        "text": STATUTORY_SYSTEM_PROMPT
                    }
                ]
            },
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 3000
            }
        }

        # Prioritized candidate models with automatic failover
        candidate_models = []
        for m in [GEMINI_MODEL, "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.6-flash"]:
            if m and m not in candidate_models:
                candidate_models.append(m)

        resp = None
        used_model = GEMINI_MODEL
        with httpx.Client(timeout=timeout_seconds) as client:
            for model_name in candidate_models:
                url = GEMINI_API_URL_TEMPLATE.format(model=model_name, key=GEMINI_API_KEY)
                try:
                    r = client.post(url, json=payload)
                    if r.status_code == 200:
                        resp = r
                        used_model = model_name
                        break
                    elif r.status_code in (404, 429, 503):
                        print(f"[GeminiExtractor] Model '{model_name}' returned HTTP {r.status_code}. Cascading to next model...")
                        continue
                    else:
                        print(f"[GeminiExtractor] API returned HTTP {r.status_code}: {r.text[:200]}")
                        return None
                except (httpx.TimeoutException, httpx.RequestError) as net_err:
                    print(f"[GeminiExtractor] Network error on model '{model_name}': {net_err}. Trying next...")
                    continue

        if resp is None or resp.status_code != 200:
            return None

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return None

        raw_json_str = parts[0].get("text", "").strip()
        if raw_json_str.startswith("```"):
            lines = raw_json_str.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_json_str = "\n".join(lines).strip()

        # Extract innermost JSON object if wrapped in conversational explanation
        json_match = re.search(r'(\{[\s\S]*\})', raw_json_str)
        if json_match:
            raw_json_str = json_match.group(1)

        parsed = json.loads(raw_json_str)
        parsed["source_model"] = used_model
        return parsed

    except httpx.TimeoutException:
        print("[GeminiExtractor] Request timed out. Falling back to local visual-salience parser.")
        return None
    except Exception as e:
        raw_snippet = repr(raw_json_str) if 'raw_json_str' in locals() else 'N/A'
        print(f"[GeminiExtractor] Warning during extraction: {e}. (raw_text={raw_snippet}). Falling back to local parser.")
        return None


def extract_commodity_with_gemini(
    image_input: Union[str, Path, bytes, Image.Image],
    ocr_blocks: Optional[List[OCRTextBlock]] = None,
    timeout_seconds: float = 20.0
) -> Optional[Dict[str, Any]]:
    """
    Calls Gemini to extract the official statutory generic commodity name
    and brand name from the product image and OCR tokens.
    """
    parsed = extract_statutory_declarations_with_gemini(image_input, ocr_blocks, timeout_seconds=timeout_seconds)
    if not parsed:
        return None

    commodity = (parsed.get("commodity_name") or "").strip()
    brand = (parsed.get("brand_name") or "").strip()
    variant = (parsed.get("variant") or "").strip()
    conf = float(parsed.get("confidence") or 0.95)
    used_model = parsed.get("source_model", GEMINI_MODEL)

    if not commodity:
        return None

    print(f"[GeminiExtractor] Extracted Commodity: '{commodity}', Brand: '{brand}' (Model: {used_model})")
    return {
        "commodity_name": commodity,
        "brand_name": brand,
        "variant": variant,
        "confidence": conf,
        "source": f"{used_model} multimodal"
    }
