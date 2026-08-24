@echo off
cd /d "%~dp0"

if not exist ngrok.exe (
    echo ngrok.exe not found in this folder.
    echo Download it from https://ngrok.com/download, unzip ngrok.exe into this
    echo same folder as this .bat file, then run this again.
    echo See the README's "View from your phone" section for full setup steps.
    pause
    exit /b 1
)

start "Polymarket Dashboard" cmd /k python dashboard.py
timeout /t 2 /nobreak >nul
start "Polymarket Public Tunnel" cmd /k ngrok.exe http 8765
