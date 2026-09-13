import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file natively if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k not in os.environ:
                    os.environ[k] = v
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

# Google Authentication & Security Settings
DEFAULT_GOOGLE_CLIENT_ID = "849299945889-dd0m49qgfji94h42ln3un3qcnge88mq5.apps.googleusercontent.com"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID)
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "synx-legal-metrology-auth-key-2026")
SESSION_EXPIRY_DAYS = int(os.environ.get("SESSION_EXPIRY_DAYS", 30))

# Rate Limiting & Resource Protection
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", 60))
MOBILE_SESSION_TTL_HOURS = int(os.environ.get("MOBILE_SESSION_TTL_HOURS", 2))

# CORS Allowed Origins
raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]

# Gemini Vision-Language Model Integration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()



