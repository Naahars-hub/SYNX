import os
import math
from pathlib import Path
from typing import List, Optional, Union, Tuple, Dict, Any
import numpy as np
from PIL import Image, ImageOps

# Guard against decompression bomb pixel attacks
Image.MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_DIMENSION = 4096

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

    def compute_optical_clarity(self, blocks: List[OCRTextBlock]) -> float:
        """
        Computes the average OCR confidence across all recognized text blocks.
        Returns float between 0.0 and 1.0 (or 1.0 if no blocks detected).
        """
        if not blocks:
            return 1.0
        confs = [b.confidence for b in blocks if b.confidence is not None]
        return round(float(sum(confs) / len(confs)), 3) if confs else 1.0

    def detect_specular_glare(self, img_np: np.ndarray) -> Tuple[float, Optional[np.ndarray]]:
        """
        Detects specular glare hot spots in packaged commodity images using CIE LAB color space.
        Specular reflections on glossy plastic/foil exhibit high luminance (L > 215)
        and very low chroma (chroma < 30).
        Returns (glare_percentage, binary_glare_mask).
        """
        if cv2 is None or img_np is None:
            return 0.0, None

        try:
            lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            chroma = np.sqrt((a.astype(float) - 128) ** 2 + (b.astype(float) - 128) ** 2)
            glare_mask = ((l > 215) & (chroma < 30)).astype(np.uint8) * 255
            total_pixels = glare_mask.size
            glare_pixels = int(np.count_nonzero(glare_mask))
            glare_pct = round(float((glare_pixels / max(total_pixels, 1)) * 100.0), 2)
            return glare_pct, glare_mask
        except Exception as e:
            print(f"[OCR] Glare detection warning: {e}")
            return 0.0, None

    def apply_clahe_and_glare_reduction(
        self, img_np: np.ndarray, clip_limit: float = 3.0, tile_grid_size: Tuple[int, int] = (8, 8)
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Applies OpenCV Contrast Limited Adaptive Histogram Equalization (CLAHE)
        and Telea specular glare attenuation on the luminance channel.
        Equalizes lighting across shadows/highlights and recovers faint inkjet printing.
        """
        telemetry = {
            "clahe_applied": False,
            "glare_percentage": 0.0,
            "glare_detected": False,
            "blocks_recovered": 0
        }

        if cv2 is None or img_np is None:
            return img_np, telemetry

        try:
            lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)

            # 1. Specular Glare Detection
            glare_pct, glare_mask = self.detect_specular_glare(img_np)
            telemetry["glare_percentage"] = glare_pct
            telemetry["glare_detected"] = glare_pct >= 0.3

            # 2. Specular Glare Inpainting / Attenuation
            if glare_mask is not None and np.count_nonzero(glare_mask) > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                dilated_mask = cv2.dilate(glare_mask, kernel, iterations=1)
                l_inpainted = cv2.inpaint(l, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
                l_target = cv2.addWeighted(l, 0.35, l_inpainted, 0.65, 0)
            else:
                l_target = l

            # 3. CLAHE Local Contrast Equalization
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
            l_clahe = clahe.apply(l_target)

            # 4. Reconstruct RGB Image
            enhanced_lab = cv2.merge([l_clahe, a, b])
            enhanced_rgb = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
            telemetry["clahe_applied"] = True

            return enhanced_rgb, telemetry
        except Exception as e:
            print(f"[OCR] CLAHE enhancement warning: {e}")
            return img_np, telemetry

    def _compute_iou(self, bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        """Computes Intersection over Union (IoU) between two bounding boxes."""
        x1 = max(bbox1.x, bbox2.x)
        y1 = max(bbox1.y, bbox2.y)
        x2 = min(bbox1.x + bbox1.width, bbox2.x + bbox2.width)
        y2 = min(bbox1.y + bbox1.height, bbox2.y + bbox2.height)

        inter_w = max(0.0, x2 - x1)
        inter_h = max(0.0, y2 - y1)
        inter_area = inter_w * inter_h

        area1 = bbox1.width * bbox1.height
        area2 = bbox2.width * bbox2.height
        union_area = area1 + area2 - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def _ocr_results_to_blocks(
        self, ocr_results: Any, mm_per_pixel: Optional[float] = None, enhancement: str = "raw"
    ) -> List[OCRTextBlock]:
        """Converts raw RapidOCR results to structured OCRTextBlock objects."""
        blocks: List[OCRTextBlock] = []
        if not ocr_results:
            return blocks

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
                height_mm=height_mm,
                source_enhancement=enhancement
            ))

        return blocks

    def process_image_with_glare_reduction(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        mm_per_pixel: Optional[float] = None
    ) -> Tuple[List[OCRTextBlock], np.ndarray, Dict[str, Any]]:
        """
        Dual-Pass Spatial OCR Fusion with OpenCV CLAHE Glare Reduction:
        1. Normalizes input with EXIF auto-orientation & downscaling
        2. Pass 1: Runs OCR on the raw image
        3. Pass 2: Detects specular glare, attenuates reflections, and applies CLAHE
        4. Spatial Fusion: Merges newly recovered blocks from Pass 2 obscured in Pass 1
        Returns (fused_blocks, enhanced_rgb_np, glare_telemetry).
        """
        # Convert PIL Image or Path to numpy array
        if isinstance(image_input, (str, Path)):
            img_path = str(image_input)
            raw_pil = Image.open(img_path)
            pil_img = ImageOps.exif_transpose(raw_pil)
            if pil_img.width > MAX_IMAGE_DIMENSION or pil_img.height > MAX_IMAGE_DIMENSION:
                pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            pil_img = pil_img.convert("RGB")
            img_np = np.array(pil_img)
        elif isinstance(image_input, Image.Image):
            pil_img = ImageOps.exif_transpose(image_input)
            if pil_img.width > MAX_IMAGE_DIMENSION or pil_img.height > MAX_IMAGE_DIMENSION:
                pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            pil_img = pil_img.convert("RGB")
            img_np = np.array(pil_img)
        else:
            img_np = image_input

        # 1. Apply OpenCV CLAHE & Glare Reduction
        enhanced_np, telemetry = self.apply_clahe_and_glare_reduction(img_np)

        if self.engine is None:
            return [], enhanced_np, telemetry

        try:
            # 2. Pass 1: Raw Image OCR
            raw_results, _ = self.engine(img_np)
            blocks_raw = self._ocr_results_to_blocks(raw_results, mm_per_pixel=mm_per_pixel, enhancement="raw")

            # 3. Pass 2: CLAHE + Anti-Glare Image OCR
            clahe_results, _ = self.engine(enhanced_np)
            blocks_clahe = self._ocr_results_to_blocks(clahe_results, mm_per_pixel=mm_per_pixel, enhancement="clahe")

            # 4. Dual-Pass Spatial Fusion
            # Start with raw blocks, then incorporate non-redundant blocks recovered by CLAHE
            merged_blocks = list(blocks_raw)
            recovered_count = 0

            for cb in blocks_clahe:
                max_iou = 0.0
                best_match = None
                for rb in blocks_raw:
                    iou = self._compute_iou(cb.bbox, rb.bbox)
                    if iou > max_iou:
                        max_iou = iou
                        best_match = rb

                # Recover block if it was missed in raw pass (IoU < 0.35)
                # or if CLAHE pass recognized text with significantly higher confidence
                if max_iou < 0.35:
                    merged_blocks.append(cb)
                    recovered_count += 1
                elif best_match and (cb.confidence - best_match.confidence > 0.20) and len(cb.text) >= len(best_match.text):
                    # Replace with higher clarity CLAHE block
                    idx = merged_blocks.index(best_match)
                    merged_blocks[idx] = cb
                    recovered_count += 1

            telemetry["blocks_recovered"] = recovered_count
            return merged_blocks, enhanced_np, telemetry
        except Exception as e:
            print(f"[OCR] Error during dual-pass OCR inference: {e}")
            return [], enhanced_np, telemetry

    def process_image(
        self, 
        image_input: Union[str, Path, Image.Image, np.ndarray],
        mm_per_pixel: Optional[float] = None
    ) -> List[OCRTextBlock]:
        """
        Standard OCR process method with built-in CLAHE glare reduction (backwards compatible).
        """
        blocks, _, _ = self.process_image_with_glare_reduction(image_input, mm_per_pixel=mm_per_pixel)
        return blocks

# Module-level convenience functions
def detect_specular_glare(img_np: np.ndarray) -> Tuple[float, Optional[np.ndarray]]:
    """Detects specular glare hot spots in packaged commodity images using CIE LAB color space."""
    return OCREngine().detect_specular_glare(img_np)

def apply_clahe_and_glare_reduction(
    img_np: np.ndarray, clip_limit: float = 3.0, tile_grid_size: Tuple[int, int] = (8, 8)
) -> np.ndarray:
    """Applies OpenCV CLAHE and Telea inpainting on specular highlights."""
    enhanced, _ = OCREngine().apply_clahe_and_glare_reduction(img_np, clip_limit, tile_grid_size)
    return enhanced

def process_image_with_glare_reduction(
    image_input: Union[str, Path, Image.Image, np.ndarray],
    mm_per_pixel: Optional[float] = None
) -> Tuple[List[OCRTextBlock], np.ndarray, float, int]:
    """Runs dual-pass spatial fusion OCR with OpenCV CLAHE glare reduction."""
    blocks, enhanced_np, telemetry = OCREngine().process_image_with_glare_reduction(image_input, mm_per_pixel)
    return blocks, enhanced_np, float(telemetry.get("glare_percentage", 0.0)), int(telemetry.get("blocks_recovered", 0))
