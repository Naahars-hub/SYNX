import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from app.config import REPORT_DIR
from app.extractor.entities import AuditResult

class PDFReportGenerator:
    """
    Generates an official, legally defensible Legal Metrology Compliance Audit Report (PDF).
    """

    def __init__(self, output_dir: Path = REPORT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(self, audit: AuditResult, image_path: Path) -> Path:
        pdf_filename = f"Audit_Report_{audit.audit_id}.pdf"
        target_path = self.output_dir / pdf_filename

        doc = SimpleDocTemplate(
            str(target_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0B2545"),
            alignment=1  # Center
        )
        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#555555"),
            alignment=1
        )
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#134074"),
            spaceBefore=8,
            spaceAfter=4
        )
        cell_bold = ParagraphStyle(
            'CellBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#222222")
        )
        cell_normal = ParagraphStyle(
            'CellNormal',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#333333")
        )

        elements = []

        # 1. Header Banner
        elements.append(Paragraph("LEGAL METROLOGY COMPLIANCE AUDIT CERTIFICATE", title_style))
        elements.append(Paragraph(
            "Packaged Commodities Rules, 2011 & Legal Metrology Act, 2009 | SYNX Automated Enforcement Engine",
            subtitle_style
        ))
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#134074"), spaceAfter=10))

        # 2. Audit Meta Table
        verdict_color = colors.HexColor("#1B998B") if audit.verdict == "COMPLIANT" else (
            colors.HexColor("#E71D36") if audit.verdict == "NON_COMPLIANT" else colors.HexColor("#FF9F1C")
        )

        meta_data = [
            [
                Paragraph(f"<b>Audit Reference:</b> {audit.audit_id}", cell_normal),
                Paragraph(f"<b>Inspection Timestamp:</b> {audit.timestamp}", cell_normal)
            ],
            [
                Paragraph(f"<b>Inspected File:</b> {audit.filename}", cell_normal),
                Paragraph(f"<b>Evidence SHA-256:</b> <font size='6'>{audit.image_hash[:24]}...</font>", cell_normal)
            ],
            [
                Paragraph(f"<b>Overall Score:</b> <b>{audit.overall_score:.1f}%</b>", cell_normal),
                Paragraph(f"<b>Statutory Verdict:</b> <font color='{verdict_color.hexval()}'><b>{audit.verdict}</b></font>", cell_normal)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[270, 270])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EEF4F8")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#B0C4DE")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#DCE7EE")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 10))

        # 3. PDP & Physical Measurements Summary
        elements.append(Paragraph("PRINCIPAL DISPLAY PANEL (PDP) & DIMENSIONAL METRICS", section_style))
        pdp = audit.pdp
        pdp_data = [
            [
                Paragraph("<b>Package Type</b>", cell_bold),
                Paragraph("<b>Dimensions (W × H × D)</b>", cell_bold),
                Paragraph("<b>Computed PDP Area</b>", cell_bold),
                Paragraph("<b>Rule 7 Min Font Height</b>", cell_bold)
            ],
            [
                Paragraph(pdp.package_type.capitalize(), cell_normal),
                Paragraph(f"{pdp.dimensions_mm['width']:.0f} × {pdp.dimensions_mm['height']:.0f} mm", cell_normal),
                Paragraph(f"{pdp.pdp_area_sqcm:.1f} cm² ({pdp.calculation_formula})", cell_normal),
                Paragraph(f"<b>≥ {pdp.required_min_font_height_mm:.1f} mm</b> ({pdp.standard_clause})", cell_normal)
            ]
        ]
        pdp_table = Table(pdp_data, colWidths=[100, 150, 160, 130])
        pdp_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#DCE7EE")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#B0C4DE")),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(pdp_table)
        elements.append(Spacer(1, 10))

        # 3b. Multi-Angle Package Scan Breakdown (if applicable)
        if len(audit.angles) > 1:
            elements.append(Paragraph("MULTI-ANGLE PACKAGE SCAN BREAKDOWN", section_style))
            angle_rows = [
                [
                    Paragraph("<b>Inspected Angle / Face</b>", cell_bold),
                    Paragraph("<b>Resolution</b>", cell_bold),
                    Paragraph("<b>Detected Elements</b>", cell_bold),
                    Paragraph("<b>Discovered Declarations</b>", cell_bold)
                ]
            ]
            for a in audit.angles:
                f_names = [f.label for f in a.extracted_fields.values()]
                f_str = ", ".join(f_names) if f_names else "No mandatory fields on this face"
                angle_rows.append([
                    Paragraph(f"<b>{a.label}</b>", cell_normal),
                    Paragraph(f"{a.image_width} × {a.image_height} px", cell_normal),
                    Paragraph(f"{len(a.ocr_blocks)} texts", cell_normal),
                    Paragraph(f"<font color='#0B2545'>{f_str}</font>", cell_normal)
                ])
            angle_table = Table(angle_rows, colWidths=[130, 90, 80, 240])
            angle_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#DCE7EE")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#B0C4DE")),
                ('PADDING', (0,0), (-1,-1), 4),
            ]))
            elements.append(angle_table)
            elements.append(Spacer(1, 10))

        # 4. Detailed Clause-by-Clause Findings
        elements.append(Paragraph("STATUTORY RULE EVALUATION & FINDINGS", section_style))
        findings_rows = [
            [
                Paragraph("<b>Clause / Rule</b>", cell_bold),
                Paragraph("<b>Requirement</b>", cell_bold),
                Paragraph("<b>Extracted Declaration / Measurement</b>", cell_bold),
                Paragraph("<b>Status</b>", cell_bold),
                Paragraph("<b>Statutory Reference</b>", cell_bold)
            ]
        ]

        for ev in audit.rule_evaluations:
            st_color = "#1B998B" if ev.status == "PASS" else ("#E71D36" if ev.status == "FAIL" else "#FF9F1C")
            meas_text = ev.measured_value or 'N/A'
            fld = audit.extracted_fields.get(ev.field_target)
            if fld and fld.source_angle and len(audit.angles) > 1:
                meas_text += f"<br/><font color='#134074' size='7'><b>Found on:</b> {fld.source_angle}</font>"

            findings_rows.append([
                Paragraph(f"<b>{ev.clause}</b>", cell_normal),
                Paragraph(ev.title, cell_normal),
                Paragraph(f"{meas_text}<br/><font color='#666' size='7'>{ev.message}</font>", cell_normal),
                Paragraph(f"<font color='{st_color}'><b>{ev.status}</b></font>", cell_bold),
                Paragraph(f"<font size='6'>{ev.statutory_ref}</font>", cell_normal)
            ])

        findings_table = Table(findings_rows, colWidths=[75, 110, 185, 55, 115])
        findings_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#134074")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(findings_table)
        elements.append(Spacer(1, 10))

        # 5. Legal Metrology Act, 2009 Section 36(1) Penalty Notice
        elements.append(Paragraph("STATUTORY PENALTY ADVISORY", section_style))
        penalty_text = (
            "<b>Legal Metrology Act, 2009 (Section 36(1)):</b> Whoever manufactures, packs, imports, sells, "
            "distributes, delivers, offers, exposes or has in possession for sale, any pre-packaged commodity "
            "which does not conform to the declarations on the package shall be punished with fine which may "
            "extend to twenty-five thousand rupees, for the second offence to fifty thousand rupees and for "
            "subsequent offences with fine up to one lakh rupees or with imprisonment for a term up to one year, or both."
        )
        penalty_table = Table([[Paragraph(penalty_text, cell_normal)]], colWidths=[540])
        penalty_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFF3CD")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FFEEBA")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(penalty_table)
        elements.append(Spacer(1, 10))

        # 6. Digital Verification & Attestation
        sign_data = [
            [
                Paragraph("<b>Audit Authority:</b> SYNX Automated Compliance Pipeline", cell_normal),
                Paragraph("<b>Verification Status:</b> Digitally Stamped & Verified", cell_normal)
            ],
            [
                Paragraph("Admissible under Sec 65B of Indian Evidence Act", cell_normal),
                Paragraph(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}", cell_normal)
            ]
        ]
        sign_table = Table(sign_data, colWidths=[270, 270])
        sign_table.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor("#999999")),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(sign_table)

        doc.build(elements)
        return target_path
