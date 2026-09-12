import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont

from app.config import SAMPLE_DIR

def get_font(size: int):
    """Attempt to load a clean sans-serif font or fallback to default."""
    try:
        # Standard Windows fonts
        windows_fonts = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\calibri.ttf"
        ]
        for f in windows_fonts:
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
    except Exception:
        pass
    return ImageFont.load_default()

class SyntheticLabelGenerator:
    """
    Generates synthetic packaged commodity labels using Pillow with intentional
    compliance attributes and edge-case violations for pipeline benchmarking.
    """

    def __init__(self, output_dir: Path = SAMPLE_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_samples(self) -> List[Dict[str, Any]]:
        manifest = [
            self.create_sample_01_compliant(),
            self.create_sample_02_missing_mrp(),
            self.create_sample_03_non_standard_unit(),
            self.create_sample_04_font_too_small(),
            self.create_sample_05_missing_consumer_care(),
            self.create_sample_06_malformed_date()
        ]
        return manifest

    def _draw_base_packaging(self, title: str, subtitle: str, color_accent=(20, 90, 160)) -> Tuple[Image.Image, ImageDraw.Draw, int, int]:
        width = 800
        height = 1100
        img = Image.new("RGB", (width, height), color=(250, 250, 252))
        draw = ImageDraw.Draw(img)

        # Outer border
        draw.rectangle([10, 10, width - 10, height - 10], outline=(200, 205, 215), width=3)

        # Brand header banner
        draw.rectangle([20, 20, width - 20, 140], fill=color_accent)
        f_brand = get_font(38)
        f_sub = get_font(20)
        draw.text((40, 35), title, fill=(255, 255, 255), font=f_brand)
        draw.text((42, 90), subtitle, fill=(220, 235, 255), font=f_sub)

        # Declaration Box Panel
        draw.rectangle([30, 160, width - 30, height - 30], outline=(170, 180, 195), fill=(255, 255, 255), width=2)
        
        # Section Header
        f_sec = get_font(18)
        draw.rectangle([30, 160, width - 30, 200], fill=(235, 240, 248))
        draw.text((45, 170), "MANDATORY DECLARATIONS (LEGAL METROLOGY ACT, 2009)", fill=(40, 50, 70), font=f_sec)

        return img, draw, width, height

    def create_sample_01_compliant(self) -> Dict[str, Any]:
        """Fully compliant packaged commodity label."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX PREMIUM SNACKS", "Roasted Almonds & Raisins Mix", color_accent=(16, 120, 80)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)

        # Product
        draw.text((50, 220), "Generic Name: Ready-to-Eat Nut Snack", fill=(10, 10, 10), font=f_med)
        
        # Net Qty (Standard 200 g, nice legible font)
        draw.text((50, 270), "Net Quantity: 200 g", fill=(10, 10, 10), font=f_large)

        # MRP & USP
        draw.text((50, 325), "MRP: Rs. 160.00 (Incl. of all taxes)", fill=(10, 10, 10), font=f_large)
        draw.text((50, 380), "Unit Sale Price: Rs. 0.80 / g", fill=(50, 50, 50), font=f_med)

        # Dates
        draw.text((50, 435), "Mfg Date: 08/2026", fill=(10, 10, 10), font=f_med)
        draw.text((50, 485), "Best Before: 9 months from date of manufacture", fill=(60, 60, 60), font=f_small)

        # Manufacturer
        draw.text((50, 540), "Manufactured & Packed by:", fill=(10, 10, 10), font=f_med)
        draw.text((50, 575), "SYNX Nutrition Foods Private Limited", fill=(40, 40, 40), font=f_small)
        draw.text((50, 605), "Plot No. 42, Sector 8, Industrial Area, Manesar", fill=(40, 40, 40), font=f_small)
        draw.text((50, 635), "Gurugram, Haryana - 122050, India", fill=(40, 40, 40), font=f_small)

        # Origin
        draw.text((50, 690), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        # Consumer Care
        draw.rectangle([45, 740, w - 45, 870], outline=(180, 200, 220), fill=(245, 250, 255), width=1)
        draw.text((55, 755), "Consumer Care / Grievance Redressal:", fill=(20, 60, 110), font=f_med)
        draw.text((55, 790), "Helpline Toll-Free: 1800-202-6000", fill=(40, 40, 40), font=f_small)
        draw.text((55, 825), "Email: care@synxfoods.in | Address: Same as Manufacturer", fill=(40, 40, 40), font=f_small)

        filename = "sample_01_compliant_snack.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 01: Fully Compliant Snack Pack",
            "expected_verdict": "COMPLIANT",
            "description": "All 8 mandatory declarations present, standard units 'g', verified tax inclusivity, valid font size."
        }

    def create_sample_02_missing_mrp(self) -> Dict[str, Any]:
        """Missing MRP & USP violation."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX PREMIUM SNACKS", "Salted Cashew Kernels", color_accent=(180, 60, 20)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)

        draw.text((50, 220), "Generic Name: Roasted Cashew Nuts", fill=(10, 10, 10), font=f_med)
        draw.text((50, 270), "Net Quantity: 250 g", fill=(10, 10, 10), font=f_large)

        # NOTE: MRP is intentionally omitted!
        draw.text((50, 330), "Mfg Date: 09/2026", fill=(10, 10, 10), font=f_med)
        draw.text((50, 380), "Best Before: 6 months from packing", fill=(60, 60, 60), font=f_small)

        draw.text((50, 440), "Manufactured & Packed by:", fill=(10, 10, 10), font=f_med)
        draw.text((50, 475), "SYNX Nutrition Foods Private Limited", fill=(40, 40, 40), font=f_small)
        draw.text((50, 505), "Plot No. 42, Sector 8, Industrial Area, Manesar", fill=(40, 40, 40), font=f_small)
        draw.text((50, 535), "Gurugram, Haryana - 122050, India", fill=(40, 40, 40), font=f_small)

        draw.text((50, 595), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        draw.rectangle([45, 650, w - 45, 780], outline=(180, 200, 220), fill=(245, 250, 255), width=1)
        draw.text((55, 665), "Consumer Care / Grievance Redressal:", fill=(20, 60, 110), font=f_med)
        draw.text((55, 700), "Helpline Toll-Free: 1800-202-6000", fill=(40, 40, 40), font=f_small)
        draw.text((55, 735), "Email: care@synxfoods.in", fill=(40, 40, 40), font=f_small)

        filename = "sample_02_missing_mrp.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 02: Missing MRP & USP",
            "expected_verdict": "NON_COMPLIANT",
            "description": "Critical violation: Maximum Retail Price (MRP) and Unit Sale Price are completely omitted, violating Rule 6(1)(e)."
        }

    def create_sample_03_non_standard_unit(self) -> Dict[str, Any]:
        """Non-standard unit 'gms' instead of standard 'g'."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX ORGANIC ATTA", "Whole Wheat Flour", color_accent=(140, 90, 20)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)

        draw.text((50, 220), "Generic Name: Whole Wheat Flour", fill=(10, 10, 10), font=f_med)
        
        # VIOLATION: '500 gms' instead of standard '500 g'
        draw.text((50, 270), "Net Weight: 500 gms", fill=(10, 10, 10), font=f_large)

        draw.text((50, 325), "MRP: Rs. 55.00 (Incl. of all taxes)", fill=(10, 10, 10), font=f_large)
        draw.text((50, 380), "Mfg Date: 08/2026", fill=(10, 10, 10), font=f_med)
        draw.text((50, 430), "Best Before: 4 months from packing", fill=(60, 60, 60), font=f_small)

        draw.text((50, 490), "Manufactured & Packed by:", fill=(10, 10, 10), font=f_med)
        draw.text((50, 525), "SYNX Agro Mills Ltd, G.T. Road, Karnal - 132001, India", fill=(40, 40, 40), font=f_small)

        draw.text((50, 580), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        draw.rectangle([45, 635, w - 45, 765], outline=(180, 200, 220), fill=(245, 250, 255), width=1)
        draw.text((55, 650), "Consumer Care:", fill=(20, 60, 110), font=f_med)
        draw.text((55, 685), "Phone: 1800-444-2222", fill=(40, 40, 40), font=f_small)
        draw.text((55, 720), "Email: contact@synxmills.com", fill=(40, 40, 40), font=f_small)

        filename = "sample_03_non_standard_unit.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 03: Illegal Non-Standard Unit ('gms')",
            "expected_verdict": "NON_COMPLIANT",
            "description": "Violates Rule 9 & 13 by printing non-standard unit symbol 'gms' instead of statutory metric symbol 'g'."
        }

    def create_sample_04_font_too_small(self) -> Dict[str, Any]:
        """Undersized font for Net Quantity on large PDP."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX DETERGENT", "Advanced Clean Laundry Powder", color_accent=(50, 70, 150)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)
        f_tiny = get_font(11)  # Deliberately tiny font (under 1.5mm)

        draw.text((50, 220), "Commodity: Laundry Detergent Powder", fill=(10, 10, 10), font=f_med)
        
        # VIOLATION: Net quantity printed in tiny font
        draw.text((50, 270), "Net Quantity: 1 kg", fill=(80, 80, 80), font=f_tiny)

        draw.text((50, 310), "MRP: Rs. 140.00 (Incl. of all taxes)", fill=(10, 10, 10), font=f_large)
        draw.text((50, 365), "Mfg Date: 07/2026", fill=(10, 10, 10), font=f_med)

        draw.text((50, 420), "Manufactured by: SYNX Chemicals India Ltd", fill=(40, 40, 40), font=f_small)
        draw.text((50, 450), "GIDC Estate, Vadodara, Gujarat - 390010", fill=(40, 40, 40), font=f_small)
        draw.text((50, 500), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        draw.rectangle([45, 550, w - 45, 680], outline=(180, 200, 220), fill=(245, 250, 255), width=1)
        draw.text((55, 565), "Customer Grievance Redressal:", fill=(20, 60, 110), font=f_med)
        draw.text((55, 600), "Phone: 1800-888-9999", fill=(40, 40, 40), font=f_small)
        draw.text((55, 635), "Email: support@synxchem.com", fill=(40, 40, 40), font=f_small)

        filename = "sample_04_font_too_small.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 04: Font Size Below Statutory Limit",
            "expected_verdict": "NON_COMPLIANT",
            "description": "Violates Rule 7(1) Table 1: Net quantity numeral printed in undersized font (< 2.0 mm required for PDP area > 100 cm²)."
        }

    def create_sample_05_missing_consumer_care(self) -> Dict[str, Any]:
        """Missing consumer care contact information."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX HERBAL SHAMPOO", "Anti-Dandruff Scalp Therapy", color_accent=(100, 40, 120)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)

        draw.text((50, 220), "Generic Name: Hair Shampoo", fill=(10, 10, 10), font=f_med)
        draw.text((50, 270), "Net Quantity: 200 ml", fill=(10, 10, 10), font=f_large)
        draw.text((50, 325), "MRP: Rs. 199.00 (Incl. of all taxes)", fill=(10, 10, 10), font=f_large)
        draw.text((50, 380), "Mfg Date: 09/2026", fill=(10, 10, 10), font=f_med)
        draw.text((50, 435), "Best Before: 24 months from mfg", fill=(60, 60, 60), font=f_small)

        draw.text((50, 490), "Manufactured by: SYNX Personal Care Ltd", fill=(40, 40, 40), font=f_small)
        draw.text((50, 520), "Baddi Industrial Area, Solan, H.P. - 173205", fill=(40, 40, 40), font=f_small)
        draw.text((50, 570), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        # NOTE: Consumer care section is completely missing!

        filename = "sample_05_missing_consumer_care.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 05: Missing Consumer Care Details",
            "expected_verdict": "NON_COMPLIANT",
            "description": "Violates Rule 6(1)(f): Consumer care telephone helpline and email address are completely absent."
        }

    def create_sample_06_malformed_date(self) -> Dict[str, Any]:
        """Missing or malformed manufacturing date."""
        img, draw, w, h = self._draw_base_packaging(
            "SYNX SPARKLING SODA", "Natural Flavored Beverage", color_accent=(10, 110, 140)
        )
        f_large = get_font(28)
        f_med = get_font(22)
        f_small = get_font(18)

        draw.text((50, 220), "Generic Name: Carbonated Beverage", fill=(10, 10, 10), font=f_med)
        draw.text((50, 270), "Net Content: 300 ml", fill=(10, 10, 10), font=f_large)
        draw.text((50, 325), "MRP: Rs. 35.00 (Incl. of all taxes)", fill=(10, 10, 10), font=f_large)
        
        # NOTE: Manufacturing date is omitted!
        draw.text((50, 385), "Best Before: Consume within 6 months", fill=(60, 60, 60), font=f_small)

        draw.text((50, 440), "Packed by: SYNX Beverages India", fill=(40, 40, 40), font=f_small)
        draw.text((50, 470), "KIADB Tech Park, Bengaluru, Karnataka - 560066", fill=(40, 40, 40), font=f_small)
        draw.text((50, 520), "Country of Origin: India", fill=(10, 10, 10), font=f_med)

        draw.rectangle([45, 570, w - 45, 700], outline=(180, 200, 220), fill=(245, 250, 255), width=1)
        draw.text((55, 585), "Consumer Care:", fill=(20, 60, 110), font=f_med)
        draw.text((55, 620), "Phone: 1800-111-3333", fill=(40, 40, 40), font=f_small)
        draw.text((55, 655), "Email: queries@synxbeverages.com", fill=(40, 40, 40), font=f_small)

        filename = "sample_06_malformed_date.png"
        path = self.output_dir / filename
        img.save(path)
        return {
            "filename": filename,
            "title": "Sample 06: Missing Manufacturing Date",
            "expected_verdict": "NON_COMPLIANT",
            "description": "Violates Rule 6(1)(d): Month and year of manufacture/packing omitted."
        }

if __name__ == "__main__":
    generator = SyntheticLabelGenerator()
    manifest = generator.generate_all_samples()
    print(f"Generated {len(manifest)} benchmark synthetic labels in {SAMPLE_DIR}")
