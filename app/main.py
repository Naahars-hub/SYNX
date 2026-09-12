import os
import uuid
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app.config import (
    BASE_DIR, UPLOAD_DIR, SAMPLE_DIR, REPORT_DIR, STATIC_DIR, RULES_FILE, get_local_ip
)
from app.extractor.entities import (
    CalibrationData, AuditResult
)
from app.ocr.engine import OCREngine
from app.extractor.parser import EntityParser
from app.rules.engine import RulesEngine
from app.rules.pdp_calculator import compute_pdp_and_font_requirements
from app.reporting.pdf_generator import PDFReportGenerator
from app.dataset.synthetic_generator import SyntheticLabelGenerator

app = FastAPI(
    title="Legal Metrology Compliance Checker - SYNX",
    description="Automated Packaged Commodities Rules 2011 Compliance Verification Engine (SIH 2026)",
    version="1.0.0"
)

# Mount static folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/sample_labels", StaticFiles(directory=str(SAMPLE_DIR)), name="sample_labels")

# Engine singletons
ocr_engine = OCREngine()
entity_parser = EntityParser()
rules_engine = RulesEngine()
pdf_generator = PDFReportGenerator()

# Cache of recent audits in-memory
audit_cache = {}

def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

@app.on_event("startup")
async def startup_event():
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
        return HTMLResponse(f.read())

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "system": "SYNX Legal Metrology Compliance Engine",
        "ocr_loaded": ocr_engine.engine is not None,
        "timestamp": datetime.now().isoformat()
    }

# Mobile camera companion sessions
mobile_sessions = {}

@app.get("/mobile", response_class=HTMLResponse)
async def serve_mobile():
    mobile_path = STATIC_DIR / "mobile.html"
    if not mobile_path.exists():
        return HTMLResponse("<h1>Mobile companion loading...</h1>")
    with open(mobile_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/api/mobile/session")
async def create_mobile_session():
    session_id = uuid.uuid4().hex[:10]
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", 8000))
    mobile_url = f"http://{local_ip}:{port}/mobile?session={session_id}"
    mobile_sessions[session_id] = {
        "status": "waiting",
        "created_at": datetime.now().isoformat(),
        "images": []
    }
    return {
        "session_id": session_id,
        "local_ip": local_ip,
        "port": port,
        "mobile_url": mobile_url
    }

@app.post("/api/mobile/upload/{session_id}")
async def upload_from_mobile(session_id: str, file: UploadFile = File(...)):
    if session_id not in mobile_sessions:
        mobile_sessions[session_id] = {"status": "waiting", "images": []}

    unique_name = f"mobile_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    img_path = UPLOAD_DIR / unique_name
    contents = await file.read()
    with open(img_path, "wb") as f:
        f.write(contents)

    image_url = f"/uploads/{unique_name}"
    item = {"filename": unique_name, "image_url": image_url}
    mobile_sessions[session_id]["images"].append(item)
    # Also set ready so single-shot works immediately or multi-shot can submit
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
        "uploaded_count": len(sess.get("images", []))
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
    audit_id = f"AUD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # Collect all image sources: List of (img_path, filename, image_url)
    image_sources = []

    # 1. Check multiple uploaded files
    upload_list = files or ([file] if file else [])
    for f in upload_list:
        if f and f.filename:
            fn = f"{audit_id}_{f.filename}"
            ip = UPLOAD_DIR / fn
            contents = await f.read()
            with open(ip, "wb") as out_f:
                out_f.write(contents)
            image_sources.append((ip, fn, f"/uploads/{fn}"))

    # 2. Check sample filenames (could be comma-separated or single)
    s_names = []
    if sample_filenames:
        s_names.extend([s.strip() for s in sample_filenames.split(",") if s.strip()])
    if sample_filename and sample_filename not in s_names:
        s_names.append(sample_filename.strip())

    for s_name in s_names:
        if (UPLOAD_DIR / s_name).exists():
            image_sources.append((UPLOAD_DIR / s_name, s_name, f"/uploads/{s_name}"))
        elif (SAMPLE_DIR / s_name).exists():
            image_sources.append((SAMPLE_DIR / s_name, s_name, f"/sample_labels/{s_name}"))

    if not image_sources:
        raise HTTPException(status_code=400, detail="No valid package image(s) provided.")

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

    # 2. Multi-Angle Spatial OCR & Entity Extraction
    from app.extractor.entities import ImageAngleResult

    angles: List[ImageAngleResult] = []
    unified_extracted_fields: Dict[str, ExtractedField] = {}
    combined_blocks: List[OCRTextBlock] = []

    angle_labels_map = [
        "Angle 1 (Front / PDP)",
        "Angle 2 (Back / Declarations)",
        "Angle 3 (Side / Nutrition)",
        "Angle 4 (Cap / Flap / Base)"
    ]

    for idx, (img_p, fn, i_url) in enumerate(image_sources):
        with Image.open(img_p) as p_img:
            w, h = p_img.size

        # OCR with calibration scale
        blocks = ocr_engine.process_image(img_p, mm_per_pixel=mm_per_px)
        fields = entity_parser.parse(blocks)

        label = angle_labels_map[idx] if idx < len(angle_labels_map) else f"Angle {idx+1}"
        for k, fld in fields.items():
            fld.source_angle = label

        angles.append(ImageAngleResult(
            angle_id=idx + 1,
            label=label,
            filename=fn,
            image_url=i_url,
            image_width=w,
            image_height=h,
            ocr_blocks=blocks,
            extracted_fields=fields
        ))

        combined_blocks.extend(blocks)

        # Merge into unified extracted fields across angles
        for k, fld in fields.items():
            if k not in unified_extracted_fields:
                unified_extracted_fields[k] = fld
            else:
                existing = unified_extracted_fields[k]
                # If existing is missing subfields, prefer more complete one
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

    # 3. Unified Rules Validation across all aggregated angles
    evaluations, score, verdict, summary = rules_engine.evaluate(
        extracted_fields=unified_extracted_fields,
        pdp=pdp,
        all_blocks=combined_blocks
    )

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
        angles=angles
    )

    # 4. Generate PDF Report
    pdf_generator.generate_report(audit_res, prim_path)

    # Cache result
    audit_cache[audit_id] = audit_res

    return audit_res

@app.get("/api/reports/{audit_id}")
async def download_report(audit_id: str):
    """Downloads the official generated PDF compliance report."""
    report_file = REPORT_DIR / f"Audit_Report_{audit_id}.pdf"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Audit report PDF not found.")
    return FileResponse(
        str(report_file),
        media_type="application/pdf",
        filename=f"Legal_Metrology_Audit_{audit_id}.pdf"
    )
