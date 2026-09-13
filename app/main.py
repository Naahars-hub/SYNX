import io
import os
import re
import time
import uuid
import secrets
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
from PIL import Image, ImageOps

# Decompression bomb and image geometry guards
Image.MAX_IMAGE_PIXELS = 50_000_000

from app.config import (
    BASE_DIR, UPLOAD_DIR, SAMPLE_DIR, REPORT_DIR, STATIC_DIR, RULES_FILE, DATABASE_PATH, get_local_ip,
    GOOGLE_CLIENT_ID, SESSION_EXPIRY_DAYS, RATE_LIMIT_PER_MINUTE, MOBILE_SESSION_TTL_HOURS, ALLOWED_ORIGINS
)
from app.extractor.entities import (
    CalibrationData, AuditResult, ExtractedField, OCRTextBlock
)
from app.ocr.engine import OCREngine
from app.extractor.parser import EntityParser
from app.rules.engine import RulesEngine
from app.rules.pdp_calculator import compute_pdp_and_font_requirements
from app.reporting.pdf_generator import PDFReportGenerator
from app.dataset.synthetic_generator import SyntheticLabelGenerator
from app.db import (
    init_db,
    save_audit_record,
    get_audit_by_id,
    list_recent_audits,
    get_manufacturer_offence_count,
    get_system_analytics,
    get_or_create_google_user,
    create_user_session,
    get_user_from_session,
    revoke_session,
    get_user_by_id,
    count_inspector_audits,
    is_inspector_role,
    list_all_users,
    update_user_role,
    check_db_health
)

app = FastAPI(
    title="Legal Metrology Compliance Checker - SYNX",
    description="Automated Packaged Commodities Rules 2011 Compliance Verification Engine (SIH 2026)",
    version="1.0.0"
)

from fastapi.middleware.cors import CORSMiddleware

# Security: CORS configuration restricted to localhost, private LAN IPs, and online tunnel/cloud domains
cors_regex = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|.*\.trycloudflare\.com|.*\.onrender\.com)(:\d+)?$"
local_ip = get_local_ip()
explicit_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    f"http://{local_ip}:8000",
    f"http://{local_ip}:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
] + ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=explicit_origins,
    allow_origin_regex=cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory sliding-window rate limiter
RATE_LIMIT_BUCKETS = defaultdict(list)

def check_rate_limit(client_ip: str, endpoint: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
    """Sliding-window rate limiter to prevent DoS attacks and resource exhaustion."""
    now = time.time()
    key = f"{client_ip}:{endpoint}"
    timestamps = RATE_LIMIT_BUCKETS[key]
    cutoff = now - window_seconds
    # Prune expired timestamps
    valid_timestamps = [t for t in timestamps if t > cutoff]
    if len(valid_timestamps) >= max_requests:
        RATE_LIMIT_BUCKETS[key] = valid_timestamps
        return False
    valid_timestamps.append(now)
    RATE_LIMIT_BUCKETS[key] = valid_timestamps
    return True

@app.middleware("http")
async def security_headers_and_rate_limit_middleware(request: Request, call_next):
    """
    Applies defensive HTTP security headers and rate limits heavy endpoints.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    path = request.url.path

    # Rate limiting on heavy / write endpoints
    rate_limited_paths = ("/api/audit", "/api/auth/google", "/api/auth/demo-login")
    if path in rate_limited_paths or path.startswith("/api/mobile/upload"):
        if not check_rate_limit(client_ip, path, max_requests=RATE_LIMIT_PER_MINUTE, window_seconds=60):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Rate limit exceeded, please retry in a moment."},
                headers={"Retry-After": "60"}
            )

    response = await call_next(request)

    # Inject OWASP recommended security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"

    # Content-Security-Policy: permits Google Identity Services (GIS), fonts, and styles
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/client https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://accounts.google.com/gsi/style; "
        "img-src 'self' data: blob: https://*.googleusercontent.com https://accounts.google.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "frame-src 'self' https://accounts.google.com; "
        "connect-src 'self' https://accounts.google.com; "
        "object-src 'none'; "
        "base-uri 'self';"
    )

    return response

def sanitize_filename(filename: str) -> str:
    """
    Strips directory traversal sequences, null bytes, and path separators,
    returning only the secure base filename.
    """
    if not filename:
        return "file"
    clean = filename.replace("\x00", "")
    base = os.path.basename(clean.replace("\\", "/"))
    base = re.sub(r"^\.+", "", base)
    return base or "file"

def is_safe_path(target_path: Path, base_dir: Path) -> bool:
    """Verifies target path resides strictly within the designated base directory."""
    try:
        return target_path.resolve().is_relative_to(base_dir.resolve())
    except Exception:
        return False

# Mount static folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/sample_labels", StaticFiles(directory=str(SAMPLE_DIR)), name="sample_labels")

# Ingestion Boundaries, Upload Limits & Allowed Formats
MAX_UPLOAD_FILES = 6
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".pdf"}

MIN_IMAGE_DIMENSION = 300
MAX_IMAGE_DIMENSION = 4096
MAX_ASPECT_RATIO = 10.0
MIN_PACKAGE_DIM_MM = 5.0
MAX_PACKAGE_DIM_MM = 2500.0

# Engine singletons
ocr_engine = OCREngine()
entity_parser = EntityParser()
rules_engine = RulesEngine()
pdf_generator = PDFReportGenerator()

# Cache of recent audits in-memory (backed permanently by SQLite database)
audit_cache = {}

def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

@app.on_event("startup")
async def startup_event():
    # Initialize Relational SQL Database
    init_db()
    print(f"[Startup] Relational SQL Database initialized at {DATABASE_PATH}")

    # Verify or generate synthetic samples if not present
    if not list(SAMPLE_DIR.glob("*.png")):
        gen = SyntheticLabelGenerator(SAMPLE_DIR)
        gen.generate_all_samples()
        print("[Startup] Generated synthetic benchmark labels.")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Legal Metrology Compliance Checker</h1><p>UI loading...</p>")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    response = HTMLResponse(content)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/health")
async def health_check():
    db_info = check_db_health()
    is_healthy = db_info.get("status") == "connected"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "system": "SYNX Legal Metrology Compliance Engine",
        "ocr_loaded": ocr_engine.engine is not None,
        "database": db_info,
        "timestamp": datetime.now().isoformat()
    }

# ==========================================
# 🔐 Google Authentication & Inspector Identity
# ==========================================

class GoogleAuthRequest(BaseModel):
    credential: str
    client_id: Optional[str] = None

class DemoAuthRequest(BaseModel):
    name: Optional[str] = "Inspector Rajesh Sharma"
    email: Optional[str] = "rajesh.sharma@legalmetrology.gov.in"
    role: Optional[str] = "Senior Legal Metrology Officer"
    department: Optional[str] = "Legal Metrology Enforcement Division"

@app.get("/api/auth/config")
async def get_auth_config():
    """Returns Google OAuth Client configuration for frontend GIS button."""
    return {
        "status": "success",
        "google_client_id": GOOGLE_CLIENT_ID,
        "has_client_id": bool(GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith("demo")),
        "demo_enabled": True
    }

@app.post("/api/auth/google")
async def authenticate_google(body: GoogleAuthRequest):
    """
    Authenticates a user via Google Identity Services (GIS) ID Token.
    Verifies the JWT token using Google's official tokeninfo endpoint.
    """
    if not body.credential:
        raise HTTPException(status_code=400, detail="Missing Google credential token.")

    token = body.credential.strip()
    google_user_info = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
            if resp.status_code == 200:
                google_user_info = resp.json()
    except Exception as e:
        print(f"[Auth] Token verification network error: {e}")

    if not google_user_info or "email" not in google_user_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Google credential. Please sign in again."
        )

    # 1. Validate Issuer
    iss = google_user_info.get("iss", "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(
            status_code=401,
            detail=f"Untrusted token issuer '{iss}'. Token must be issued by Google."
        )

    # 2. Validate Email Verification
    email_verified = google_user_info.get("email_verified")
    if email_verified not in (True, "true", "True", 1):
        raise HTTPException(
            status_code=401,
            detail="Google account email is not verified. Please verify your email with Google before signing in."
        )

    # 3. Validate Token Expiry
    if "exp" in google_user_info:
        try:
            if int(google_user_info["exp"]) < int(time.time()):
                raise HTTPException(
                    status_code=401,
                    detail="Google credential token has expired. Please sign in again."
                )
        except (ValueError, TypeError):
            pass

    # 4. Validate Audience (Client ID)
    if GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith("demo"):
        aud = google_user_info.get("aud")
        if aud != GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=401,
                detail=f"Google credential token audience mismatch. Expected authorized client ID."
            )

    google_id = google_user_info.get("sub", "")
    email = google_user_info.get("email", "")
    name = google_user_info.get("name") or email.split("@")[0].title()
    picture = google_user_info.get("picture", "")

    user = get_or_create_google_user(
        google_id=google_id,
        email=email,
        name=name,
        picture=picture,
        role=None,
        department="Legal Metrology Enforcement Division"
    )

    session_token = create_user_session(user["id"], duration_days=SESSION_EXPIRY_DAYS)

    return {
        "status": "success",
        "message": f"Welcome, {user['name']}.",
        "token": session_token,
        "user": user
    }

@app.post("/api/auth/demo-login")
async def demo_inspector_login(body: Optional[DemoAuthRequest] = None):
    """
    1-click instant login as a verified Legal Metrology Enforcement Officer.
    Enables testing and evaluation when Google Cloud credentials are not configured.
    """
    data = body or DemoAuthRequest()
    name = data.name or "Inspector Rajesh Sharma"
    email = data.email or "rajesh.sharma@legalmetrology.gov.in"
    role = data.role or "Senior Legal Metrology Officer"
    dept = data.department or "Legal Metrology Enforcement Division"
    demo_id = f"demo_{email.split('@')[0]}"

    user = get_or_create_google_user(
        google_id=demo_id,
        email=email,
        name=name,
        picture="",
        role=role,
        department=dept
    )

    session_token = create_user_session(user["id"], duration_days=SESSION_EXPIRY_DAYS)

    return {
        "status": "success",
        "message": f"Signed in as {name}.",
        "token": session_token,
        "user": user
    }

@app.get("/api/auth/me")
async def get_current_user_profile(
    request: Request,
    token: Optional[str] = None
):
    """Returns currently authenticated user profile from bearer token or query parameter."""
    auth_header = request.headers.get("Authorization", "")
    session_token = token
    if auth_header.startswith("Bearer "):
        session_token = auth_header.replace("Bearer ", "").strip()

    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication token required.")

    user = get_user_from_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

    return {
        "status": "success",
        "user": user
    }

@app.post("/api/auth/logout")
async def logout_user(request: Request, token: Optional[str] = None):
    """Terminates active session."""
    auth_header = request.headers.get("Authorization", "")
    session_token = token
    if auth_header.startswith("Bearer "):
        session_token = auth_header.replace("Bearer ", "").strip()

    if session_token:
        revoke_session(session_token)

    return {
        "status": "success",
        "message": "Logged out successfully."
    }

class UpdateRoleRequest(BaseModel):
    role: str

@app.get("/api/users")
async def get_all_users(request: Request):
    """
    Returns directory of registered officers for role management.
    Requires authenticated officer session.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication token required.")
    token = auth_header.replace("Bearer ", "").strip()
    current_user = get_user_from_session(token)
    if not current_user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")

    users = list_all_users()
    return {"status": "success", "users": users}

@app.post("/api/users/{user_id}/role")
async def assign_user_role(user_id: int, body: UpdateRoleRequest, request: Request):
    """
    Assigns or updates an officer's statutory role.
    Protected by RBAC: Only authorized Inspectors can promote or assign roles.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication token required.")
    token = auth_header.replace("Bearer ", "").strip()
    current_user = get_user_from_session(token)
    if not current_user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")

    if not is_inspector_role(current_user.get("role", "")):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: Only authorized Legal Metrology Inspectors can assign officer roles."
        )

    valid_roles = [
        "Legal Metrology Inspector",
        "Senior Legal Metrology Officer",
        "Field Officer",
        "Auditor"
    ]
    new_role = body.role.strip()
    if new_role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{new_role}'. Must be one of: {', '.join(valid_roles)}."
        )

    updated = update_user_role(user_id, new_role)
    if not updated:
        raise HTTPException(status_code=404, detail="Officer record not found.")

    return {
        "status": "success",
        "message": f"Successfully assigned role '{new_role}' to {updated['name']}.",
        "user": updated
    }

# Mobile camera companion sessions
mobile_sessions = {}

@app.get("/mobile", response_class=HTMLResponse)
async def serve_mobile():
    mobile_path = STATIC_DIR / "mobile.html"
    if not mobile_path.exists():
        return HTMLResponse("<h1>Mobile companion loading...</h1>")
    with open(mobile_path, "r", encoding="utf-8") as f:
        content = f.read()
    response = HTMLResponse(content)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def cleanup_stale_mobile_sessions():
    """Prunes mobile sessions older than MOBILE_SESSION_TTL_HOURS to prevent memory leaks."""
    now = datetime.now()
    max_age_seconds = MOBILE_SESSION_TTL_HOURS * 3600
    stale_keys = []
    for sid, sdata in mobile_sessions.items():
        created_str = sdata.get("created_at")
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str)
                if (now - created_dt).total_seconds() > max_age_seconds:
                    stale_keys.append(sid)
            except Exception:
                pass
    for sid in stale_keys:
        mobile_sessions.pop(sid, None)

@app.post("/api/mobile/session")
async def create_mobile_session():
    cleanup_stale_mobile_sessions()
    session_id = secrets.token_hex(8)
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", 8000))
    mobile_url = f"http://{local_ip}:{port}/mobile?session={session_id}"
    localhost_url = f"http://localhost:{port}/mobile?session={session_id}"
    mobile_sessions[session_id] = {
        "status": "waiting",
        "created_at": datetime.now().isoformat(),
        "images": []
    }
    return {
        "session_id": session_id,
        "local_ip": local_ip,
        "port": port,
        "mobile_url": mobile_url,
        "localhost_url": localhost_url
    }

@app.post("/api/mobile/upload/{session_id}")
async def upload_from_mobile(session_id: str, file: UploadFile = File(...)):
    if session_id not in mobile_sessions:
        mobile_sessions[session_id] = {"status": "waiting", "images": []}

    if len(mobile_sessions[session_id]["images"]) >= MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload limit reached: Maximum {MAX_UPLOAD_FILES} images allowed per session."
        )

    orig_name = file.filename or "mobile_photo.jpg"
    ext = Path(orig_name).suffix.lower()

    # Automatically resolve mobile camera captures missing extensions (e.g. 'blob' or 'image')
    if not ext or ext not in ALLOWED_EXTENSIONS:
        ct = (file.content_type or "").lower()
        if "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
        elif "png" in ct:
            ext = ".png"
        elif "webp" in ct:
            ext = ".webp"
        elif "heic" in ct or "heif" in ct:
            ext = ".jpg"  # Will convert to JPEG
        elif not ext:
            ext = ".jpg"

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed formats: JPG, PNG, WEBP, BMP, TIFF, PDF."
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        size_mb = len(contents) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds size limit: {size_mb:.1f} MB uploaded, max allowed is {MAX_FILE_SIZE_MB} MB."
        )

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    try:
        with Image.open(io.BytesIO(contents)) as pil_img:
            # Auto-orient based on mobile camera EXIF orientation tag
            pil_img = ImageOps.exif_transpose(pil_img)
            w, h = pil_img.size

            if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image resolution too low ({w}×{h} px). Minimum {MIN_IMAGE_DIMENSION}×{MIN_IMAGE_DIMENSION} px required for statutory font measurement."
                )

            aspect = max(w, h) / max(min(w, h), 1)
            if aspect > MAX_ASPECT_RATIO:
                raise HTTPException(
                    status_code=400,
                    detail=f"Extreme aspect ratio detected ({aspect:.1f}:1). Maximum supported aspect ratio is {int(MAX_ASPECT_RATIO)}:1. Please upload standard crop."
                )

            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

            safe_stem = Path(orig_name).stem or "photo"
            safe_stem = "".join(c for c in safe_stem if c.isalnum() or c in ("-", "_"))[:16]
            clean_ext = ".jpg" if ext in [".jpg", ".jpeg", ".heic", ".heif"] else ext
            unique_name = f"mobile_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}_{safe_stem}{clean_ext}"
            img_path = UPLOAD_DIR / unique_name
            pil_img.convert("RGB").save(img_path, "JPEG" if clean_ext in [".jpg", ".jpeg"] else "PNG")
    except HTTPException:
        raise
    except Exception as ie:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {str(ie)}")

    image_url = f"/uploads/{unique_name}"
    item = {"filename": unique_name, "image_url": image_url}
    mobile_sessions[session_id]["images"].append(item)
    mobile_sessions[session_id]["status"] = "has_images"

    return {
        "status": "success",
        "count": len(mobile_sessions[session_id]["images"]),
        "images": mobile_sessions[session_id]["images"],
        "latest": item
    }

@app.post("/api/mobile/submit/{session_id}")
async def submit_mobile_session(session_id: str):
    sess = mobile_sessions.get(session_id)
    if not sess or not sess.get("images"):
        raise HTTPException(status_code=400, detail="No photos uploaded yet.")
    sess["status"] = "ready"
    return {"status": "success", "count": len(sess["images"])}

@app.get("/api/mobile/poll/{session_id}")
async def poll_mobile_session(session_id: str):
    sess = mobile_sessions.get(session_id)
    if not sess:
        return {"status": "not_found"}
    if sess.get("status") == "ready":
        data = {
            "status": "ready",
            "images": sess["images"],
            "filenames": [img["filename"] for img in sess["images"]],
            "image_url": sess["images"][0]["image_url"] if sess["images"] else ""
        }
        sess["status"] = "consumed"
        return data
    return {
        "status": sess.get("status", "waiting"),
        "uploaded_count": len(sess.get("images", [])),
        "images": sess.get("images", [])
    }

@app.delete("/api/mobile/image/{session_id}/{filename}")
@app.post("/api/mobile/delete/{session_id}/{filename}")
async def delete_mobile_image(session_id: str, filename: str):
    """
    Deletes a captured angle image from active mobile session and disk.
    Enforces strict path traversal defenses and session ownership verification.
    """
    # 1. Path traversal guard
    if ".." in filename or "/" in filename or "\\" in filename or "\x00" in filename:
        raise HTTPException(status_code=400, detail="Path traversal security violation: Invalid filename.")

    clean_name = sanitize_filename(filename)
    if clean_name != filename:
        raise HTTPException(status_code=400, detail="Invalid characters detected in filename.")

    sess = mobile_sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Mobile session not found.")

    # 2. Session ownership check: File MUST belong to this session
    session_images = sess.get("images", [])
    matching_img = next((img for img in session_images if img.get("filename") == clean_name), None)
    if not matching_img:
        raise HTTPException(status_code=404, detail="File does not exist or does not belong to this mobile session.")

    # 3. Path boundary verification
    target_file = UPLOAD_DIR / clean_name
    if not is_safe_path(target_file, UPLOAD_DIR):
        raise HTTPException(status_code=400, detail="Path traversal security violation.")

    # Remove from session state
    sess["images"] = [img for img in session_images if img.get("filename") != clean_name]

    # Safely delete from filesystem
    if target_file.exists():
        try:
            target_file.unlink()
        except Exception as e:
            print(f"[Mobile] Notice deleting {clean_name}: {e}")

    sess["status"] = "has_images" if sess["images"] else "waiting"

    return {
        "status": "success",
        "deleted": clean_name,
        "remaining_count": len(sess["images"]),
        "images": sess["images"]
    }

@app.get("/api/samples")
async def list_samples():
    """Returns manifest of synthetic benchmark and real product labels for 1-click test runs."""
    gen = SyntheticLabelGenerator(SAMPLE_DIR)
    samples = gen.generate_all_samples()
    for s in samples:
        s["image_url"] = f"/sample_labels/{s['filename']}"

    # Also list downloaded real FMCG product samples
    real_manifest = [
        {
            "filename": "real_haldiram_snack.jpg",
            "title": "Real Product: Haldiram Namkeen",
            "description": "Actual back panel photo of Haldiram snack with FSSAI & declaration panel."
        },
        {
            "filename": "real_lays_chips.jpg",
            "title": "Real Product: Lay's Potato Chips",
            "description": "Actual package photo with ingredients, manufacturer, and barcode."
        },
        {
            "filename": "real_haldiram_1.jpg",
            "title": "Real Product: Haldiram Pouch",
            "description": "Actual pouch photo with FSSAI & nutrition table."
        }
    ]
    for r in real_manifest:
        if (SAMPLE_DIR / r["filename"]).exists():
            r["image_url"] = f"/sample_labels/{r['filename']}"
            samples.append(r)

    return samples

@app.get("/api/rules")
async def get_rules():
    """Returns current active JSON rulebook."""
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.put("/api/rules")
async def update_rules(payload: dict):
    """Updates active JSON rulebook without server restart."""
    try:
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        rules_engine.reload_rules()
        return {"status": "success", "message": "Rulebook updated and hot-reloaded successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update rules: {str(e)}")

@app.post("/api/audit", response_model=AuditResult)
async def audit_image(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    sample_filename: Optional[str] = Form(None),
    sample_filenames: Optional[str] = Form(None),
    calibration_mode: str = Form("dimensions"),
    package_type: str = Form("rectangular"),
    package_width_mm: float = Form(120.0),
    package_height_mm: float = Form(180.0),
    package_depth_mm: float = Form(40.0),
    reference_object_id: Optional[str] = Form(None),
    reference_pixel_size: Optional[float] = Form(None),
    request: Request = None,
):
    """
    Main compliance verification pipeline (Supports single or multi-angle photos):
    1. Ingest 1 or more images from different package sides/angles
    2. Physical calibration & PDP computation
    3. Spatial OCR & entity extraction per angle
    4. Unified multi-angle aggregation across all declarations
    5. Deterministic rule validation against Legal Metrology Rules, 2011
    6. PDF report generation with all angle thumbnails
    """
    # Boundary check package dimensions
    if package_width_mm is not None and package_width_mm <= 0:
        raise HTTPException(status_code=400, detail="Invalid package dimensions: Width must be strictly positive (minimum 5 mm).")
    if package_height_mm is not None and package_height_mm <= 0:
        raise HTTPException(status_code=400, detail="Invalid package dimensions: Height must be strictly positive (minimum 5 mm).")
    if package_depth_mm is not None and package_depth_mm < 0:
        raise HTTPException(status_code=400, detail="Invalid package dimensions: Depth cannot be negative.")
    if package_type.lower() == "cylindrical":
        if (package_width_mm is not None and package_width_mm <= 0) or (package_height_mm is not None and package_height_mm <= 0):
            raise HTTPException(status_code=400, detail="Cylindrical package requires valid positive diameter and height (minimum 5 mm).")

    audit_id = f"AUD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Collect all image sources: List of (img_path, filename, image_url)
    image_sources = []

    # 1. Check multiple uploaded files
    upload_list = [f for f in (files or ([file] if file else [])) if f and f.filename]
    if len(upload_list) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload limit exceeded: Maximum {MAX_UPLOAD_FILES} images/documents allowed per audit. Received {len(upload_list)}."
        )

    for f in upload_list:
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{ext}' for file '{f.filename}'. Allowed formats: JPG, PNG, WEBP, BMP, TIFF, PDF."
            )

        contents = await f.read()
        if len(contents) > MAX_FILE_SIZE_BYTES:
            size_mb = len(contents) / (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"File '{f.filename}' ({size_mb:.1f} MB) exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB."
            )

        if len(contents) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file '{f.filename}' is empty (0 bytes)."
            )

        if ext == ".pdf":
            try:
                import pypdfium2 as pdfium
                try:
                    pdf = pdfium.PdfDocument(contents)
                except Exception as pe:
                    err_msg = str(pe).lower()
                    if "password" in err_msg or "encrypt" in err_msg or "unauthorized" in err_msg:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Password-protected or encrypted PDF detected for '{f.filename}'. Please upload an unlocked PDF."
                        )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Password-protected or invalid PDF document '{f.filename}'. Please upload an unlocked PDF."
                    )

                num_pages = len(pdf)
                if num_pages == 0:
                    raise HTTPException(status_code=400, detail=f"PDF document '{f.filename}' contains no pages.")

                # Save original PDF file for records
                pdf_fn = f"{audit_id}_{f.filename}"
                with open(UPLOAD_DIR / pdf_fn, "wb") as pf:
                    pf.write(contents)

                extracted_from_pdf = []

                if num_pages > 1:
                    # Multi-page PDF: render each page as an angle/panel
                    for p_idx in range(min(num_pages, MAX_UPLOAD_FILES)):
                        page = pdf[p_idx]
                        # Render at scale 2.0 (~144-200 DPI) for high-resolution OCR
                        pil_img = page.render(scale=2.0).to_pil()
                        pil_img = ImageOps.exif_transpose(pil_img)
                        if pil_img.width > MAX_IMAGE_DIMENSION or pil_img.height > MAX_IMAGE_DIMENSION:
                            pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

                        w, h = pil_img.size
                        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Image resolution too low ({w}×{h} px) in page {p_idx + 1} of '{f.filename}'. Minimum {MIN_IMAGE_DIMENSION}×{MIN_IMAGE_DIMENSION} px required for statutory font measurement."
                            )
                        aspect = max(w, h) / max(min(w, h), 1)
                        if aspect > MAX_ASPECT_RATIO:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Extreme aspect ratio detected ({aspect:.1f}:1) in page {p_idx + 1} of '{f.filename}'. Maximum supported aspect ratio is {int(MAX_ASPECT_RATIO)}:1."
                            )

                        img_fn = f"{audit_id}_{Path(f.filename).stem}_p{p_idx + 1}.png"
                        img_path = UPLOAD_DIR / img_fn
                        pil_img.convert("RGB").save(img_path, "PNG")
                        extracted_from_pdf.append((img_path, img_fn, f"/uploads/{img_fn}"))
                else:
                    # Single-page PDF: check if it contains multiple embedded images
                    page = pdf[0]
                    embedded_imgs = []
                    for obj in page.get_objects():
                        if isinstance(obj, pdfium.PdfImage):
                            try:
                                bmp = obj.get_bitmap()
                                e_img = bmp.to_pil()
                                if e_img.width >= MIN_IMAGE_DIMENSION and e_img.height >= MIN_IMAGE_DIMENSION:
                                    embedded_imgs.append(e_img)
                            except Exception:
                                pass

                    if len(embedded_imgs) > 1:
                        # Multiple images embedded on this single page
                        for i_idx, e_img in enumerate(embedded_imgs[:MAX_UPLOAD_FILES]):
                            e_img = ImageOps.exif_transpose(e_img)
                            if e_img.width > MAX_IMAGE_DIMENSION or e_img.height > MAX_IMAGE_DIMENSION:
                                e_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                            w, h = e_img.size
                            aspect = max(w, h) / max(min(w, h), 1)
                            if aspect > MAX_ASPECT_RATIO:
                                continue
                            img_fn = f"{audit_id}_{Path(f.filename).stem}_img{i_idx + 1}.png"
                            img_path = UPLOAD_DIR / img_fn
                            e_img.convert("RGB").save(img_path, "PNG")
                            extracted_from_pdf.append((img_path, img_fn, f"/uploads/{img_fn}"))

                    if not extracted_from_pdf:
                        # Standard single-page document
                        pil_img = page.render(scale=2.0).to_pil()
                        pil_img = ImageOps.exif_transpose(pil_img)
                        if pil_img.width > MAX_IMAGE_DIMENSION or pil_img.height > MAX_IMAGE_DIMENSION:
                            pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                        w, h = pil_img.size
                        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Image resolution too low ({w}×{h} px) for '{f.filename}'. Minimum {MIN_IMAGE_DIMENSION}×{MIN_IMAGE_DIMENSION} px required for statutory font measurement."
                            )
                        aspect = max(w, h) / max(min(w, h), 1)
                        if aspect > MAX_ASPECT_RATIO:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Extreme aspect ratio detected ({aspect:.1f}:1) for '{f.filename}'. Maximum supported aspect ratio is {int(MAX_ASPECT_RATIO)}:1."
                            )

                        img_fn = f"{audit_id}_{Path(f.filename).stem}_p1.png"
                        img_path = UPLOAD_DIR / img_fn
                        pil_img.convert("RGB").save(img_path, "PNG")
                        extracted_from_pdf.append((img_path, img_fn, f"/uploads/{img_fn}"))

                # Append up to MAX_UPLOAD_FILES
                remaining_slots = MAX_UPLOAD_FILES - len(image_sources)
                image_sources.extend(extracted_from_pdf[:remaining_slots])
            except HTTPException:
                raise
            except Exception as pe:
                raise HTTPException(status_code=400, detail=f"Failed to process PDF document '{f.filename}': {str(pe)}")
        else:
            try:
                with Image.open(io.BytesIO(contents)) as pil_img:
                    pil_img = ImageOps.exif_transpose(pil_img)
                    w, h = pil_img.size

                    # Micro-resolution guard
                    if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Image resolution too low ({w}×{h} px) for '{f.filename}'. Minimum {MIN_IMAGE_DIMENSION}×{MIN_IMAGE_DIMENSION} px required for statutory font measurement."
                        )

                    # Extreme aspect ratio guard
                    aspect = max(w, h) / max(min(w, h), 1)
                    if aspect > MAX_ASPECT_RATIO:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Extreme aspect ratio detected ({aspect:.1f}:1) for '{f.filename}'. Maximum supported aspect ratio is {int(MAX_ASPECT_RATIO)}:1. Please upload standard crop."
                        )

                    # Decompression bomb downscaling
                    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                        pil_img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

                    fn = f"{audit_id}_{f.filename}"
                    ip = UPLOAD_DIR / fn
                    pil_img.convert("RGB").save(ip, "JPEG" if ext in [".jpg", ".jpeg"] else "PNG")
                    image_sources.append((ip, fn, f"/uploads/{fn}"))
            except HTTPException:
                raise
            except Exception as ie:
                raise HTTPException(status_code=400, detail=f"Invalid image file '{f.filename}': {str(ie)}")

    # 2. Check sample filenames (could be comma-separated or single)
    s_names = []
    if sample_filenames:
        s_names.extend([s.strip() for s in sample_filenames.split(",") if s.strip()])
    if sample_filename and sample_filename not in s_names:
        s_names.append(sample_filename.strip())

    for s_name in s_names:
        clean_s = sanitize_filename(s_name)
        target_up = UPLOAD_DIR / clean_s
        target_sp = SAMPLE_DIR / clean_s
        if target_up.exists() and is_safe_path(target_up, UPLOAD_DIR):
            image_sources.append((target_up, clean_s, f"/uploads/{clean_s}"))
        elif target_sp.exists() and is_safe_path(target_sp, SAMPLE_DIR):
            image_sources.append((target_sp, clean_s, f"/sample_labels/{clean_s}"))

    if not image_sources:
        raise HTTPException(status_code=400, detail="No valid package image(s) provided.")

    # 3. Duplicate Angle Detection across uploaded images
    if len(image_sources) > 1:
        seen_hashes = {}
        for idx, (img_p, fn, i_url) in enumerate(image_sources):
            h = compute_file_sha256(img_p)
            if h in seen_hashes:
                prev_idx = seen_hashes[h]
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate image detected: Angle {idx + 1} and Angle {prev_idx + 1} are identical. Please upload distinct package sides."
                )
            seen_hashes[h] = idx

    # Primary image (Angle 1) for primary dimensions & hash
    prim_path, prim_fn, prim_url = image_sources[0]
    with Image.open(prim_path) as pil_img:
        img_w, img_h = pil_img.size
    img_hash = compute_file_sha256(prim_path)

    # 1. Calibration & PDP
    calibration = CalibrationData(
        mode=calibration_mode,
        package_type=package_type,
        package_width_mm=package_width_mm,
        package_height_mm=package_height_mm,
        package_depth_mm=package_depth_mm,
        reference_object_id=reference_object_id,
        reference_pixel_size=reference_pixel_size
    )

    pdp, mm_per_px = compute_pdp_and_font_requirements(
        calibration=calibration,
        image_width=img_w,
        image_height=img_h
    )
    calibration.mm_per_pixel = mm_per_px

    # 2. Multi-Angle Spatial OCR & Entity Extraction with OpenCV CLAHE Glare Reduction
    from app.extractor.entities import ImageAngleResult

    angles: List[ImageAngleResult] = []
    unified_extracted_fields: Dict[str, ExtractedField] = {}
    combined_blocks: List[OCRTextBlock] = []
    total_glare_pct = 0.0
    total_clahe_recovered = 0

    for idx, (img_p, fn, i_url) in enumerate(image_sources):
        with Image.open(img_p) as p_img:
            w, h = p_img.size

        # Run dual-pass OCR with OpenCV CLAHE local contrast & specular glare inpainting
        blocks, enhanced_np, glare_meta = ocr_engine.process_image_with_glare_reduction(img_p, mm_per_pixel=mm_per_px)
        
        # Save preprocessed CLAHE image to uploads for live UI toggle inspection
        clahe_fn = f"{audit_id}_angle{idx + 1}_clahe.jpg"
        clahe_path = UPLOAD_DIR / clahe_fn
        try:
            clahe_pil = Image.fromarray(enhanced_np)
            clahe_pil.save(clahe_path, "JPEG", quality=92)
            clahe_url = f"/uploads/{clahe_fn}"
        except Exception as ce:
            print(f"[Main] Warning saving CLAHE image: {ce}")
            clahe_url = i_url

        fields = entity_parser.parse(blocks, image_path=img_p)

        label = f"Angle {idx + 1}"
        for k, fld in fields.items():
            fld.source_angle = label

        glare_pct = float(glare_meta.get("glare_percentage", 0.0))
        recovered = int(glare_meta.get("blocks_recovered", 0))
        total_glare_pct += glare_pct
        total_clahe_recovered += recovered

        angles.append(ImageAngleResult(
            angle_id=idx + 1,
            label=label,
            filename=fn,
            image_url=i_url,
            image_width=w,
            image_height=h,
            ocr_blocks=blocks,
            extracted_fields=fields,
            clahe_image_url=clahe_url,
            glare_percentage=glare_pct,
            clahe_applied=bool(glare_meta.get("clahe_applied", True)),
            blocks_recovered_by_clahe=recovered
        ))

        combined_blocks.extend(blocks)

        # Merge into unified extracted fields across angles
        for k, fld in fields.items():
            if k not in unified_extracted_fields:
                unified_extracted_fields[k] = fld
            else:
                existing = unified_extracted_fields[k]
                if k == "consumer_care":
                    ex_val = existing.parsed_value if isinstance(existing.parsed_value, dict) else {}
                    new_val = fld.parsed_value if isinstance(fld.parsed_value, dict) else {}
                    if new_val.get("has_both") and not ex_val.get("has_both"):
                        unified_extracted_fields[k] = fld
                elif k == "manufacturer":
                    ex_val = existing.parsed_value if isinstance(existing.parsed_value, dict) else {}
                    new_val = fld.parsed_value if isinstance(fld.parsed_value, dict) else {}
                    if new_val.get("has_pincode") and not ex_val.get("has_pincode"):
                        unified_extracted_fields[k] = fld
                elif fld.confidence > existing.confidence:
                    unified_extracted_fields[k] = fld

    # Re-evaluate PDP with unified net quantity if available
    net_qty_obj = unified_extracted_fields.get("net_quantity")
    if net_qty_obj and isinstance(net_qty_obj.parsed_value, (int, float)):
        pdp, _ = compute_pdp_and_font_requirements(
            calibration=calibration,
            image_width=img_w,
            image_height=img_h,
            net_quantity_g_ml=float(net_qty_obj.parsed_value)
        )

    # 3. Unified Rules Validation across all aggregated angles with Dual MRP and Exemptions
    evaluations, score, verdict, summary = rules_engine.evaluate(
        extracted_fields=unified_extracted_fields,
        pdp=pdp,
        all_blocks=combined_blocks,
        angles=angles
    )

    avg_glare_pct = round(total_glare_pct / max(len(angles), 1), 2)
    summary["clahe_applied"] = True
    summary["glare_percentage"] = avg_glare_pct
    summary["blocks_recovered_by_clahe"] = total_clahe_recovered

    # Construct AuditResult
    audit_res = AuditResult(
        audit_id=audit_id,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        image_hash=img_hash,
        filename=prim_fn,
        image_url=prim_url,
        image_width=img_w,
        image_height=img_h,
        calibration=calibration,
        pdp=pdp,
        extracted_fields=unified_extracted_fields,
        all_ocr_blocks=angles[0].ocr_blocks if angles else [],
        rule_evaluations=evaluations,
        overall_score=score,
        verdict=verdict,
        summary=summary,
        angles=angles,
        exemptions=summary.get("exemptions", []),
        ocr_confidence=summary.get("ocr_confidence", 1.0),
        total_glare_percentage=avg_glare_pct,
        blocks_recovered_by_clahe=total_clahe_recovered
    )

    # 4. Generate PDF Report
    pdf_filename = f"Audit_Report_{audit_id}.pdf"
    pdf_generator.generate_report(audit_res, prim_path)

    # 5. Extract inspector identity if signed in
    inspector_name = ""
    inspector_email = ""
    if request:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            s_tok = auth_header.replace("Bearer ", "").strip()
            officer = get_user_from_session(s_tok)
            if officer:
                inspector_name = officer.get("name", "")
                inspector_email = officer.get("email", "")

    # 6. Persist permanently in SQL Database (SQLite / PostgreSQL)
    save_audit_record(
        audit_res,
        image_sha256=img_hash,
        pdf_filename=pdf_filename,
        inspector_name=inspector_name,
        inspector_email=inspector_email
    )

    # Fast in-memory cache
    audit_cache[audit_id] = audit_res

    return audit_res

@app.get("/api/reports/{audit_id}")
async def download_report(audit_id: str):
    """Downloads the official generated PDF compliance report."""
    if not re.match(r"^[A-Za-z0-9_-]+$", audit_id):
        raise HTTPException(status_code=400, detail="Invalid audit ID format.")

    report_file = REPORT_DIR / f"Audit_Report_{audit_id}.pdf"
    if not is_safe_path(report_file, REPORT_DIR):
        raise HTTPException(status_code=400, detail="Path traversal security violation.")

    if not report_file.exists():
        # Check if audit is in SQL database and regenerate report if missing
        db_audit = get_audit_by_id(audit_id)
        if db_audit and db_audit.get("audit_detail"):
            try:
                from app.extractor.entities import AuditResult
                reconstructed = AuditResult.model_validate(db_audit["audit_detail"])
                img_path = None
                if reconstructed.image_url:
                    clean_rel = reconstructed.image_url.lstrip("/")
                    p1 = BASE_DIR / clean_rel
                    p2 = Path(clean_rel)
                    img_path = p1 if p1.exists() else (p2 if p2.exists() else None)
                if not img_path:
                    img_path = BASE_DIR / "sample_labels" / "sample_01_compliant_snack.png"
                pdf_generator.generate_report(reconstructed, img_path)
            except Exception as e:
                print(f"Could not regenerate PDF for {audit_id}: {e}")

    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Audit report PDF not found.")
    return FileResponse(
        str(report_file),
        media_type="application/pdf",
        filename=f"Legal_Metrology_Audit_{audit_id}.pdf"
    )

@app.get("/api/history")
async def get_history(
    request: Request,
    limit: int = 50,
    search: Optional[str] = None,
    scope: Optional[str] = None,
):
    """
    Fetches historical audit records from the SQL database.
    - scope='all': Strictly restricted to users with the Legal Metrology Inspector role.
    - scope='mine' (default): Returns exclusively the requesting officer's statutory inspections.
    """
    inspector_email = None
    auth_header = request.headers.get("Authorization", "")
    current_user = None
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        current_user = get_user_from_session(token)

    if scope == "all":
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to view department inspection ledgers."
            )
        if not is_inspector_role(current_user.get("role", "")):
            raise HTTPException(
                status_code=403,
                detail="Access denied: Only authorized Legal Metrology Inspectors can access all department inspection ledgers."
            )
        inspector_email = None
    else:
        if current_user:
            inspector_email = current_user.get("email")
        else:
            return []

    return list_recent_audits(limit=limit, search=search, inspector_email=inspector_email)

@app.get("/api/history/{audit_id}")
async def get_history_detail(audit_id: str):
    """Fetches full details of a specific historical audit from the SQL database."""
    if not re.match(r"^[A-Za-z0-9_-]+$", audit_id):
        raise HTTPException(status_code=400, detail="Invalid audit ID format.")
    record = get_audit_by_id(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found in database.")
    return record

@app.get("/api/analytics")
async def get_analytics(request: Request):
    """Returns statutory compliance analytics aggregated from the SQL database."""
    stats = get_system_analytics()
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        user = get_user_from_session(token)
        if user and user.get("email"):
            stats["officer_name"] = user.get("name", "")
            stats["officer_email"] = user.get("email", "")
            stats["officer_audit_count"] = count_inspector_audits(user.get("email", ""))
    return stats
