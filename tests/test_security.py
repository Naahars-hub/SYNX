import io
import time
import unittest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app, mobile_sessions, cleanup_stale_mobile_sessions, RATE_LIMIT_BUCKETS
from app.db.database import init_db, create_user_session, get_user_from_session, list_recent_audits

class TestSecurityMeasures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        # Clear rate limit buckets between tests to avoid cross-test throttling
        RATE_LIMIT_BUCKETS.clear()

    def test_defensive_security_headers(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=(self)", res.headers.get("Permissions-Policy", ""))
        csp = res.headers.get("Content-Security-Policy", "")
        self.assertIn("accounts.google.com", csp)
        self.assertIn("default-src 'self'", csp)

    def test_cors_policy(self):
        # Authorized local origin
        res_allowed = self.client.options(
            "/api/health",
            headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"}
        )
        self.assertEqual(res_allowed.headers.get("Access-Control-Allow-Origin"), "http://localhost:8000")

        # Unauthorized external origin
        res_blocked = self.client.options(
            "/api/health",
            headers={"Origin": "https://attacker-domain.com", "Access-Control-Request-Method": "GET"}
        )
        self.assertNotEqual(res_blocked.headers.get("Access-Control-Allow-Origin"), "https://attacker-domain.com")

    def test_mobile_delete_path_traversal_blocked(self):
        # Create valid session
        sess_res = self.client.post("/api/mobile/session")
        self.assertEqual(sess_res.status_code, 200)
        sid = sess_res.json()["session_id"]

        # Traversal attempt with ../
        traversal_res = self.client.post(f"/api/mobile/delete/{sid}/..%2F..%2Fdata%2Fmetrology_audit.db")
        self.assertIn(traversal_res.status_code, [400, 404])

        # Attempt deleting file not belonging to session
        unauthorized_delete = self.client.post(f"/api/mobile/delete/{sid}/system32_kernel.dll")
        self.assertEqual(unauthorized_delete.status_code, 404)

    def test_reports_and_history_path_traversal_blocked(self):
        # Invalid audit ID format with illegal characters / path traversal attempts
        rep_res = self.client.get("/api/reports/invalid..id!audit")
        self.assertEqual(rep_res.status_code, 400)
        self.assertIn("Invalid audit ID format", rep_res.json()["detail"])

        hist_res = self.client.get("/api/history/invalid..id!audit")
        self.assertEqual(hist_res.status_code, 400)
        self.assertIn("Invalid audit ID format", hist_res.json()["detail"])

        # URL encoded path traversal is blocked by routing / validator
        encoded_rep = self.client.get("/api/reports/..%2F..%2Fdata%2Fmetrology_audit.db")
        self.assertIn(encoded_rep.status_code, [400, 404])

    def test_audit_sample_path_traversal_rejected(self):
        res = self.client.post(
            "/api/audit",
            data={"sample_filenames": "../../app/config.py"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("No valid package image(s) provided", res.json()["detail"])

    def test_csprng_session_tokens(self):
        token1 = create_user_session(user_id=1, duration_days=7)
        token2 = create_user_session(user_id=1, duration_days=7)
        self.assertNotEqual(token1, token2)
        self.assertGreaterEqual(len(token1), 32)
        # Verify valid base64-urlsafe character set
        import re
        self.assertTrue(bool(re.match(r"^[A-Za-z0-9_-]+$", token1)))

    def test_mobile_session_stale_cleanup(self):
        # Insert a stale session (3 hours ago)
        stale_id = "stale_session_test_123"
        three_hours_ago = (datetime.now() - timedelta(hours=3)).isoformat()
        mobile_sessions[stale_id] = {
            "status": "waiting",
            "created_at": three_hours_ago,
            "images": []
        }

        # Insert an active session
        active_id = "active_session_test_456"
        mobile_sessions[active_id] = {
            "status": "waiting",
            "created_at": datetime.now().isoformat(),
            "images": []
        }

        cleanup_stale_mobile_sessions()
        self.assertNotIn(stale_id, mobile_sessions)
        self.assertIn(active_id, mobile_sessions)
        # Clean up
        mobile_sessions.pop(active_id, None)

    def test_history_limit_bounding(self):
        # Verify list_recent_audits accepts arbitrary limits safely
        records = list_recent_audits(limit=999999)
        self.assertIsInstance(records, list)
        records_neg = list_recent_audits(limit=-10)
        self.assertIsInstance(records_neg, list)

    def test_rate_limiting_enforcement(self):
        # Test rate limiting on /api/auth/demo-login
        RATE_LIMIT_BUCKETS.clear()
        
        # Trigger requests up to limit
        hit_429 = False
        for _ in range(65):
            res = self.client.post("/api/auth/demo-login", json={"name": "Rate Limit Test"})
            if res.status_code == 429:
                hit_429 = True
                self.assertIn("Retry-After", res.headers)
                break
        self.assertTrue(hit_429, "Expected 429 Too Many Requests when rate limit is exceeded")

if __name__ == "__main__":
    unittest.main()
