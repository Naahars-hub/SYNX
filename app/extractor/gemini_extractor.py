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

SYSTEM_PROMPT = """You are an expert Statutory Legal Metrology (Packaged Commodities) Inspector.
Analyze this packaged commodity label/image and its recognized text.

Your job is to identify:
1. "commodity_name": The official, common or generic commodity name under Rule 6(1)(b) of the Legal Metrology (Packaged Commodities) Rules, 2011.
   - Examples of valid generic commodity names: 'Vacuum Insulated Stainless Steel Bottle', 'Potato Chips', 'Packaged Drinking Water', 'Ready to Serve Fruit Drink', 'Instant Coffee Powder', 'Biscuits', 'Refined Sunflower Oil'.
   - CRITICAL STATUTORY RULES:
     * Do NOT use marketing slogans (e.g. '100% PURE', 'NATURAL', 'EXTRA TASTY') as the commodity name.
     * Do NOT use blend or roast descriptors (e.g. 'BLEND', 'DARKROAST') as the commodity name.
     * Do NOT use the brand name as the commodity name.
     * If the label has an explicit 'Generic Name:', 'Common Name:', or 'Name of Commodity:', use that exact declared commodity.
2. "brand_name": The commercial brand or manufacturer brand (e.g. 'Tata', 'Lays', 'Milton', 'Amul', 'Borosil', 'Parle').
3. "variant": Flavor, variant, or model designation if present (e.g. 'Gold', 'Classic Salted', 'Hydra 1000ml').
4. "confidence": Confidence score between 0.0 and 1.0 (float).

Respond ONLY with valid JSON conforming to this schema:
{
  "brand_name": "string",
  "commodity_name": "string",
  "variant": "string",
  "confidence": 1.0
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


def extract_commodity_with_gemini(
    image_input: Union[str, Path, bytes, Image.Image],
    ocr_blocks: Optional[List[OCRTextBlock]] = None,
    timeout_seconds: float = 10.0
) -> Optional[Dict[str, Any]]:
    """
    Calls Gemini 1.5 Flash to extract the official statutory generic commodity name
    and brand name from the product image and OCR tokens.

    Returns:
        Dict with keys: commodity_name, brand_name, variant, confidence, source
        or None if Gemini is unconfigured, times out, or encounters an error.
    """
    if not is_gemini_available():
        return None

    try:
        b64_image = _prepare_image_base64(image_input)

        ocr_context = ""
        if ocr_blocks:
            sample_texts = [b.text.strip() for b in ocr_blocks[:25] if b.text and len(b.text.strip()) > 1]
            if sample_texts:
                ocr_context = "\n\nOCR Recognized Text Snippets:\n" + "\n".join(f"- {xt}" for xt in sample_texts)

        user_prompt = f"Identify the official statutory generic commodity name and brand name for this packaged product.{ocr_context}"

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
                        "text": SYSTEM_PROMPT
                    }
                ]
            },
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 2048
            }
        }

        # Prioritized candidate models with automatic failover on 404 (deprecated) or 503 (high demand)
        candidate_models = []
        for m in [GEMINI_MODEL, "gemini-3.6-flash", "gemini-flash-latest"]:
            if m and m not in candidate_models:
                candidate_models.append(m)

        resp = None
        used_model = GEMINI_MODEL
        with httpx.Client(timeout=timeout_seconds) as client:
            for model_name in candidate_models:
                url = GEMINI_API_URL_TEMPLATE.format(model=model_name, key=GEMINI_API_KEY)
                r = client.post(url, json=payload)
                if r.status_code == 200:
                    resp = r
                    used_model = model_name
                    break
                elif r.status_code in (404, 503):
                    print(f"[GeminiExtractor] Model '{model_name}' returned HTTP {r.status_code}. Failing over to next model...")
                    continue
                else:
                    print(f"[GeminiExtractor] API returned HTTP {r.status_code}: {r.text[:200]}")
                    return None

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

        commodity = (parsed.get("commodity_name") or "").strip()
        brand = (parsed.get("brand_name") or "").strip()
        variant = (parsed.get("variant") or "").strip()
        conf = float(parsed.get("confidence", 0.95))

        if not commodity:
            return None

        print(f"[GeminiExtractor] Extracted Commodity: '{commodity}', Brand: '{brand}' (Confidence: {conf:.2f})")
        return {
            "commodity_name": commodity,
            "brand_name": brand,
            "variant": variant,
            "confidence": conf,
            "source": f"{used_model} multimodal"
        }

    except httpx.TimeoutException:
        print("[GeminiExtractor] Request timed out. Falling back to local visual-salience parser.")
        return None
    except Exception as e:
        raw_snippet = repr(raw_json_str) if 'raw_json_str' in locals() else 'N/A'
        print(f"[GeminiExtractor] Warning during extraction: {e}. (raw_text={raw_snippet}). Falling back to local parser.")
        return None
