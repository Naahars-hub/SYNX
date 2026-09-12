from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    x: float = Field(..., description="Top-left x coordinate in pixels")
    y: float = Field(..., description="Top-left y coordinate in pixels")
    width: float = Field(..., description="Width in pixels")
    height: float = Field(..., description="Height in pixels")
    polygon: Optional[List[List[float]]] = Field(
        default=None, 
        description="4-point polygon [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]"
    )

class OCRTextBlock(BaseModel):
    text: str
    confidence: float
    bbox: BoundingBox
    height_px: float
    height_mm: Optional[float] = None

class ExtractedField(BaseModel):
    field_type: str  # e.g., 'mrp', 'net_quantity', 'mfg_date', 'manufacturer', 'consumer_care', etc.
    label: str
    raw_text: str
    parsed_value: Any
    unit: Optional[str] = None
    confidence: float = 1.0
    bbox: Optional[BoundingBox] = None
    font_height_px: Optional[float] = None
    font_height_mm: Optional[float] = None
    source_block_index: Optional[int] = None
    source_angle: Optional[str] = "Angle 1"

class CalibrationData(BaseModel):
    mode: str = Field(
        default="dimensions", 
        description="'dimensions' (W x H) or 'reference_object' (coin/card) or 'dpi'"
    )
    package_type: str = Field(default="rectangular", description="rectangular, cylindrical, or other")
    package_width_mm: Optional[float] = 120.0
    package_height_mm: Optional[float] = 180.0
    package_depth_mm: Optional[float] = 40.0
    reference_object_id: Optional[str] = None
    reference_pixel_size: Optional[float] = None
    mm_per_pixel: Optional[float] = None

class PDPCalculation(BaseModel):
    package_type: str
    dimensions_mm: Dict[str, float]
    pdp_area_sqcm: float
    calculation_formula: str
    required_min_font_height_mm: float
    standard_clause: str = "Rule 7(1) Table 1 & Table 2"

class RuleEvaluation(BaseModel):
    rule_id: str
    clause: str
    title: str
    field_target: str
    status: str  # PASS, FAIL, WARNING, INFO
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    message: str
    measured_value: Optional[str] = None
    expected_value: Optional[str] = None
    penalty_risk: Optional[str] = None
    statutory_ref: str

class ImageAngleResult(BaseModel):
    angle_id: int
    label: str  # e.g., "Front Panel (PDP)", "Back Panel", "Flap / Cap"
    filename: str
    image_url: str
    image_width: int
    image_height: int
    ocr_blocks: List[OCRTextBlock] = []
    extracted_fields: Dict[str, ExtractedField] = {}

class AuditResult(BaseModel):
    audit_id: str
    timestamp: str
    image_hash: str
    filename: str
    image_url: str
    image_width: int
    image_height: int
    calibration: CalibrationData
    pdp: PDPCalculation
    extracted_fields: Dict[str, ExtractedField]
    all_ocr_blocks: List[OCRTextBlock]
    rule_evaluations: List[RuleEvaluation]
    overall_score: float  # 0 to 100
    verdict: str  # COMPLIANT, NON_COMPLIANT, CONDITIONAL
    summary: Dict[str, int]
    angles: List[ImageAngleResult] = []

