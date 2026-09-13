import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from app.extractor.entities import OCRTextBlock, BoundingBox
from app.extractor.parser import EntityParser
from app.extractor.gemini_extractor import is_gemini_available, extract_commodity_with_gemini

class TestGeminiAndSalience(unittest.TestCase):

    def setUp(self):
        self.parser = EntityParser()

    def test_visual_salience_rejects_marketing_buzzwords(self):
        """Test that single buzzwords like 'BLEND' or '100% PURE' are NOT picked over real product names."""
        blocks = [
            OCRTextBlock(
                text="BLEND",
                confidence=0.99,
                bbox=BoundingBox(x=10, y=10, width=80, height=40),
                height_px=40.0,
                height_mm=4.0
            ),
            OCRTextBlock(
                text="PREMIUM DARK ROAST",
                confidence=0.95,
                bbox=BoundingBox(x=10, y=60, width=150, height=30),
                height_px=30.0,
                height_mm=3.0
            ),
            OCRTextBlock(
                text="INSTANT COFFEE POWDER",
                confidence=0.94,
                bbox=BoundingBox(x=10, y=100, width=200, height=35),
                height_px=35.0,
                height_mm=3.5
            ),
            OCRTextBlock(
                text="MRP Rs. 250.00",
                confidence=0.95,
                bbox=BoundingBox(x=10, y=150, width=100, height=20),
                height_px=20.0,
                height_mm=2.0
            )
        ]

        extracted = self.parser.parse(blocks)
        self.assertIn("commodity_name", extracted)
        self.assertNotEqual(extracted["commodity_name"].parsed_value.upper(), "BLEND")
        # Should pick the statutory commodity phrase or coherent product title
        self.assertIn("COFFEE", extracted["commodity_name"].parsed_value.upper())

    def test_statutory_declaration_lookahead(self):
        """Test 'Generic Name:' followed by next-line lookahead."""
        blocks = [
            OCRTextBlock(
                text="Generic Name:",
                confidence=0.95,
                bbox=BoundingBox(x=10, y=10, width=90, height=20),
                height_px=15.0,
                height_mm=1.5
            ),
            OCRTextBlock(
                text="Vacuum Insulated Stainless Steel Bottle",
                confidence=0.96,
                bbox=BoundingBox(x=10, y=35, width=250, height=25),
                height_px=18.0,
                height_mm=1.8
            )
        ]

        extracted = self.parser.parse(blocks)
        self.assertIn("commodity_name", extracted)
        self.assertEqual(
            extracted["commodity_name"].parsed_value,
            "Vacuum Insulated Stainless Steel Bottle"
        )

    def test_gemini_unavailable_graceful_fallback(self):
        """When Gemini is not configured, parsing still succeeds with zero errors."""
        blocks = [
            OCRTextBlock(
                text="Potato Chips",
                confidence=0.92,
                bbox=BoundingBox(x=10, y=10, width=120, height=30),
                height_px=30.0,
                height_mm=3.0
            )
        ]
        # Should not throw any exception even if image_path is passed
        extracted = self.parser.parse(blocks, image_path="non_existent_image.jpg")
        self.assertIn("commodity_name", extracted)
        self.assertEqual(extracted["commodity_name"].parsed_value, "Potato Chips")

    @patch("app.extractor.parser.is_gemini_available", return_value=True)
    @patch("app.extractor.parser.extract_commodity_with_gemini")
    def test_gemini_multimodal_used_when_available(self, mock_gemini, mock_is_avail):
        """When Gemini is available, multimodal generic commodity is prioritized."""
        mock_gemini.return_value = {
            "commodity_name": "Vacuum Insulated Stainless Steel Bottle",
            "brand_name": "Milton",
            "variant": "Hydra 1000",
            "confidence": 0.98,
            "source": "gemini-1.5-flash multimodal"
        }

        blocks = [
            OCRTextBlock(
                text="MILTON HYDRA",
                confidence=0.95,
                bbox=BoundingBox(x=20, y=20, width=100, height=40),
                height_px=40.0,
                height_mm=4.0
            ),
            OCRTextBlock(
                text="COLD FOR 24 HOURS",
                confidence=0.90,
                bbox=BoundingBox(x=20, y=70, width=150, height=25),
                height_px=25.0,
                height_mm=2.5
            )
        ]

        extracted = self.parser.parse(blocks, image_path=Path("dummy.jpg"))
        self.assertIn("commodity_name", extracted)
        self.assertEqual(
            extracted["commodity_name"].parsed_value,
            "Vacuum Insulated Stainless Steel Bottle"
        )
        self.assertEqual(extracted["commodity_name"].confidence, 0.98)


if __name__ == "__main__":
    unittest.main()
