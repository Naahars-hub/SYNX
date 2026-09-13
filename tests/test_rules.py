import unittest
from app.rules.pdp_calculator import (
    calculate_pdp_area,
    get_rule_7_min_font_height,
    compute_pdp_and_font_requirements
)
from app.rules.engine import RulesEngine
from app.extractor.entities import (
    CalibrationData,
    ExtractedField,
    BoundingBox,
    PDPCalculation,
    OCRTextBlock
)

class TestLegalMetrologyRules(unittest.TestCase):

    def setUp(self):
        self.engine = RulesEngine()

    def test_pdp_calculation_rectangular(self):
        # 120mm x 180mm package -> 21600 mm² = 216 cm²
        area, formula = calculate_pdp_area("rectangular", width_mm=120.0, height_mm=180.0)
        self.assertEqual(area, 216.0)
        self.assertIn("Width", formula)

    def test_pdp_calculation_cylindrical(self):
        # Cylindrical: 40% of height x pi x diameter
        # Height: 100mm, Diameter: 50mm
        # Area = 0.40 * 100 * 3.14159 * 50 = 6283.18 mm² = 62.83 cm²
        area, formula = calculate_pdp_area("cylindrical", width_mm=50.0, height_mm=100.0)
        self.assertAlmostEqual(area, 62.83, places=1)
        self.assertIn("0.40", formula)

    def test_rule_7_font_height_thresholds(self):
        # PDP <= 50 cm² -> 1.0 mm
        self.assertEqual(get_rule_7_min_font_height(pdp_area_sqcm=30.0), 1.0)

        # 50 < PDP <= 100 cm² -> 1.5 mm
        self.assertEqual(get_rule_7_min_font_height(pdp_area_sqcm=75.0), 1.5)

        # 100 < PDP <= 500 cm² -> 2.0 mm
        self.assertEqual(get_rule_7_min_font_height(pdp_area_sqcm=250.0), 2.0)

        # 500 < PDP <= 2500 cm² -> 4.0 mm
        self.assertEqual(get_rule_7_min_font_height(pdp_area_sqcm=800.0), 4.0)

        # Net quantity > 1 kg -> requires at least 4.0 mm or 6.0 mm depending on quantity
        self.assertEqual(get_rule_7_min_font_height(pdp_area_sqcm=200.0, net_quantity_g_or_ml=1500), 6.0)

    def test_non_standard_unit_violation(self):
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 120, "height": 180, "depth": 40},
            pdp_area_sqcm=216.0,
            calculation_formula="W x H",
            required_min_font_height_mm=2.0
        )

        extracted = {
            "net_quantity": ExtractedField(
                field_type="net_quantity",
                label="Net Quantity",
                raw_text="Net Weight: 500 gms",
                parsed_value=500,
                unit="gms",  # Illegal unit under Rule 9 & 13
                font_height_mm=2.5
            )
        }

        evals, score, verdict, summary = self.engine.evaluate(extracted, pdp, [])
        unit_eval = next((e for e in evals if e.rule_id == "RULE_9_13_UNITS"), None)
        self.assertIsNotNone(unit_eval)
        self.assertEqual(unit_eval.status, "FAIL")
        self.assertIn("'gms' used", unit_eval.message)
        self.assertIn("g", unit_eval.expected_value)

    def test_undersized_font_violation(self):
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 120, "height": 180, "depth": 40},
            pdp_area_sqcm=216.0,
            calculation_formula="W x H",
            required_min_font_height_mm=2.0  # Requires >= 2.0 mm
        )

        extracted = {
            "net_quantity": ExtractedField(
                field_type="net_quantity",
                label="Net Quantity",
                raw_text="Net Quantity: 200 g",
                parsed_value=200,
                unit="g",
                font_height_mm=1.1  # Violation! Only 1.1 mm
            )
        }

        evals, score, verdict, summary = self.engine.evaluate(extracted, pdp, [])
        font_eval = next((e for e in evals if e.rule_id == "RULE_7_FONT_HEIGHT"), None)
        self.assertIsNotNone(font_eval)
        self.assertEqual(font_eval.status, "FAIL")
        self.assertIn("below the minimum required", font_eval.message)

    def test_rule_26_small_package_exemption(self):
        """Packages <= 10g or <= 10ml should be exempt from mfg date and USP under Rule 26(a)."""
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 30, "height": 40, "depth": 10},
            pdp_area_sqcm=12.0,
            calculation_formula="W x H",
            required_min_font_height_mm=1.0
        )
        extracted = {
            "net_quantity": ExtractedField(
                field_type="net_quantity",
                label="Net Quantity",
                raw_text="Net Wt: 5 g",
                parsed_value=5.0,
                unit="g",
                font_height_mm=0.8
            ),
            "mrp": ExtractedField(
                field_type="mrp",
                label="MRP",
                raw_text="MRP Rs. 5 (incl. of all taxes)",
                parsed_value={"amount": 5.0, "inclusive_of_all_taxes": True}
            )
        }
        evals, score, verdict, summary = self.engine.evaluate(extracted, pdp, [])
        date_eval = next((e for e in evals if e.field_target == "mfg_date"), None)
        self.assertIsNotNone(date_eval)
        self.assertEqual(date_eval.status, "PASS")
        self.assertIn("Exempt under Rule 26(a)", date_eval.message)
        self.assertIn("Rule 26(a) Small Package Exemption (≤ 10g/ml)", summary.get("exemptions", []))

    def test_rule_3_bulk_package_tag(self):
        """Packages > 25 kg/L should be tagged with Rule 3 bulk package exemption."""
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 400, "height": 600, "depth": 200},
            pdp_area_sqcm=2400.0,
            calculation_formula="W x H",
            required_min_font_height_mm=4.0
        )
        extracted = {
            "net_quantity": ExtractedField(
                field_type="net_quantity",
                label="Net Quantity",
                raw_text="Net Weight: 50 kg",
                parsed_value=50.0,
                unit="kg"
            )
        }
        evals, score, verdict, summary = self.engine.evaluate(extracted, pdp, [])
        bulk_eval = next((e for e in evals if e.rule_id == "RULE_3_BULK_EXEMPTION"), None)
        self.assertIsNotNone(bulk_eval)
        self.assertEqual(bulk_eval.status, "INFO")
        self.assertIn("Rule 3", bulk_eval.message)

    def test_dual_mrp_conflict_violation(self):
        """Conflicting MRP declarations across package angles must trigger CRITICAL failure."""
        from app.extractor.entities import ImageAngleResult
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 100, "height": 100, "depth": 20},
            pdp_area_sqcm=100.0,
            calculation_formula="W x H",
            required_min_font_height_mm=1.5
        )
        ang1 = ImageAngleResult(
            angle_id=1, label="Angle 1", filename="a1.png", image_url="", image_width=500, image_height=500,
            extracted_fields={"mrp": ExtractedField(field_type="mrp", label="MRP", raw_text="MRP Rs. 100", parsed_value={"amount": 100.0, "inclusive_of_all_taxes": True})}
        )
        ang2 = ImageAngleResult(
            angle_id=2, label="Angle 2", filename="a2.png", image_url="", image_width=500, image_height=500,
            extracted_fields={"mrp": ExtractedField(field_type="mrp", label="MRP", raw_text="MRP Rs. 120", parsed_value={"amount": 120.0, "inclusive_of_all_taxes": True})}
        )
        evals, score, verdict, summary = self.engine.evaluate({}, pdp, [], angles=[ang1, ang2])
        dual_mrp_eval = next((e for e in evals if e.rule_id == "RULE_6_1_E_DUAL_MRP"), None)
        self.assertIsNotNone(dual_mrp_eval)
        self.assertEqual(dual_mrp_eval.status, "FAIL")
        self.assertEqual(dual_mrp_eval.severity, "CRITICAL")
        self.assertIn("Dual MRP violation", dual_mrp_eval.message)

    def test_low_optical_clarity_warning(self):
        """OCR blocks with average confidence below 50% must emit an optical clarity warning."""
        from app.extractor.entities import OCRTextBlock, BoundingBox
        pdp = PDPCalculation(
            package_type="rectangular",
            dimensions_mm={"width": 100, "height": 100, "depth": 20},
            pdp_area_sqcm=100.0,
            calculation_formula="W x H",
            required_min_font_height_mm=1.5
        )
        low_conf_blocks = [
            OCRTextBlock(text="fuzzy text", confidence=0.32, bbox=BoundingBox(x=10, y=10, width=50, height=20), height_px=20),
            OCRTextBlock(text="blurry text", confidence=0.40, bbox=BoundingBox(x=10, y=40, width=50, height=20), height_px=20)
        ]
        evals, score, verdict, summary = self.engine.evaluate({}, pdp, low_conf_blocks)
        clarity_eval = next((e for e in evals if e.rule_id == "OPTICAL_CLARITY_WARNING"), None)
        self.assertIsNotNone(clarity_eval)
        self.assertEqual(clarity_eval.status, "WARNING")
        self.assertIn("Low optical clarity", clarity_eval.message)

    def test_mrp_usp_dot_matrix_noise_cleaning(self):
        """Dot-matrix OCR text with noise characters (e.g. MRPT125/-USP70.36/包!) must produce clean MRP and USP."""
        from app.extractor.parser import EntityParser
        parser = EntityParser()
        block = OCRTextBlock(
            text="MRPT125/-USP70.36/包!",
            confidence=0.88,
            bbox=BoundingBox(x=10, y=10, width=120, height=25),
            height_px=22
        )
        fields = parser.parse([block])
        self.assertIn("mrp", fields)
        self.assertIn("unit_sale_price", fields)

        mrp_fld = fields["mrp"]
        self.assertEqual(mrp_fld.parsed_value["amount"], 125.0)
        self.assertNotIn("包", mrp_fld.raw_text)
        self.assertNotIn("USP", mrp_fld.raw_text)

        usp_fld = fields["unit_sale_price"]
        self.assertEqual(usp_fld.parsed_value["amount"], 0.36)
        self.assertNotIn("包", usp_fld.raw_text)
        self.assertNotIn("MRPT", usp_fld.raw_text)

    def test_consumer_care_tollfree_and_multiblock_usp_extraction(self):
        """Real-world packaged food OCR (e.g. Lay's Magic Masala) must properly extract phone, USP, and pincode."""
        from app.extractor.parser import EntityParser
        parser = EntityParser()

        blocks = [
            OCRTextBlock(text="UNIT SALE PRICE:", confidence=0.97, bbox=BoundingBox(x=10, y=10, width=100, height=20), height_px=18),
            OCRTextBlock(text="Rs. 0.561- FER g", confidence=0.96, bbox=BoundingBox(x=10, y=35, width=100, height=20), height_px=18),
            OCRTextBlock(text="PEPSICO INDIA HOLDINGS PVT.LTD", confidence=0.91, bbox=BoundingBox(x=10, y=60, width=200, height=20), height_px=18),
            OCRTextBlock(text="GURUGRAM122002,HARYANA,INDIA", confidence=0.80, bbox=BoundingBox(x=10, y=85, width=200, height=20), height_px=18),
            OCRTextBlock(text="OR CALL US AT 180022 4020", confidence=0.91, bbox=BoundingBox(x=10, y=110, width=200, height=20), height_px=18),
            OCRTextBlock(text="CONSUMER.FEEDBACK@PEPSICO.COM", confidence=0.99, bbox=BoundingBox(x=10, y=135, width=200, height=20), height_px=18),
            OCRTextBlock(text="30/08/26 & 2701127", confidence=0.91, bbox=BoundingBox(x=10, y=160, width=150, height=20), height_px=18),
            OCRTextBlock(text="2.2/N43008280", confidence=0.93, bbox=BoundingBox(x=10, y=185, width=150, height=20), height_px=18),
        ]

        fields = parser.parse(blocks)

        # 1. Unit Sale Price
        self.assertIn("unit_sale_price", fields)
        self.assertEqual(fields["unit_sale_price"].parsed_value["amount"], 0.56)
        self.assertEqual(fields["unit_sale_price"].parsed_value["unit"], "g")
        self.assertIn("0.56", fields["unit_sale_price"].raw_text)

        # 2. Consumer Care
        self.assertIn("consumer_care", fields)
        self.assertEqual(fields["consumer_care"].parsed_value["phone"], "180022 4020")
        self.assertIn("CONSUMER.FEEDBACK@PEPSICO.COM", fields["consumer_care"].parsed_value["email"])
        self.assertTrue(fields["consumer_care"].parsed_value["has_both"])

        # 3. Manufacturer PIN Code
        self.assertIn("manufacturer", fields)
        self.assertTrue(fields["manufacturer"].parsed_value["has_pincode"])

        # 4. Mfg Date (Not batch number)
        self.assertIn("mfg_date", fields)
        self.assertEqual(fields["mfg_date"].parsed_value, "30/08/2026")

if __name__ == "__main__":
    unittest.main()

