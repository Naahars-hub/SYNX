import unittest
from pathlib import Path
from app.config import SAMPLE_DIR, REPORT_DIR
from app.ocr.engine import OCREngine
from app.extractor.parser import EntityParser
from app.rules.engine import RulesEngine
from app.rules.pdp_calculator import compute_pdp_and_font_requirements
from app.extractor.entities import CalibrationData, AuditResult
from app.reporting.pdf_generator import PDFReportGenerator

class TestEndToEndPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ocr = OCREngine()
        cls.parser = EntityParser()
        cls.rules = RulesEngine()
        cls.pdf_gen = PDFReportGenerator()
        cls.sample_path = SAMPLE_DIR / "sample_01_compliant_snack.png"

    def test_pipeline_on_compliant_sample(self):
        self.assertTrue(self.sample_path.exists(), "Sample 01 image should exist")

        calibration = CalibrationData(
            mode="dimensions",
            package_type="rectangular",
            package_width_mm=120.0,
            package_height_mm=180.0
        )

        pdp, mm_per_px = compute_pdp_and_font_requirements(
            calibration=calibration,
            image_width=800,
            image_height=1100
        )
        calibration.mm_per_pixel = mm_per_px

        # OCR
        blocks = self.ocr.process_image(self.sample_path, mm_per_pixel=mm_per_px)
        self.assertGreater(len(blocks), 5, "Should extract text blocks from compliant sample")

        # Entity Extraction
        extracted = self.parser.parse(blocks)
        self.assertIn("net_quantity", extracted)
        self.assertIn("mrp", extracted)

        # Rules Evaluation
        evals, score, verdict, summary = self.rules.evaluate(extracted, pdp, blocks)
        self.assertGreaterEqual(score, 70.0)

        # PDF Report
        audit_res = AuditResult(
            audit_id="TEST-AUDIT-001",
            timestamp="2026-09-11 12:00:00 IST",
            image_hash="abc123hash",
            filename=self.sample_path.name,
            image_url="/sample_labels/sample_01_compliant_snack.png",
            image_width=800,
            image_height=1100,
            calibration=calibration,
            pdp=pdp,
            extracted_fields=extracted,
            all_ocr_blocks=blocks,
            rule_evaluations=evals,
            overall_score=score,
            verdict=verdict,
            summary=summary
        )

        pdf_path = self.pdf_gen.generate_report(audit_res, self.sample_path)
        self.assertTrue(pdf_path.exists(), "Generated PDF report should exist")
        self.assertGreater(pdf_path.stat().st_size, 1000, "PDF should not be empty")

if __name__ == "__main__":
    unittest.main()
