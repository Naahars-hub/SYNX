import unittest
import uuid
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime

from app.config import DATABASE_PATH
from app.extractor.entities import (
    AuditResult, CalibrationData, PDPCalculation, ExtractedField, BoundingBox, RuleEvaluation
)
from app.db.database import (
    init_db,
    save_audit_record,
    get_audit_by_id,
    list_recent_audits,
    get_manufacturer_offence_count,
    get_system_analytics
)

class TestDatabase(unittest.TestCase):

    def setUp(self):
        init_db()

    def tearDown(self):
        if hasattr(self, "audit_id"):
            with sqlite3.connect(str(DATABASE_PATH)) as conn:
                conn.execute("DELETE FROM audit_evaluations WHERE audit_id = ?;", (self.audit_id,))
                conn.execute("DELETE FROM inspections WHERE audit_id = ?;", (self.audit_id,))
                conn.commit()

    def test_save_and_retrieve_audit(self):
        self.audit_id = f"test_{uuid.uuid4().hex[:8]}"
        audit_id = self.audit_id
        audit = AuditResult(
            audit_id=audit_id,
            timestamp=datetime.now().isoformat(),
            image_hash="abc123sha256",
            filename="test_product.jpg",
            image_url="/uploads/test_product.jpg",
            image_width=1000,
            image_height=1500,
            calibration=CalibrationData(mm_per_pixel=0.15, method="dimensions", confidence=1.0),
            pdp=PDPCalculation(
                package_type="rectangular",
                dimensions_mm={"width": 120.0, "height": 180.0, "depth": 40.0},
                pdp_area_sqcm=180.0,
                required_min_font_height_mm=2.0,
                calculation_formula="W * H"
            ),
            extracted_fields={
                "commodity_name": ExtractedField(
                    field_type="commodity_name",
                    label="Commodity Name",
                    raw_text="Wheat Flour Atta",
                    parsed_value="Wheat Flour Atta",
                    confidence=0.98,
                    bbox=BoundingBox(x=10, y=20, width=200, height=40)
                ),
                "manufacturer": ExtractedField(
                    field_type="manufacturer",
                    label="Manufacturer",
                    raw_text="Hindustan Foods Ltd, Mumbai 400001",
                    parsed_value="Hindustan Foods Ltd",
                    confidence=0.95,
                    bbox=BoundingBox(x=10, y=80, width=300, height=50)
                )
            },
            all_ocr_blocks=[],
            rule_evaluations=[
                RuleEvaluation(
                    rule_id="RULE_6_1_B",
                    clause="Rule 6(1)(b)",
                    title="Commodity Name",
                    field_target="commodity_name",
                    status="PASS",
                    severity="HIGH",
                    message="Valid commodity name detected.",
                    measured_value="Wheat Flour Atta",
                    expected_value="Declared name",
                    statutory_ref="Rule 6(1)(b)"
                ),
                RuleEvaluation(
                    rule_id="RULE_6_1_C",
                    clause="Rule 6(1)(c)",
                    title="Net Quantity",
                    field_target="net_quantity",
                    status="FAIL",
                    severity="CRITICAL",
                    message="Net quantity is missing.",
                    measured_value="Not Detected",
                    expected_value="Standard net quantity",
                    penalty_risk="Fine up to ₹25,000",
                    statutory_ref="Rule 6(1)(c)"
                )
            ],
            overall_score=75.0,
            verdict="NON_COMPLIANT",
            summary={"passed": 1, "warnings": 0, "failed": 1},
            angles=[]
        )

        res = save_audit_record(audit, image_sha256="abc123sha256", pdf_filename="test.pdf")
        self.assertEqual(res["audit_id"], audit_id)

        # Retrieve from DB
        retrieved = get_audit_by_id(audit_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["audit_id"], audit_id)
        self.assertEqual(retrieved["commodity_name"], "Wheat Flour Atta")
        self.assertEqual(retrieved["manufacturer"], "Hindustan Foods Ltd, Mumbai 400001")
        self.assertEqual(retrieved["verdict"], "NON_COMPLIANT")
        self.assertEqual(retrieved["overall_score"], 75.0)

        # Search list
        recent = list_recent_audits(limit=10, search="Hindustan Foods")
        found = any(r["audit_id"] == audit_id for r in recent)
        self.assertTrue(found)

        # Offense count for Hindustan Foods should be at least 1
        offences = get_manufacturer_offence_count("Hindustan Foods")
        self.assertGreaterEqual(offences, 1)

        # System analytics
        analytics = get_system_analytics()
        self.assertIn("total_inspections", analytics)
        self.assertIn("compliance_rate_percent", analytics)
        self.assertGreaterEqual(analytics["total_inspections"], 1)

    def test_check_db_health(self):
        from app.db.database import check_db_health
        health = check_db_health()
        self.assertEqual(health["status"], "connected")
        self.assertEqual(health["engine"], "SQLite3")
        self.assertGreaterEqual(health["inspections_count"], 0)
        self.assertGreaterEqual(health["users_count"], 0)

if __name__ == "__main__":
    unittest.main()
