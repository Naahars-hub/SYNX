@echo off
title SYNX - Legal Metrology Compliance Checker (SIH 2026)
echo ================================================================
echo   SYNX - Legal Metrology Compliance Checker (Problem Statement 26034)
echo   Smart India Hackathon 2026
echo ================================================================
echo Starting server and launching browser...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else (
    python run.py
)

pause
