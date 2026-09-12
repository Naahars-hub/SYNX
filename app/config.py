import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
SAMPLE_DIR = BASE_DIR / "sample_labels"
REPORT_DIR = BASE_DIR / "data" / "reports"
RULES_FILE = APP_DIR / "rules" / "legal_metrology_2011.json"
DATABASE_PATH = BASE_DIR / "data" / "metrology_audit.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# Ensure runtime directories exist
for path in [UPLOAD_DIR, SAMPLE_DIR, REPORT_DIR, STATIC_DIR, DATABASE_PATH.parent]:
    path.mkdir(parents=True, exist_ok=True)

# Default Calibration Constants
DEFAULT_DPI = 96.0  # standard screen / photo estimate when uncalibrated
MM_PER_INCH = 25.4

# Known reference objects (in millimeters)
REFERENCE_OBJECTS = {
    "coin_5rs": {"name": "₹5 Coin (23 mm diameter)", "dimension_mm": 23.0, "type": "diameter"},
    "coin_1rs": {"name": "₹1 Coin (21.93 mm diameter)", "dimension_mm": 21.93, "type": "diameter"},
    "coin_10rs": {"name": "₹10 Coin (27 mm diameter)", "dimension_mm": 27.0, "type": "diameter"},
    "credit_card": {"name": "Standard ID/Card (85.6 mm width)", "dimension_mm": 85.6, "type": "width"},
    "custom": {"name": "Custom Reference", "dimension_mm": 0.0, "type": "custom"},
}

def get_local_ip() -> str:
    """Returns machine's primary local network IP address."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not send actual traffic, just routes to determine local outbound interface
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

