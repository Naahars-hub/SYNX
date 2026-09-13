# ==============================================================================
# SYNX Legal Metrology Compliance Engine - Online Deployment Script (PowerShell)
# ==============================================================================

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "  SYNX LEGAL METROLOGY COMPLIANCE CHECKER (SIH 2026)" -ForegroundColor Green
Write-Host "  Online Deployment: Public Access for Mobile & Remote Devices" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Check local server
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if (-not $conn) {
    Write-Host "`n[*] Starting local web server in background..." -ForegroundColor Yellow
    $py = ".\.venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    Start-Process -FilePath $py -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "`n[OK] Local web server is active on port 8000." -ForegroundColor Green
}

# 2. Check cloudflared binary
if (-not (Test-Path "cloudflared.exe")) {
    Write-Host "[*] Downloading Cloudflare Tunnel binary..." -ForegroundColor Yellow
    curl.exe -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -o "cloudflared.exe"
}

Write-Host "`n[*] Exposing application securely via Cloudflare Tunnel..." -ForegroundColor Green
Write-Host "Look for the public https://*.trycloudflare.com link below:`n" -ForegroundColor Yellow

.\cloudflared.exe tunnel --url http://127.0.0.1:8000
