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

set NGROK_DOMAIN=
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="NGROK_DOMAIN" set NGROK_DOMAIN=%%B
)

start "Polymarket Dashboard" cmd /k python dashboard.py
timeout /t 2 /nobreak >nul

if "%NGROK_DOMAIN%"=="" (
    start "Polymarket Public Tunnel" cmd /k ngrok.exe http 8765
) else (
    start "Polymarket Public Tunnel" cmd /k ngrok.exe http 8765 --domain=%NGROK_DOMAIN%
)
