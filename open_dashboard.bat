@echo off
cd /d "%~dp0"
start "Polymarket Dashboard" cmd /k python dashboard.py
timeout /t 2 /nobreak >nul
start "" http://localhost:8765
