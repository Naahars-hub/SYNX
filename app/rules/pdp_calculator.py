import math
from typing import Dict, Any, Tuple
from app.extractor.entities import PDPCalculation, CalibrationData

MIN_DIMENSION_MM = 5.0
MAX_DIMENSION_MM = 2500.0
OVERSIZE_THRESHOLD_MM = 1000.0

def calculate_pdp_area(
    package_type: str,
    width_mm: float,
    height_mm: float,
    depth_mm: float = 0.0,
    diameter_mm: float = 0.0
) -> Tuple[float, str]:
    """
    Calculates Principal Display Panel (PDP) area in square centimeters (cm²)
    under Legal Metrology (Packaged Commodities) Rules, 2011, Rule 7.
    Enforces boundary clamping (5mm <= dim <= 2500mm).
    """
    pkg_type = package_type.lower()
    
    # Boundary clamping
    w = max(MIN_DIMENSION_MM, min(MAX_DIMENSION_MM, float(width_mm)))
    h = max(MIN_DIMENSION_MM, min(MAX_DIMENSION_MM, float(height_mm)))
    d = max(0.0, min(MAX_DIMENSION_MM, float(depth_mm))) if depth_mm else 0.0
    diam = max(0.0, min(MAX_DIMENSION_MM, float(diameter_mm))) if diameter_mm else 0.0

    if pkg_type == "cylindrical":
        # Rule 7: 40% of height x circumference (or 40% of height x pi x diameter)
        eff_diam = diam if diam > 0 else w
        eff_diam = max(MIN_DIMENSION_MM, eff_diam)
        circumference = math.pi * eff_diam
        area_sqmm = 0.40 * h * circumference
        formula = f"0.40 * Height ({h:.1f}mm) * (π * Diam ({eff_diam:.1f}mm))"
    elif pkg_type == "other":
        # Rule 7: 40% of total surface area
        if d > 0:
            total_surface_sqmm = 2 * (w * h + h * d + w * d)
            area_sqmm = 0.40 * total_surface_sqmm
            formula = f"0.40 * Total Surface Area ({total_surface_sqmm:.1f}mm²)"
        else:
            area_sqmm = 0.40 * (w * h)
            formula = f"0.40 * Face Area ({w * h:.1f}mm²)"
    else:  # Rectangular default
        # Rule 7: Product of height and width of one face
        area_sqmm = w * h
        formula = f"Width ({w:.1f}mm) * Height ({h:.1f}mm)"
    
    area_sqcm = area_sqmm / 100.0  # 1 cm² = 100 mm²
    return round(area_sqcm, 2), formula

def get_rule_7_min_font_height(
    pdp_area_sqcm: float,
    is_blown_or_moulded: bool = False,
    net_quantity_g_or_ml: float = None
) -> float:
    """
    Determines minimum required font height in mm according to Rule 7 Tables 1 & 2.
    """
    # Table 1: Based on PDP Area
    if pdp_area_sqcm <= 50:
        area_min = 2.0 if is_blown_or_moulded else 1.0
    elif pdp_area_sqcm <= 100:
        area_min = 3.0 if is_blown_or_moulded else 1.5
    elif pdp_area_sqcm <= 500:
        area_min = 4.0 if is_blown_or_moulded else 2.0
    elif pdp_area_sqcm <= 2500:
        area_min = 6.0 if is_blown_or_moulded else 4.0
    else:
        area_min = 6.0

    # Table 2: Based on Net Quantity (for net quantity numerals)
    qty_min = 1.0
    if net_quantity_g_or_ml is not None and net_quantity_g_or_ml > 0:
        if net_quantity_g_or_ml <= 50:
            qty_min = 1.0
        elif net_quantity_g_or_ml <= 200:
            qty_min = 2.0
        elif net_quantity_g_or_ml <= 1000:
            qty_min = 4.0
        else:
            qty_min = 6.0

    # The required minimum is the stricter of PDP area or Net Quantity requirements
    return max(area_min, qty_min)

def compute_pdp_and_font_requirements(
    calibration: CalibrationData,
    image_width: int,
    image_height: int,
    net_quantity_g_ml: float = None
) -> Tuple[PDPCalculation, float]:
    """
    Returns PDPCalculation and mm_per_pixel scale factor.
    """
    # 1. Determine physical package dimensions with boundary clamping
    raw_w = calibration.package_width_mm if calibration.package_width_mm is not None else 120.0
    raw_h = calibration.package_height_mm if calibration.package_height_mm is not None else 180.0
    raw_d = calibration.package_depth_mm if calibration.package_depth_mm is not None else 40.0
    
    w_mm = max(MIN_DIMENSION_MM, min(MAX_DIMENSION_MM, float(raw_w)))
    h_mm = max(MIN_DIMENSION_MM, min(MAX_DIMENSION_MM, float(raw_h)))
    d_mm = max(0.0, min(MAX_DIMENSION_MM, float(raw_d)))
    
    # 2. Compute mm_per_pixel
    if calibration.mm_per_pixel and calibration.mm_per_pixel > 0:
        mm_per_px = calibration.mm_per_pixel
    elif calibration.mode == "reference_object" and calibration.reference_pixel_size:
        # e.g., coin diameter in pixels
        ref_mm = 23.0  # default 5rs coin
        if calibration.reference_object_id == "coin_1rs":
            ref_mm = 21.93
        elif calibration.reference_object_id == "coin_10rs":
            ref_mm = 27.0
        elif calibration.reference_object_id == "credit_card":
            ref_mm = 85.6
        mm_per_px = ref_mm / calibration.reference_pixel_size
    elif image_height > 0:
        # Calibrate height of image to package height
        mm_per_px = h_mm / float(image_height)
    else:
        mm_per_px = 0.264  # ~96 DPI default (25.4 / 96)

    # 3. Calculate PDP Area
    area_sqcm, formula = calculate_pdp_area(
        calibration.package_type,
        width_mm=w_mm,
        height_mm=h_mm,
        depth_mm=d_mm
    )

    # 4. Get minimum font requirement
    min_font_mm = get_rule_7_min_font_height(
        area_sqcm, 
        is_blown_or_moulded=False, 
        net_quantity_g_or_ml=net_quantity_g_ml
    )

    pdp_obj = PDPCalculation(
        package_type=calibration.package_type,
        dimensions_mm={"width": w_mm, "height": h_mm, "depth": d_mm},
        pdp_area_sqcm=area_sqcm,
        calculation_formula=formula,
        required_min_font_height_mm=min_font_mm,
        standard_clause="Rule 7(1) Table 1 & Table 2"
    )

    return pdp_obj, round(mm_per_px, 4)
