# ==============================================================================
# SYNX Legal Metrology Compliance Engine - Local Deployment Script (PowerShell)
# ==============================================================================

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  SYNX - LEGAL METROLOGY COMPLIANCE CHECKER (SIH 2026)" -ForegroundColor Green
Write-Host "  Local Web Application & Relational Database Deployment" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$PythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "`n[1/3] Verifying Relational Database Integrity..." -ForegroundColor Yellow
& $PythonExe db_admin.py verify
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Database verification failed! Aborting startup." -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/3] Checking Port 8000 Availability..." -ForegroundColor Yellow
$ExistingConn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($ExistingConn) {
    Write-Host "[INFO] Port 8000 is currently occupied. Freeing port..." -ForegroundColor Yellow
    $ProcessIds = $ExistingConn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $ProcessIds) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

Write-Host "`n[3/3] Launching Production Web Application Server..." -ForegroundColor Green
Write-Host "  -> Dashboard URL: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  -> API Health   : http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
Write-Host "  -> Database     : SQLite (data/metrology_audit.db)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the deployment server.`n" -ForegroundColor DarkGray

& $PythonExe run.py
