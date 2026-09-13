import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from app.config import RULES_FILE
from app.extractor.entities import (
    ExtractedField,
    PDPCalculation,
    RuleEvaluation,
    AuditResult,
    CalibrationData,
    OCRTextBlock
)

class RulesEngine:
    """
    Deterministic Legal Metrology compliance validation engine based on
    the Legal Metrology (Packaged Commodities) Rules, 2011.
    """

    def __init__(self, rules_path: Path = RULES_FILE):
        self.rules_path = rules_path
        self.rulebook = self._load_rulebook()

    def _load_rulebook(self) -> Dict[str, Any]:
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def reload_rules(self):
        """Allows hot-reloading rules when modified via UI/API without server restart."""
        self.rulebook = self._load_rulebook()

    def evaluate(
        self,
        extracted_fields: Dict[str, ExtractedField],
        pdp: PDPCalculation,
        all_blocks: List[OCRTextBlock],
        angles: Optional[List[Any]] = None
    ) -> Tuple[List[RuleEvaluation], float, str, Dict[str, Any]]:
        """
        Runs all rules and returns:
        (evaluations, overall_score, verdict, summary_counts)
        Incorporates Statutory Exemptions (Rule 26 & Rule 3), Dual MRP checks,
        and Optical Clarity assessments.
        """
        evaluations: List[RuleEvaluation] = []
        penalty_36 = self.rulebook.get("penalty_clauses", {}).get("section_36_1", "")

        # Check Statutory Exemptions: Rule 26(a) Small Package & Rule 3 Institutional/Bulk
        net_qty = extracted_fields.get("net_quantity")
        is_small_package = False
        is_bulk_package = False
        exemptions: List[str] = []

        if net_qty and net_qty.parsed_value is not None:
            try:
                num_val = float(net_qty.parsed_value)
                u = (net_qty.unit or "").lower().strip()
                if u in ["g", "gm", "gms", "ml", "mls"] and num_val <= 10.0:
                    is_small_package = True
                    exemptions.append("Rule 26(a) Small Package Exemption (≤ 10g/ml)")
                elif (u in ["kg", "kgs", "l", "ltr", "ltrs", "liter", "liters"] and num_val > 25.0) or \
                     (u in ["g", "gm", "gms", "ml", "mls"] and num_val > 25000.0):
                    is_bulk_package = True
                    exemptions.append("Rule 3 Bulk/Institutional Package Exemption (> 25 kg/L)")
            except (ValueError, TypeError):
                pass

        # 1. Evaluate Rule 6 Mandatory Declarations
        mandatory_defs = self.rulebook.get("mandatory_declarations", [])
        for m_rule in mandatory_defs:
            field_key = m_rule["field_target"]
            field = extracted_fields.get(field_key)

            if not field:
                # Statutory Exemption Checks for missing fields
                if is_small_package and field_key == "mfg_date":
                    evaluations.append(RuleEvaluation(
                        rule_id=m_rule["id"],
                        clause=m_rule["clause"],
                        title=m_rule["title"],
                        field_target=field_key,
                        status="PASS",
                        severity="LOW",
                        message="Exempt under Rule 26(a): Date of manufacture/packing is exempt for packages with net quantity ≤ 10g or ≤ 10ml.",
                        measured_value=f"Net Qty: {net_qty.parsed_value} {net_qty.unit}",
                        expected_value="Exempt under Rule 26(a)",
                        penalty_risk=None,
                        statutory_ref="Legal Metrology (Packaged Commodities) Rules, 2011, Rule 26(a)"
                    ))
                    continue

                if is_small_package and field_key == "unit_sale_price":
                    evaluations.append(RuleEvaluation(
                        rule_id=m_rule["id"],
                        clause=m_rule["clause"],
                        title=m_rule["title"],
                        field_target=field_key,
                        status="INFO",
                        severity="LOW",
                        message="Exempt under Rule 26(a): Unit Sale Price (USP) declaration is exempt for small packages ≤ 10g or ≤ 10ml.",
                        measured_value=f"Net Qty: {net_qty.parsed_value} {net_qty.unit}",
                        expected_value="Exempt under Rule 26(a)",
                        penalty_risk=None,
                        statutory_ref="Legal Metrology (Packaged Commodities) Rules, 2011, Rule 26(a)"
                    ))
                    continue

                # Field is missing
                if m_rule.get("required", True):
                    evaluations.append(RuleEvaluation(
                        rule_id=m_rule["id"],
                        clause=m_rule["clause"],
                        title=m_rule["title"],
                        field_target=field_key,
                        status="FAIL",
                        severity=m_rule.get("severity", "CRITICAL"),
                        message=f"Mandatory declaration '{m_rule['title']}' is missing on the package.",
                        measured_value="Missing / Not Detected",
                        expected_value=f"Clearly printed {m_rule['title']}",
                        penalty_risk=penalty_36,
                        statutory_ref=m_rule["statutory_ref"]
                    ))
                else:
                    # Optional or advisory (e.g. USP in some sub-categories)
                    evaluations.append(RuleEvaluation(
                        rule_id=m_rule["id"],
                        clause=m_rule["clause"],
                        title=m_rule["title"],
                        field_target=field_key,
                        status="INFO",
                        severity="LOW",
                        message=f"{m_rule['title']} is recommended under recent amendments.",
                        measured_value="Not Detected",
                        expected_value="Unit Sale Price declaration (e.g. ₹/g or ₹/ml)",
                        penalty_risk=None,
                        statutory_ref=m_rule["statutory_ref"]
                    ))
            else:
                # Field is present -> Check deep field-specific compliance
                if field_key == "mrp":
                    self._check_mrp_details(field, m_rule, penalty_36, evaluations)
                elif field_key == "consumer_care":
                    self._check_consumer_care_details(field, m_rule, penalty_36, evaluations)
                elif field_key == "manufacturer":
                    self._check_manufacturer_details(field, m_rule, penalty_36, evaluations)
                else:
                    evaluations.append(RuleEvaluation(
                        rule_id=m_rule["id"],
                        clause=m_rule["clause"],
                        title=m_rule["title"],
                        field_target=field_key,
                        status="PASS",
                        severity="LOW",
                        message=f"Declared correctly: '{field.raw_text}'",
                        measured_value=str(field.parsed_value),
                        expected_value=f"Valid {m_rule['title']}",
                        penalty_risk=None,
                        statutory_ref=m_rule["statutory_ref"]
                    ))

        # 2. Institutional / Bulk Consumer Exemption Note (Rule 3)
        if is_bulk_package:
            evaluations.append(RuleEvaluation(
                rule_id="RULE_3_BULK_EXEMPTION",
                clause="Rule 3",
                title="Rule 3 Institutional / Industrial Package Exemption",
                field_target="net_quantity",
                status="INFO",
                severity="LOW",
                message="Package net quantity exceeds 25 kg/L. If supplied directly to institutional or industrial consumers, retail declarations under Chapter II are exempt under Rule 3.",
                measured_value=f"{net_qty.parsed_value} {net_qty.unit}",
                expected_value="Institutional / Bulk class (> 25 kg/L)",
                penalty_risk=None,
                statutory_ref="Legal Metrology (Packaged Commodities) Rules, 2011, Rule 3"
            ))

        # 3. Multi-Angle Conflict: Dual MRP Violation Check (Rule 6(1)(e))
        if angles and len(angles) > 1:
            angle_mrps = []
            for ang in angles:
                flds = getattr(ang, "extracted_fields", {})
                m_fld = flds.get("mrp")
                if m_fld and isinstance(m_fld.parsed_value, dict):
                    amt = m_fld.parsed_value.get("amount")
                    if amt is not None:
                        try:
                            angle_mrps.append((float(amt), getattr(ang, "label", f"Angle {getattr(ang, 'angle_id', '')}")))
                        except (ValueError, TypeError):
                            pass
                elif m_fld and isinstance(m_fld.parsed_value, (int, float)):
                    angle_mrps.append((float(m_fld.parsed_value), getattr(ang, "label", f"Angle {getattr(ang, 'angle_id', '')}")))

            if len(angle_mrps) >= 2:
                min_mrp, min_label = min(angle_mrps, key=lambda x: x[0])
                max_mrp, max_label = max(angle_mrps, key=lambda x: x[0])
                if min_mrp > 0 and (max_mrp - min_mrp) / min_mrp > 0.01:
                    evaluations.append(RuleEvaluation(
                        rule_id="RULE_6_1_E_DUAL_MRP",
                        clause="Rule 6(1)(e)",
                        title="Prohibition of Dual MRP / Conflicting Price Declarations",
                        field_target="mrp",
                        status="FAIL",
                        severity="CRITICAL",
                        message=f"Dual MRP violation: Conflicting retail prices detected across package angles ({min_label}: ₹{min_mrp:.2f} vs {max_label}: ₹{max_mrp:.2f}). Declaring different MRPs for identical package units violates Rule 6(1)(e).",
                        measured_value=f"Conflicting MRPs: ₹{min_mrp:.2f} vs ₹{max_mrp:.2f}",
                        expected_value="Single uniform MRP across all package angles",
                        penalty_risk=penalty_36,
                        statutory_ref="Legal Metrology (Packaged Commodities) Rules, 2011, Rule 6(1)(e)"
                    ))

        # 4. Evaluate Rule 9 & 13: Standard Units of Measurement
        self._check_units(extracted_fields, penalty_36, evaluations)

        # 5. Evaluate Rule 7: Minimum Font Size / Height on PDP (with Rule 26(a) relaxation)
        self._check_font_heights(extracted_fields, pdp, penalty_36, evaluations, is_small_package=is_small_package)

        # 6. Low Optical Clarity / Glare Assessment
        ocr_confidence = 1.0
        if all_blocks:
            confs = [b.confidence for b in all_blocks if getattr(b, "confidence", None) is not None]
            if confs:
                ocr_confidence = round(float(sum(confs) / len(confs)), 3)
                if ocr_confidence < 0.50:
                    evaluations.append(RuleEvaluation(
                        rule_id="OPTICAL_CLARITY_WARNING",
                        clause="Advisory / Image Clarity",
                        title="Optical Clarity & Glare Assessment",
                        field_target="general",
                        status="WARNING",
                        severity="MEDIUM",
                        message=f"Low optical clarity detected (average OCR confidence: {ocr_confidence * 100:.1f}%). Reflection, glare, or motion blur may obscure statutory declarations. Re-scan recommended for definitive legal audit.",
                        measured_value=f"{ocr_confidence * 100:.1f}% confidence",
                        expected_value="≥ 50.0% optical confidence",
                        penalty_risk=None,
                        statutory_ref="Legal Metrology Ingestion Standard"
                    ))

        # Calculate score and verdict
        total_evals = len(evaluations)
        pass_count = sum(1 for e in evaluations if e.status == "PASS")
        fail_count = sum(1 for e in evaluations if e.status == "FAIL")
        warn_count = sum(1 for e in evaluations if e.status == "WARNING")
        info_count = sum(1 for e in evaluations if e.status == "INFO")

        # Weighted score: FAIL has heavy deduction (-20 CRITICAL, -15 other), WARNING (-7)
        score = 100.0
        for e in evaluations:
            if e.status == "FAIL":
                deduction = 20.0 if e.severity == "CRITICAL" else 15.0
                score -= deduction
            elif e.status == "WARNING":
                score -= 7.0
        score = max(0.0, round(score, 1))

        critical_fails = sum(1 for e in evaluations if e.status == "FAIL" and e.severity == "CRITICAL")
        if critical_fails > 0 or score < 60.0:
            verdict = "NON_COMPLIANT"
        elif warn_count > 0 or score < 85.0:
            verdict = "CONDITIONAL"
        else:
            verdict = "COMPLIANT"

        summary = {
            "total_checks": total_evals,
            "passed": pass_count,
            "failed": fail_count,
            "warnings": warn_count,
            "info": info_count,
            "exemptions": exemptions,
            "ocr_confidence": ocr_confidence
        }

        return evaluations, score, verdict, summary

    def _check_mrp_details(
        self, field: ExtractedField, rule_def: Dict[str, Any], penalty: str, evals: List[RuleEvaluation]
    ):
        val = field.parsed_value
        is_tax_incl = val.get("inclusive_of_all_taxes", False) if isinstance(val, dict) else False

        if not is_tax_incl:
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="mrp",
                status="WARNING",
                severity="HIGH",
                message="MRP found, but 'inclusive of all taxes' declaration was not clearly verified.",
                measured_value=field.raw_text,
                expected_value="MRP Rs. XX (incl. of all taxes)",
                penalty_risk=penalty,
                statutory_ref=rule_def["statutory_ref"]
            ))
        else:
            amt = val.get("amount") if isinstance(val, dict) else None
            m_val = f"₹{float(amt):.2f}" if (amt is not None and isinstance(amt, (int, float))) else (
                f"₹{field.raw_text}" if not str(field.raw_text).startswith("₹") else str(field.raw_text)
            )
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="mrp",
                status="PASS",
                severity="LOW",
                message=f"MRP compliant with tax inclusivity: '{field.raw_text}'",
                measured_value=m_val,
                expected_value="MRP with tax inclusivity",
                penalty_risk=None,
                statutory_ref=rule_def["statutory_ref"]
            ))

    def _check_consumer_care_details(
        self, field: ExtractedField, rule_def: Dict[str, Any], penalty: str, evals: List[RuleEvaluation]
    ):
        val = field.parsed_value
        has_phone = bool(val.get("phone")) if isinstance(val, dict) else False
        has_email = bool(val.get("email")) if isinstance(val, dict) else False

        if not has_phone and not has_email:
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="consumer_care",
                status="FAIL",
                severity="CRITICAL",
                message="Consumer care section is missing both helpline telephone number and email address.",
                measured_value=field.raw_text,
                expected_value="Both valid telephone number and e-mail address",
                penalty_risk=penalty,
                statutory_ref=rule_def["statutory_ref"]
            ))
        elif not has_phone or not has_email:
            missing_item = "Email address" if not has_email else "Telephone number"
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="consumer_care",
                status="WARNING",
                severity="MEDIUM",
                message=f"{missing_item} is missing in the consumer care declaration.",
                measured_value=f"Phone: {val.get('phone') or 'N/A'}, Email: {val.get('email') or 'N/A'}",
                expected_value="Both phone number and email address required under Rule 6(1)(f)",
                penalty_risk=penalty,
                statutory_ref=rule_def["statutory_ref"]
            ))
        else:
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="consumer_care",
                status="PASS",
                severity="LOW",
                message="Consumer care details contain both phone and email contacts.",
                measured_value=f"Phone: {val.get('phone')}, Email: {val.get('email')}",
                expected_value="Valid phone and email contacts",
                penalty_risk=None,
                statutory_ref=rule_def["statutory_ref"]
            ))

    def _check_manufacturer_details(
        self, field: ExtractedField, rule_def: Dict[str, Any], penalty: str, evals: List[RuleEvaluation]
    ):
        val = field.parsed_value
        has_pin = val.get("has_pincode", False) if isinstance(val, dict) else False

        if not has_pin:
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="manufacturer",
                status="WARNING",
                severity="MEDIUM",
                message="Manufacturer address detected but missing 6-digit postal PIN code.",
                measured_value=field.raw_text[:60] + "...",
                expected_value="Complete postal address including PIN code",
                penalty_risk=penalty,
                statutory_ref=rule_def["statutory_ref"]
            ))
        else:
            evals.append(RuleEvaluation(
                rule_id=rule_def["id"],
                clause=rule_def["clause"],
                title=rule_def["title"],
                field_target="manufacturer",
                status="PASS",
                severity="LOW",
                message="Complete manufacturer details and postal PIN code detected.",
                measured_value=field.raw_text[:60] + "...",
                expected_value="Complete manufacturer address",
                penalty_risk=None,
                statutory_ref=rule_def["statutory_ref"]
            ))

    def _check_units(
        self, extracted_fields: Dict[str, ExtractedField], penalty: str, evals: List[RuleEvaluation]
    ):
        net_qty = extracted_fields.get("net_quantity")
        if not net_qty or not net_qty.unit:
            return

        unit = net_qty.unit.lower().strip()
        units_cfg = self.rulebook.get("standard_units", {})
        valid_units = units_cfg.get("valid_units", ["g", "kg", "ml", "l", "m", "cm", "mm", "n", "u"])
        invalid_mappings = units_cfg.get("invalid_mappings", {})

        if unit in invalid_mappings:
            correct_unit = invalid_mappings[unit]
            evals.append(RuleEvaluation(
                rule_id="RULE_9_13_UNITS",
                clause="Rule 9 & Rule 13",
                title="Standard Unit of Measurement Symbol",
                field_target="net_quantity",
                status="FAIL",
                severity="CRITICAL",
                message=f"Non-standard unit symbol '{net_qty.unit}' used. Standard symbol required is '{correct_unit}'. (e.g. 'g' instead of 'gms').",
                measured_value=f"{net_qty.parsed_value} {net_qty.unit}",
                expected_value=f"{net_qty.parsed_value} {correct_unit}",
                penalty_risk=penalty,
                statutory_ref=units_cfg.get("statutory_ref", "Legal Metrology Rules, 2011, Rule 9 & 13")
            ))
        elif unit in valid_units:
            evals.append(RuleEvaluation(
                rule_id="RULE_9_13_UNITS",
                clause="Rule 9 & Rule 13",
                title="Standard Unit of Measurement Symbol",
                field_target="net_quantity",
                status="PASS",
                severity="LOW",
                message=f"Standard metric unit symbol '{net_qty.unit}' correctly used.",
                measured_value=f"{net_qty.parsed_value} {net_qty.unit}",
                expected_value=f"Standard unit ({', '.join(valid_units)})",
                penalty_risk=None,
                statutory_ref=units_cfg.get("statutory_ref", "Legal Metrology Rules, 2011, Rule 9 & 13")
            ))

    def _check_font_heights(
        self,
        extracted_fields: Dict[str, ExtractedField],
        pdp: PDPCalculation,
        penalty: str,
        evals: List[RuleEvaluation],
        is_small_package: bool = False
    ):
        req_min_height = pdp.required_min_font_height_mm
        pdp_ref = self.rulebook.get("rule_7_font_height_tables", {}).get(
            "statutory_ref", "Legal Metrology (Packaged Commodities) Rules, 2011, Rule 7"
        )

        net_qty = extracted_fields.get("net_quantity")
        if net_qty and net_qty.font_height_mm:
            measured_mm = net_qty.font_height_mm
            # Rule 26(a) small package exemption relaxes font height constraints
            if is_small_package:
                evals.append(RuleEvaluation(
                    rule_id="RULE_7_FONT_HEIGHT",
                    clause="Rule 7 & Rule 26(a)",
                    title="Minimum Font / Numeral Height on PDP",
                    field_target="net_quantity",
                    status="PASS",
                    severity="LOW",
                    message=f"Relaxed under Rule 26(a): Small packages (≤ 10g/ml) are exempt from standard font minimums ({measured_mm:.2f} mm measured).",
                    measured_value=f"{measured_mm:.2f} mm",
                    expected_value="Relaxed (Rule 26(a) Exemption)",
                    penalty_risk=None,
                    statutory_ref="Legal Metrology (Packaged Commodities) Rules, 2011, Rule 26(a)"
                ))
            # Allow 10% tolerance due to optical blur / angle
            elif measured_mm < (req_min_height * 0.9):
                evals.append(RuleEvaluation(
                    rule_id="RULE_7_FONT_HEIGHT",
                    clause="Rule 7(1) Table 1 & Table 2",
                    title="Minimum Font / Numeral Height on PDP",
                    field_target="net_quantity",
                    status="FAIL",
                    severity="CRITICAL",
                    message=f"Net quantity numeral height ({measured_mm:.2f} mm) is below the minimum required ({req_min_height:.1f} mm) for PDP Area of {pdp.pdp_area_sqcm:.1f} cm².",
                    measured_value=f"{measured_mm:.2f} mm",
                    expected_value=f"≥ {req_min_height:.1f} mm",
                    penalty_risk=penalty,
                    statutory_ref=pdp_ref
                ))
            else:
                evals.append(RuleEvaluation(
                    rule_id="RULE_7_FONT_HEIGHT",
                    clause="Rule 7(1) Table 1 & Table 2",
                    title="Minimum Font / Numeral Height on PDP",
                    field_target="net_quantity",
                    status="PASS",
                    severity="LOW",
                    message=f"Font height ({measured_mm:.2f} mm) satisfies Rule 7 minimum requirement (≥ {req_min_height:.1f} mm).",
                    measured_value=f"{measured_mm:.2f} mm",
                    expected_value=f"≥ {req_min_height:.1f} mm",
                    penalty_risk=None,
                    statutory_ref=pdp_ref
                ))
        else:
            evals.append(RuleEvaluation(
                rule_id="RULE_7_FONT_HEIGHT",
                clause="Rule 7(1) Table 1 & Table 2",
                title="Minimum Font / Numeral Height on PDP",
                field_target="net_quantity",
                status="INFO",
                severity="LOW",
                message=f"PDP Area computed as {pdp.pdp_area_sqcm:.1f} cm². Minimum required font height is {req_min_height:.1f} mm.",
                measured_value="Calibrated without exact pixel measurement",
                expected_value=f"≥ {req_min_height:.1f} mm",
                penalty_risk=None,
                statutory_ref=pdp_ref
            ))
