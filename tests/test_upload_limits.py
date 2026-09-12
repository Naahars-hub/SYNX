import unittest
import io
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.main import app, MAX_UPLOAD_FILES, MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES

client = TestClient(app)

class TestUploadLimits(unittest.TestCase):

    def _generate_dummy_png(self, size_bytes: int = 100) -> bytes:
        header = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff"
            b"?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        if size_bytes > len(header):
            return header + b"X" * (size_bytes - len(header))
        return header

    def _generate_dummy_pdf(self) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, "Brand: SYNX Snack")
        c.drawString(100, 720, "Net Weight: 250 g")
        c.drawString(100, 690, "MRP: Rs. 99.00 (Incl. of all taxes)")
        c.drawString(100, 660, "Mfg: SYNX Labs Pvt Ltd")
        c.drawString(100, 630, "Customer Care: support@synx.ai")
        c.save()
        buf.seek(0)
        return buf.read()

    def test_exceed_max_files_limit(self):
        """Uploading more than MAX_UPLOAD_FILES (6) must return HTTP 400."""
        dummy_png = self._generate_dummy_png()
        files = [
            ("files", (f"side_{i}.png", dummy_png, "image/png"))
            for i in range(MAX_UPLOAD_FILES + 1)
        ]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Upload limit exceeded", response.json()["detail"])
        self.assertIn(f"Maximum {MAX_UPLOAD_FILES}", response.json()["detail"])

    def test_exceed_file_size_limit(self):
        """Uploading a file larger than MAX_FILE_SIZE_MB (10 MB) must return HTTP 400."""
        oversized_bytes = self._generate_dummy_png(MAX_FILE_SIZE_BYTES + 1024)
        files = [
            ("files", ("large_label.png", oversized_bytes, "image/png"))
        ]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds maximum allowed size", response.json()["detail"])
        self.assertIn(f"{MAX_FILE_SIZE_MB} MB", response.json()["detail"])

    def test_empty_file_rejected(self):
        """Uploading a 0-byte file must return HTTP 400."""
        files = [
            ("files", ("empty.png", b"", "image/png"))
        ]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", response.json()["detail"].lower())

    def test_unsupported_file_extension(self):
        """Uploading an unsupported file format like .exe must return HTTP 400."""
        files = [
            ("files", ("malicious.exe", b"MZ\x90\x00", "application/octet-stream"))
        ]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.json()["detail"])

    def test_mobile_upload_size_limit(self):
        """Mobile upload endpoint must reject oversized files (>10MB)."""
        oversized = self._generate_dummy_png(MAX_FILE_SIZE_BYTES + 512)
        files = {"file": ("snap.jpg", oversized, "image/jpeg")}
        response = client.post("/api/mobile/upload/test_sess_01", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertIn("size limit", response.json()["detail"].lower())

    def test_valid_pdf_document_audit(self):
        """Uploading a valid PDF document within size limits should succeed."""
        pdf_bytes = self._generate_dummy_pdf()
        self.assertLess(len(pdf_bytes), MAX_FILE_SIZE_BYTES)
        files = [
            ("files", ("label_proof.pdf", pdf_bytes, "application/pdf"))
        ]
        data = {
            "calibration_mode": "dimensions",
            "package_type": "rectangular",
            "package_width_mm": "100",
            "package_height_mm": "150",
            "package_depth_mm": "30"
        }
        response = client.post("/api/audit", files=files, data=data)
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertIn("verdict", res)
        self.assertIn("overall_score", res)
        self.assertIn("audit_id", res)

    def test_multipage_pdf_audit(self):
        """Uploading a multi-page PDF must extract and analyze every page into separate angles."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        # Page 1: Front / Commodity
        c.drawString(100, 750, "Brand: SYNX Organic Almonds")
        c.drawString(100, 720, "Net Weight: 500 g")
        c.showPage()
        # Page 2: Back / Price & Dates
        c.drawString(100, 750, "MRP: Rs. 450.00 (Incl. of all taxes)")
        c.drawString(100, 720, "Pkd Date: 01/2026")
        c.drawString(100, 690, "Consumer Care: help@synx.org")
        c.showPage()
        # Page 3: Side / Manufacturer
        c.drawString(100, 750, "Manufactured by: SYNX Foods Pvt Ltd, New Delhi")
        c.drawString(100, 720, "Country of Origin: India")
        c.showPage()
        c.save()
        buf.seek(0)
        pdf_bytes = buf.read()

        files = [
            ("files", ("multipage_packaging.pdf", pdf_bytes, "application/pdf"))
        ]
        data = {
            "calibration_mode": "dimensions",
            "package_type": "rectangular",
            "package_width_mm": "120",
            "package_height_mm": "180",
            "package_depth_mm": "40"
        }
        response = client.post("/api/audit", files=files, data=data)
        self.assertEqual(response.status_code, 200)
        res = response.json()
        angles = res.get("angles", [])
        # Must have extracted all 3 pages as 3 separate angles!
        self.assertEqual(len(angles), 3, "Multi-page PDF must yield 3 angles for 3 pages")
        self.assertEqual(angles[0]["label"], "Angle 1")
        self.assertEqual(angles[1]["label"], "Angle 2")
        self.assertEqual(angles[2]["label"], "Angle 3")
        # Check that extracted fields are unified across pages
        extracted = res.get("extracted_fields", {})
        self.assertTrue(len(extracted) > 0, "Should have extracted fields across all pages")

    def _generate_valid_png(self, width: int = 400, height: int = 400, text_val: str = "Test") -> bytes:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), text_val, fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_micro_resolution_rejected(self):
        """Images smaller than 300x300 must be rejected with HTTP 400."""
        tiny_png = self._generate_valid_png(width=200, height=200)
        files = [("files", ("tiny.png", tiny_png, "image/png"))]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("resolution too low", response.json()["detail"].lower())

    def test_extreme_aspect_ratio_rejected(self):
        """Images with aspect ratio > 10:1 must be rejected with HTTP 400."""
        strip_png = self._generate_valid_png(width=3500, height=320)
        files = [("files", ("strip.png", strip_png, "image/png"))]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("aspect ratio", response.json()["detail"].lower())

    def test_duplicate_image_upload_rejected(self):
        """Uploading two identical images across angles must be caught and rejected with HTTP 400."""
        img_bytes = self._generate_valid_png(width=500, height=500, text_val="Same Photo")
        files = [
            ("files", ("angle1.png", img_bytes, "image/png")),
            ("files", ("angle2.png", img_bytes, "image/png"))
        ]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("duplicate image detected", response.json()["detail"].lower())

    def test_invalid_negative_or_zero_dimension_rejected(self):
        """Zero or negative dimension inputs must be rejected with HTTP 400."""
        img_bytes = self._generate_valid_png(width=500, height=500)
        files = [("files", ("pkg.png", img_bytes, "image/png"))]
        response = client.post(
            "/api/audit",
            files=files,
            data={"package_width_mm": "-10", "package_height_mm": "100"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("strictly positive", response.json()["detail"].lower())

    def test_encrypted_or_corrupt_pdf_rejected(self):
        """Corrupt or encrypted fake PDF must return clean HTTP 400."""
        fake_pdf = b"%PDF-1.7\n%Fake encrypted content\n/Encrypt << >>\ntrailer << >>\n%%EOF"
        files = [("files", ("locked.pdf", fake_pdf, "application/pdf"))]
        response = client.post("/api/audit", files=files, data={"calibration_mode": "dimensions"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("pdf", response.json()["detail"].lower())

if __name__ == "__main__":
    unittest.main()
