# ==============================================================================
# SYNX Legal Metrology Compliance Checker - Production Dockerfile
# Python 3.12 slim container with ONNX runtime, OpenCV headless & PDF engine
# ==============================================================================

FROM python:3.12-slim

# Prevent interactive prompts & Python buffering
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Install system dependencies required for OpenCV, RapidOCR (libgomp, libgl), and font rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Set application directory
WORKDIR /app

# Install Python dependencies first for caching efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and pre-trained rulebook
COPY app/ /app/app/
COPY sample_labels/ /app/sample_labels/
COPY run.py /app/run.py
COPY db_admin.py /app/db_admin.py

# Create persistent storage directories and assign permissions
RUN mkdir -p /app/data/uploads /app/data/reports /app/data/backups && \
    useradd -m -u 1001 -s /bin/bash synxuser && \
    chown -R synxuser:synxuser /app

# Switch to non-root user for defensive security
USER synxuser

# Expose standard application port
EXPOSE 8000

# Health check to ensure web server and database respond
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; res = urllib.request.urlopen('http://127.0.0.1:8000/api/health'); exit(0 if res.status == 200 else 1)"

# Production server launch
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
