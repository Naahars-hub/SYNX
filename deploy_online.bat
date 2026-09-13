@echo off
title SYNX - Deploy Web Application & Database Online (Cloudflare Tunnel)
echo ==============================================================================
echo   SYNX LEGAL METROLOGY COMPLIANCE CHECKER (SIH 2026)
echo   Deploying Web Application and Database Online for Public/Multi-Device Access
echo ==============================================================================
echo.

if not exist "cloudflared.exe" (
    echo [INFO] Downloading Cloudflare Tunnel binary...
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe -o cloudflared.exe
)

echo [1/2] Verifying Local Server...
netstat -ano | findstr :8000 >nul
if errorlevel 1 (
    echo [INFO] Local web server is not running. Starting server in background...
    if exist ".venv\Scripts\python.exe" (
        start /b "" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    ) else (
        start /b "" python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    )
    timeout /t 3 >nul
) else (
    echo [OK] Local web server is already active on port 8000.
)

echo.
echo [2/2] Launching Public HTTPS Tunnel...
echo Any device on any network (phones, laptops, tablets) can access the URL below.
echo Press Ctrl+C anytime to stop public access.
echo ==============================================================================
echo.
.\cloudflared.exe tunnel --url http://127.0.0.1:8000
