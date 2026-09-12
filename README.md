# Legal Metrology Compliance Checker (SIH 2026 | Team SYNX)

**Problem Statement ID:** `26034`  
**Problem Statement Title:** *Software System to check compliance of Packaged Commodities under Legal Metrology Rules, 2011 by scanning products, images and labels.*  
**Theme:** Miscellaneous / Software  
**Team:** SYNX

---

## 🎯 Executive Summary
In India, every packaged commodity must strictly adhere to mandatory declarations mandated by the **Legal Metrology (Packaged Commodities) Rules, 2011** and the **Legal Metrology Act, 2009**. Violations carry hefty statutory penalties under **Section 36(1)** (up to ₹1,00,000 fine and imprisonment).

Current compliance audits rely on slow, manual inspections prone to oversight. **SYNX Compliance Checker** automates compliance checking:
1. **Captures & Calibrates**: Ingests package label photos and establishes physical millimeter scale via dimension inputs or reference object (e.g. ₹5 coin).
2. **Spatial Text Extraction**: Runs PaddleOCR ONNX (`RapidOCR`) to extract textual strings and polygon coordinates.
3. **Entity Extraction**: Normalizes and classifies text into the 8 mandatory declarations (MRP, Net Qty, Dates, Manufacturer, Consumer Care, Origin, USP).
4. **Deterministic Rules Engine**: Validates declarations, standard unit symbols (Rule 9/13), and physical font size in mm against Rule 7 PDP tables.
5. **Interactive UI & Certified Audit Reports**: Displays bounding boxes on an interactive canvas, highlights violations in real time, and exports official PDF audit reports with cryptographic SHA-256 evidence hashes.
6. **Decoupled Digital Rulebook**: Rules are encoded in editable JSON, allowing instant updates when government circulars amend laws without code redeployment.

---

## 📐 Legal Metrology (Packaged Commodities) Rules 2011 Digitized

| Rule / Clause | Statutory Requirement | How SYNX Validates It |
| :--- | :--- | :--- |
| **Rule 6(1)(a)** | Manufacturer / Packer / Importer Name & Complete Postal Address | Verified with 6-digit postal PIN code detection. |
| **Rule 6(1)(b)** | Generic or Common Name of Commodity | Verified on prominent display / title. |
| **Rule 6(1)(c)** | Net Quantity Declaration | Verified presence, value, and standard unit. |
| **Rule 6(1)(d)** | Month and Year of Manufacture / Packing / Import | Validates date formatting (`MM/YYYY` or `MMM YYYY`). |
| **Rule 6(1)(e)** | Maximum Retail Price (MRP) & Unit Sale Price (USP) | Checks numeric price, tax inclusivity (`incl. of all taxes`), and unit rate. |
| **Rule 6(1)(f)** | Consumer Care / Grievance Redressal Contacts | Verifies presence of both telephone helpline and email address. |
| **Rule 6(10)** | Country of Origin | Required declaration on all packaged goods. |
| **Rule 7 & First Sched.** | Minimum Font / Numeral Height in mm | Computes Principal Display Panel area ($A = W \times H$ or cylindrical formula) and checks font height $\ge$ Table 1 / Table 2 statutory minimums. |
| **Rule 9 & Rule 13** | Standard Symbols of Units | Enforces metric symbols (`g`, `kg`, `ml`, `l`, `m`, `cm`, `mm`, `N`, `U`) and flags illegal abbreviations (`gms`, `kgs`, `ltrs`, `oz`, `lbs`). |
| **Act Sec. 36(1)** | Penalty Assessment | Every flagged violation links to statutory fines (up to ₹25,000 / ₹50,000 / ₹1,00,000). |

---

## 🚀 Quick Start & Launch

### Prerequisites
- Python 3.11 or 3.12 (managed via `uv` or standard Python)

### 1. Launch the Application
Run the startup script:
```bash
python run.py
```
Or using the isolated virtual environment:
```powershell
.\.venv\Scripts\python.exe run.py
```
This starts the FastAPI server at `http://127.0.0.1:8000` and automatically opens your web browser.

---

## 🧪 Ground-Truth Benchmark Test Suite (Slide 10)

The application includes 6 pre-generated benchmark synthetic labels to test and demonstrate edge cases instantly:

1. **Sample 01: Fully Compliant Snack Pack** (`sample_01_compliant_snack.png`)
   - All 8 declarations present, metric unit `g`, font size verified, score: 100% (**COMPLIANT**).
2. **Sample 02: Missing MRP & USP** (`sample_02_missing_mrp.png`)
   - MRP omitted, triggers critical failure under Rule 6(1)(e) (**NON_COMPLIANT**).
3. **Sample 03: Illegal Non-Standard Unit ('gms')** (`sample_03_non_standard_unit.png`)
   - Uses `500 gms` instead of statutory `500 g`, triggers Rule 9/13 violation (**NON_COMPLIANT**).
4. **Sample 04: Undersized Font (< 2.0 mm)** (`sample_04_font_too_small.png`)
   - Net quantity printed in tiny font ($1.1\text{ mm}$ on a $150\text{ cm}^2$ PDP), triggers Rule 7 Table 1 failure (**NON_COMPLIANT**).
5. **Sample 05: Missing Consumer Care Contacts** (`sample_05_missing_consumer_care.png`)
   - Customer care telephone and email omitted, triggers Rule 6(1)(f) violation (**NON_COMPLIANT**).
6. **Sample 06: Missing Manufacturing Date** (`sample_06_malformed_date.png`)
   - Packing/mfg date omitted, triggers Rule 6(1)(d) failure (**NON_COMPLIANT**).

---

## 🔬 Running Tests
Run automated unit tests and end-to-end pipeline verification:
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

---

## 🏛️ System Architecture

```
c:\Users\Jayant verma\Desktop\SIH\
├── app/
│   ├── main.py                     # FastAPI routes & pipeline coordination
│   ├── config.py                   # Paths, constants, and calibration configs
│   ├── ocr/
│   │   └── engine.py               # RapidOCR (PaddleOCR ONNX) spatial extraction
│   ├── extractor/
│   │   ├── entities.py             # Pydantic data models
│   │   └── parser.py               # Regex & heuristic NLP field classifier
│   ├── rules/
│   │   ├── engine.py               # Deterministic rule evaluator
│   │   ├── legal_metrology_2011.json # Digitized version-controlled rulebook
│   │   └── pdp_calculator.py       # Principal Display Panel area & font height logic
│   ├── reporting/
│   │   └── pdf_generator.py        # Defensible PDF audit certificate generator
│   ├── dataset/
│   │   └── synthetic_generator.py  # Pillow benchmark label generator
│   └── static/
│       ├── css/style.css           # Modern cyber-regulatory dark theme
│       ├── js/app.js               # Canvas polygon overlay & interaction
│       └── index.html              # Web workstation dashboard
├── sample_labels/                  # Generated benchmark test packaging labels
├── tests/
│   ├── test_rules.py               # Unit tests for Legal Metrology rules
│   └── test_pipeline.py            # End-to-end test suite
├── run.py                          # 1-click application launcher
└── requirements.txt                # Dependency specifications
```
