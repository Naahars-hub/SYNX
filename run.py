#!/usr/bin/env python3
"""
SYNX - Legal Metrology Compliance Checker
Startup script to launch the FastAPI server and open the browser.
"""

import os
import sys
import webbrowser
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import uvicorn

from app.config import get_local_ip

def main():
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    local_ip = get_local_ip()
    local_url = f"http://127.0.0.1:{port}"
    mobile_url = f"http://{local_ip}:{port}/mobile"

    print("=" * 68)
    print("  SYNX - LEGAL METROLOGY COMPLIANCE CHECKER (SIH 2026)")
    print("  Packaged Commodities Rules, 2011 Automated Verification")
    print(f"  Laptop Dashboard : {local_url}")
    print(f"  Mobile Camera URL: {mobile_url}")
    print("=" * 68)

    # Open browser automatically on PC
    try:
        webbrowser.open(local_url)
    except Exception:
        pass

    uvicorn.run("app.main:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    main()
