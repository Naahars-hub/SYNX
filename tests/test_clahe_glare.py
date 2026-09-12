import os
import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

from app.ocr.engine import (
    detect_specular_glare,
    apply_clahe_and_glare_reduction,
    process_image_with_glare_reduction,
)
from app.main import app

client = TestClient(app)

class TestClaheGlareReduction(unittest.TestCase):

    def setUp(self):
        self.sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_labels", "real_haldiram_1.jpg")

    def test_synthetic_glare_detection(self):
        """Verify specular glare detection on a synthetic white highlight."""
        # Create 100x100 mid-gray image
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        # Add a 20x20 specular hotspot (white, pure reflection)
        img[40:60, 40:60] = [255, 255, 255]

        glare_pct, mask = detect_specular_glare(img)
        # Hotspot is 400 pixels out of 10000 = 4.0%
        self.assertAlmostEqual(glare_pct, 4.0, places=1)
        self.assertEqual(mask.shape, (100, 100))
        self.assertEqual(np.sum(mask > 0), 400)

    def test_real_package_glare_detection(self):
        """Verify specular glare detection on real Haldiram glossy packaging."""
        if not os.path.exists(self.sample_path):
            self.skipTest(f"Sample file not found at {self.sample_path}")

        img = cv2.imread(self.sample_path)
        self.assertIsNotNone(img)

        glare_pct, mask = detect_specular_glare(img)
        # Haldiram pack has significant specular cellophane glare (~7.25%)
        self.assertGreater(glare_pct, 2.0)
        self.assertLess(glare_pct, 30.0)
        self.assertEqual(mask.shape, img.shape[:2])

    def test_clahe_and_inpainting_output_structure(self):
        """Verify CLAHE equalization and Telea inpainting produce valid uint8 RGB image."""
        if not os.path.exists(self.sample_path):
            self.skipTest("Sample file not found")

        img = cv2.imread(self.sample_path)
        enhanced = apply_clahe_and_glare_reduction(img)

        self.assertIsInstance(enhanced, np.ndarray)
        self.assertEqual(enhanced.dtype, np.uint8)
        self.assertEqual(enhanced.shape, img.shape)

        # Ensure image was modified (glare hot spots softened and local contrast enhanced)
        diff = cv2.absdiff(img, enhanced)
        self.assertGreater(np.mean(diff), 1.0)

    def test_dual_pass_ocr_fusion(self):
        """Verify dual-pass OCR fuses recovered blocks and tags source enhancement correctly."""
        if not os.path.exists(self.sample_path):
            self.skipTest("Sample file not found")

        blocks, clahe_img, glare_pct, recovered_count = process_image_with_glare_reduction(
            self.sample_path,
            mm_per_pixel=0.35
        )

        self.assertIsInstance(blocks, list)
        self.assertGreater(len(blocks), 5)
        self.assertIsInstance(clahe_img, np.ndarray)
        self.assertGreater(glare_pct, 0.0)
        self.assertGreaterEqual(recovered_count, 0)

        # Verify all blocks have valid source_enhancement
        for b in blocks:
            self.assertIn(b.source_enhancement, ("raw", "clahe"))
            self.assertIsNotNone(b.text)
            self.assertGreater(b.confidence, 0.0)

    def test_api_audit_clahe_integration(self):
        """Verify /api/audit endpoint outputs clahe_image_url and glare telemetry."""
        response = client.post(
            "/api/audit",
            data={
                "sample_filenames": "real_haldiram_1.jpg",
                "calibration_mode": "dimensions",
                "package_type": "rectangular_box",
                "package_width_mm": "150",
                "package_height_mm": "220",
                "package_depth_mm": "40"
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check root audit results
        self.assertIn("total_glare_percentage", data)
        self.assertIn("blocks_recovered_by_clahe", data)
        self.assertGreater(data["total_glare_percentage"], 0.0)

        # Check angle-specific results
        self.assertIn("angles", data)
        self.assertGreaterEqual(len(data["angles"]), 1)
        angle = data["angles"][0]

        self.assertTrue(angle.get("clahe_applied"))
        self.assertIsNotNone(angle.get("clahe_image_url"))
        self.assertGreater(angle.get("glare_percentage", 0), 0)

        # Verify the generated CLAHE image is served by the static file endpoint
        clahe_url = angle["clahe_image_url"]
        img_res = client.get(clahe_url)
        self.assertEqual(img_res.status_code, 200)
        self.assertTrue(img_res.headers.get("content-type", "").startswith("image/"))


if __name__ == "__main__":
    unittest.main()
