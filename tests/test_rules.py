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
    PDPCalculation
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

if __name__ == "__main__":
    unittest.main()
