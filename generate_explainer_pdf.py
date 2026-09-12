from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

pdf_path = Path("SYNX_Complete_System_Explainer.pdf")
doc = SimpleDocTemplate(
    str(pdf_path),
    pagesize=letter,
    rightMargin=36,
    leftMargin=36,
    topMargin=36,
    bottomMargin=36
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    'DocTitle',
    parent=styles['Heading1'],
    fontName='Helvetica-Bold',
    fontSize=18,
    leading=22,
    textColor=colors.HexColor("#0B2545"),
    alignment=1
)
sub_style = ParagraphStyle(
    'DocSub',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#4A5568"),
    alignment=1
)
h1_style = ParagraphStyle(
    'H1',
    parent=styles['Heading2'],
    fontName='Helvetica-Bold',
    fontSize=13,
    leading=16,
    textColor=colors.HexColor("#134074"),
    spaceBefore=12,
    spaceAfter=6
)
h2_style = ParagraphStyle(
    'H2',
    parent=styles['Heading3'],
    fontName='Helvetica-Bold',
    fontSize=10.5,
    leading=13,
    textColor=colors.HexColor("#1D4ED8"),
    spaceBefore=8,
    spaceAfter=4
)
body = ParagraphStyle(
    'Body',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=8.5,
    leading=12,
    textColor=colors.HexColor("#2D3748")
)
body_bold = ParagraphStyle(
    'BodyBold',
    parent=body,
    fontName='Helvetica-Bold'
)
callout = ParagraphStyle(
    'Callout',
    parent=body,
    fontName='Helvetica-Oblique',
    textColor=colors.HexColor("#1E3A8A")
)
cell_hdr = ParagraphStyle(
    'CellHdr',
    parent=body,
    fontName='Helvetica-Bold',
    textColor=colors.white
)
cell_txt = ParagraphStyle(
    'CellTxt',
    parent=body,
    fontSize=8,
    leading=10.5
)

elements = []

# Title & Banner
elements.append(Paragraph("SYNX - COMPLETE SYSTEM EXPLAINER & ARCHITECTURE GUIDE", title_style))
elements.append(Paragraph("Smart India Hackathon 2026 | Problem Statement ID: 26034 | Team SYNX", sub_style))
elements.append(Paragraph("Automated Verification under Legal Metrology (Packaged Commodities) Rules, 2011", sub_style))
elements.append(Spacer(1, 8))
elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#134074"), spaceAfter=10))

# Executive Box
intro_p = Paragraph(
    "<b>In Simple English:</b> SYNX is an automated AI-powered digital inspector. "
    "It takes photos of any packaged product (like chips, cold drinks, or shampoo), reads all the text, "
    "mathematically measures the font height down to millimeters, verifies every mandatory Indian legal declaration, "
    "and instantly produces an official, court-admissible PDF violation and audit certificate.",
    callout
)
intro_table = Table([[intro_p]], colWidths=[540])
intro_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#3B82F6")),
    ('PADDING', (0,0), (-1,-1), 8),
]))
elements.append(intro_table)
elements.append(Spacer(1, 10))

# 8 Stages Overview
elements.append(Paragraph("1. THE 8 PIPELINE STAGES (DATA FLOW AT A GLANCE)", h1_style))

stages_data = [
    [Paragraph("<b>Stage</b>", cell_hdr), Paragraph("<b>Component</b>", cell_hdr), Paragraph("<b>Plain English Job (Analogy)</b>", cell_hdr)],
    [Paragraph("<b>1. Ingestion</b>", cell_txt), Paragraph("FastAPI REST API + QR Session", cell_txt), Paragraph("Takes photos from phone camera or desktop without installing apps.", cell_txt)],
    [Paragraph("<b>2. Anti-Glare Clean</b>", cell_txt), Paragraph("OpenCV + CLAHE Filter", cell_txt), Paragraph("Like polarized sunglasses for AI; removes shiny light glare from foil/plastic.", cell_txt)],
    [Paragraph("<b>3. Spatial OCR</b>", cell_txt), Paragraph("RapidOCR (PaddleOCR ONNX)", cell_txt), Paragraph("Reads every single word and records where it sits on the packaging.", cell_txt)],
    [Paragraph("<b>4. Calibration</b>", cell_txt), Paragraph("Millimeter Scale Calculator", cell_txt), Paragraph("Converts screen pixels into real millimeters using package dimensions or a coin.", cell_txt)],
    [Paragraph("<b>5. Entity NLP</b>", cell_txt), Paragraph("Heuristic Regex & Detective Brain", cell_txt), Paragraph("Figures out which word is Price, Date, Factory, or Weight (and filters nutrition).", cell_txt)],
    [Paragraph("<b>6. 3D Assembly</b>", cell_txt), Paragraph("Multi-Angle Aggregator", cell_txt), Paragraph("Combines Front, Back, and Cap into one single unified product brain.", cell_txt)],
    [Paragraph("<b>7. Rulebook</b>", cell_txt), Paragraph("Legal Metrology Rules Engine", cell_txt), Paragraph("Evaluates rules, detects violations, and calculates Sec 36(1) penalty risk.", cell_txt)],
    [Paragraph("<b>8. Legal Report</b>", cell_txt), Paragraph("HTML5 Canvas + ReportLab PDF", cell_txt), Paragraph("Draws green/red boxes on screen and prints an official court-ready certificate.", cell_txt)]
]
stages_table = Table(stages_data, colWidths=[85, 160, 295])
stages_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#134074")),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
    ('PADDING', (0,0), (-1,-1), 4.5),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
]))
elements.append(stages_table)
elements.append(Spacer(1, 10))

# Technical Deep Dive
elements.append(Paragraph("2. STEP-BY-STEP TECHNICAL EXPLANATIONS & JARGON BUSTERS", h1_style))

steps = [
    ("Step 1: Smartphone Zero-Install QR Ingestion",
     "<b>REST API & Polling:</b> Think of the REST API as a waiter in a restaurant. When you scan the QR code on your phone, "
     "the server opens a private mailbox (Session ID). The phone drops photos into that mailbox, and the laptop checks the mailbox "
     "every second until the photos arrive. No native mobile app install is needed!"),
    ("Step 2: Glare Attenuation & CLAHE Preprocessing",
     "<b>Computer Vision (OpenCV) & CLAHE:</b> Real packaging (chips packets, plastic bottles) acts like a mirror under store lights. "
     "Ordinary cameras see blinding white glare spots. CLAHE (Contrast Limited Adaptive Histogram Equalization) cuts the image into "
     "tiny micro-tiles and balances dark/light areas locally. It works like polarized sunglasses, cutting through reflections to reveal faint dot-matrix printing."),
    ("Step 3: Spatial OCR & Bounding Box Detection",
     "<b>PaddleOCR ONNX & Bounding Boxes:</b> We use a pre-trained deep neural network running on ONNX. It reads text and returns "
     "the exact pixel box (X, Y, W, H) and confidence score (e.g., 98% sure) for every word. Because it uses ONNX, it runs in less than "
     "1 second on a standard laptop CPU without requiring an expensive gaming graphics card (GPU)."),
    ("Step 4: Millimeter Calibration & Rule 7 PDP Calculations",
     "<b>Scale Factor & Principal Display Panel (PDP):</b> A screen only knows pixels, not millimeters. By inputting the package dimensions "
     "or using a ₹5 coin (legally exactly 23.0 mm), our math engine computes the scale (e.g. 0.1 mm per pixel). It calculates the PDP area "
     "(front face of the pack) and looks up the statutory minimum font height tier under Rule 7 (e.g. >= 2.0 mm or >= 4.0 mm)."),
    ("Step 5: NLP Entity Parsing & Blacklist Filtering",
     "<b>Regex, Blacklists & Disambiguation:</b> OCR gives us 60 random words. Our detective brain uses regex patterns to extract entities: "
     "it finds 6-digit PIN codes, extracts dot-matrix dates (12/2026), strictly filters out nutrition tables (so Sugar: 14g is never mistaken "
     "for the pack weight!), and distinguishes total MRP (Rs. 30.00) from Unit Sale Price (Rs. 0.075/ml)."),
    ("Step 6: Multi-Angle 3D Product Aggregation",
     "<b>Unified Packaging Ledger:</b> Real packages are 3D! The brand is on the front, factory address is on the back, and the price is stamped "
     "on the cap. Our multi-angle aggregator tags each extraction with its source face and merges them into one complete audit record."),
    ("Step 7: Decoupled Statutory Rulebook & Penalties",
     "<b>JSON Rulebook & Section 36(1):</b> Laws are stored in an editable JSON file rather than hardcoded in Python. If legal rules change, "
     "lawyers can edit the JSON in the browser with live hot-reloading. The engine automatically maps violations to Legal Metrology Act Sec 36(1) "
     "penalties (fines of ₹25,000, ₹50,000, or ₹1,00,000 / 1 year imprisonment)."),
    ("Step 8: Court-Admissible PDF with SHA-256 Hashing",
     "<b>Cryptographic Evidence Integrity:</b> Under Section 65B of the Indian Evidence Act, digital proof must be untampered. "
     "The system computes a SHA-256 mathematical hash of the photo. If someone edits even one pixel in Photoshop, the hash breaks. "
     "This proves digital authenticity in a court of law.")
]

for title, desc in steps:
    elements.append(Paragraph(title, h2_style))
    elements.append(Paragraph(desc, body))
    elements.append(Spacer(1, 4))

elements.append(Spacer(1, 8))
elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

# 8 Statutory Rules Explained
elements.append(Paragraph("3. THE 8 MANDATORY STATUTORY RULES IN PLAIN ENGLISH", h1_style))

rules_data = [
    [Paragraph("<b>Statutory Rule</b>", cell_hdr), Paragraph("<b>Plain English Meaning</b>", cell_hdr), Paragraph("<b>What SYNX Verifies & Catches</b>", cell_hdr)],
    [Paragraph("<b>Rule 6(1)(a)</b>", cell_txt), Paragraph("Manufacturer Details", cell_txt), Paragraph("Checks complete address and verifies mandatory 6-digit postal PIN code.", cell_txt)],
    [Paragraph("<b>Rule 6(1)(b)</b>", cell_txt), Paragraph("Commodity Name", cell_txt), Paragraph("Identifies genuine generic name; filters out marketing slogans and process text.", cell_txt)],
    [Paragraph("<b>Rule 6(1)(c)</b>", cell_txt), Paragraph("Net Quantity & Units", cell_txt), Paragraph("Verifies SI metric units (g, ml, kg); penalizes illegal symbols (gms, kgs).", cell_txt)],
    [Paragraph("<b>Rule 6(1)(d)</b>", cell_txt), Paragraph("Mfg / Packing Date", cell_txt), Paragraph("Extracts MM/YYYY or DD/MM/YYYY dates, including faint dot-matrix cap stamps.", cell_txt)],
    [Paragraph("<b>Rule 6(1)(e)</b>", cell_txt), Paragraph("MRP & Taxes", cell_txt), Paragraph("Extracts total price and verifies 'inclusive of all taxes' declaration.", cell_txt)],
    [Paragraph("<b>Rule 6(1)(e)</b>", cell_txt), Paragraph("Unit Sale Price (USP)", cell_txt), Paragraph("Verifies per-unit rate (e.g. Rs. 0.075/ml) so consumers can compare value.", cell_txt)],
    [Paragraph("<b>Rule 6(1)(f)</b>", cell_txt), Paragraph("Consumer Care", cell_txt), Paragraph("Checks phone helpline and email; rejects fake 14-digit FSSAI numbers.", cell_txt)],
    [Paragraph("<b>Rule 6(10)</b>", cell_txt), Paragraph("Country of Origin", cell_txt), Paragraph("Checks explicit declaration (e.g. Made in India) or manufacturer postal origin.", cell_txt)],
    [Paragraph("<b>Rule 7</b>", cell_txt), Paragraph("Font Height Tiers", cell_txt), Paragraph("Measures physical letter height in mm against statutory minimum thresholds.", cell_txt)],
    [Paragraph("<b>Sec 36(1)</b>", cell_txt), Paragraph("Statutory Penalties", cell_txt), Paragraph("Calculates legal liability: ₹25k (1st), ₹50k (2nd), ₹1L / 1yr jail (subsequent).", cell_txt)]
]
rules_table = Table(rules_data, colWidths=[80, 140, 320])
rules_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#134074")),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
    ('PADDING', (0,0), (-1,-1), 4),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
]))
elements.append(rules_table)
elements.append(Spacer(1, 12))

# Footer notice
footer_p = Paragraph(
    "<b>How to Run in 1 Click:</b> Double-click <code>start.bat</code> in the project folder to launch the server and open the browser interface automatically.",
    callout
)
elements.append(Table([[footer_p]], colWidths=[540], style=[
    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#22C55E")),
    ('PADDING', (0,0), (-1,-1), 6),
]))

doc.build(elements)
print("PDF generated successfully:", pdf_path.resolve())
