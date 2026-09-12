import os
import math
from pathlib import Path
from typing import List, Optional, Union, Tuple
import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:
    cv2 = None

from app.extractor.entities import OCRTextBlock, BoundingBox

# Global engine singleton
_RAPID_OCR_INSTANCE = None

def get_ocr_engine():
    global _RAPID_OCR_INSTANCE
    if _RAPID_OCR_INSTANCE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR_INSTANCE = RapidOCR()
        except Exception as e:
            print(f"[OCR] RapidOCR initialization warning: {e}")
            _RAPID_OCR_INSTANCE = None
    return _RAPID_OCR_INSTANCE

class OCREngine:
    def __init__(self):
        self.engine = get_ocr_engine()

    def _enhance_packaging_image(self, img_np: np.ndarray) -> np.ndarray:
        """
        Applies contrast enhancement (CLAHE) on the luminance channel
        to reduce wrapper reflections/glare and boost faint inkjet text.
        """
        if cv2 is None:
            return img_np

        try:
            # Convert RGB to LAB
            lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            # Apply CLAHE to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
            return enhanced
        except Exception:
            return img_np

    def process_image(
        self, 
        image_input: Union[str, Path, Image.Image, np.ndarray],
        mm_per_pixel: Optional[float] = None
    ) -> List[OCRTextBlock]:
        """
        Runs OCR and returns structured OCRTextBlock objects with polygon coordinates
        and physical font height in mm.
        """
        # Convert PIL Image or Path to numpy array
        if isinstance(image_input, (str, Path)):
            img_path = str(image_input)
            pil_img = Image.open(img_path).convert("RGB")
            img_np = np.array(pil_img)
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
            img_np = np.array(pil_img)
        else:
            img_np = image_input

        blocks: List[OCRTextBlock] = []

        if self.engine is not None:
            try:
                # 1. Primary pass on original image
                ocr_results, _ = self.engine(img_np)
                
                # 2. If text is sparse or faint on plastic wrappers, try enhanced contrast
                if not ocr_results or len(ocr_results) < 8:
                    enhanced_np = self._enhance_packaging_image(img_np)
                    enh_results, _ = self.engine(enhanced_np)
                    if enh_results and len(enh_results) > (len(ocr_results) if ocr_results else 0):
                        ocr_results = enh_results

                if ocr_results:
                    for item in ocr_results:
                        polygon = item[0]
                        text = str(item[1]).strip()
                        confidence = float(item[2])

                        xs = [pt[0] for pt in polygon]
                        ys = [pt[1] for pt in polygon]
                        x_min = float(min(xs))
                        x_max = float(max(xs))
                        y_min = float(min(ys))
                        y_max = float(max(ys))

                        width = max(1.0, x_max - x_min)
                        height = max(1.0, y_max - y_min)

                        height_mm = None
                        if mm_per_pixel and mm_per_pixel > 0:
                            height_mm = round(height * mm_per_pixel, 2)

                        bbox = BoundingBox(
                            x=round(x_min, 1),
                            y=round(y_min, 1),
                            width=round(width, 1),
                            height=round(height, 1),
                            polygon=[[round(float(p[0]), 1), round(float(p[1]), 1)] for p in polygon]
                        )

                        blocks.append(OCRTextBlock(
                            text=text,
                            confidence=round(confidence, 3),
                            bbox=bbox,
                            height_px=round(height, 1),
                            height_mm=height_mm
                        ))
            except Exception as e:
                print(f"[OCR] Error during OCR inference: {e}")

        return blocks
