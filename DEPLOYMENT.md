# 🚀 SYNX Legal Metrology Verification Engine - Deployment Manual

Comprehensive guide for deploying the **SYNX Web Application** and **Relational Database** (`data/metrology_audit.db`) across local environments, Docker containers, and cloud PaaS platforms.

---

## 🏗️ Architectural Overview

- **Web Application Backend**: FastAPI (Python 3.12, Uvicorn ASGI).
- **Computer Vision & OCR Engine**: RapidOCR (PaddleOCR ONNX Runtime) with OpenCV CLAHE pre-processing.
- **Relational Database**: Embedded SQLite3 with Row factory, PRAGMA foreign keys, and indexes (`inspections`, `audit_evaluations`, `users`, `sessions`).
- **Persistent Storage**:
  - `data/metrology_audit.db`: Relational statutory ledger & audit history.
  - `data/uploads/`: Photographic evidence and calibrated packaging images.
  - `data/reports/`: Cryptographically signed statutory audit certificates (PDF).
  - `data/backups/`: Database snapshot backups.

---

## 💻 Option 1: Instant Local Deployment (Windows / Linux / macOS)

### 1. Prerequisites
- Python 3.11 or 3.12 (or virtual environment in `.venv`)
- Dependencies installed:
  ```powershell
  uv pip install -r requirements.txt
  # OR
  pip install -r requirements.txt
  ```

### 2. Verify Database Integrity
Run the built-in database management CLI tool:
```powershell
.\.venv\Scripts\python.exe db_admin.py verify
```
Expected output:
```text
[1] SQLite File Integrity: PRAGMA integrity_check: OK
[2] Foreign Key Integrity: No foreign key violations found (100% consistent).
[3] Relational Tables & Row Counts: inspections, audit_evaluations, users, sessions all OK.
```

### 3. Deploy & Run
Execute the local deployment script:
```powershell
powershell -ExecutionPolicy Bypass -File deploy_local.ps1
```
Or simply:
```powershell
.\.venv\Scripts\python.exe run.py
```
- **Web Dashboard**: `http://127.0.0.1:8000`
- **Mobile Companion**: `http://<YOUR_LAN_IP>:8000/mobile`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

## 🐳 Option 2: Docker & Docker Compose Containerized Deployment

Docker provides an isolated, zero-dependency environment complete with ONNX, OpenCV headless, and non-root security.

### 1. One-Click Compose Deployment
```bash
docker compose up -d --build
```

### 2. Check Container Health
```bash
docker compose ps
docker logs -f synx_metrology_app
```

### 3. Volume Persistence
The `docker-compose.yml` mounts host directory `./data` into `/app/data`:
- Database records in `./data/metrology_audit.db` persist across container teardowns (`docker compose down`).
- Uploads and generated PDFs remain securely saved on the host.

### 4. Stop or Restart
```bash
docker compose stop
docker compose start
```

---

## ☁️ Option 3: Cloud PaaS Deployment

### 1. Render (Recommended)
This repository includes a native `render.yaml` blueprint with persistent disk mounting:
1. Push this repository to GitHub/GitLab.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New** -> **Blueprint**.
3. Connect your repository. Render automatically reads `render.yaml`, spins up the Docker web service, attaches a 10GB persistent disk at `/app/data`, and provides a public HTTPS domain.

### 2. Railway / Fly.io / AWS EC2
- **Railway**: Connect GitHub repository. Railway automatically builds using `Dockerfile`. Add a persistent volume mounted to `/app/data`.
- **Fly.io**:
  ```bash
  fly launch
  fly volumes create synx_data --size 10
  fly deploy
  ```
- **AWS EC2 (Ubuntu 22.04 / 24.04 LTS)**:
  ```bash
  git clone <repo_url>
  cd SIH
  sudo docker compose up -d --build
  ```

---

## 🗄️ Database Operations & Maintenance

The `db_admin.py` CLI provides operational utilities:

| Command | Action |
| :--- | :--- |
| `python db_admin.py verify` | Validates SQLite integrity, foreign keys, and table schema |
| `python db_admin.py stats` | Displays total inspections, user accounts, and statutory violation stats |
| `python db_admin.py backup` | Generates a timestamped atomic backup under `data/backups/` |
| `python db_admin.py vacuum` | Defragments and compacts database storage (`VACUUM` & `REINDEX`) |
| `python db_admin.py init` | Reconstructs missing tables or runs database migrations |

---

## 🛡️ Health & Observability Endpoint

Check the live deployment health:
```bash
curl http://127.0.0.1:8000/api/health
```

Sample Response:
```json
{
  "status": "healthy",
  "system": "SYNX Legal Metrology Compliance Engine",
  "ocr_loaded": true,
  "database": {
    "status": "connected",
    "engine": "SQLite3",
    "database_name": "metrology_audit.db",
    "size_kb": 1932.0,
    "inspections_count": 102,
    "users_count": 16
  },
  "timestamp": "2026-09-13T06:58:00.000000"
}
```
