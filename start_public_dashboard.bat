@echo off
cd /d "%~dp0"

set NGROK_CMD=ngrok.exe
if not exist ngrok.exe (
    where ngrok >nul 2>nul
    if errorlevel 1 (
        echo ngrok not found - no local ngrok.exe in this folder, and "ngrok" isn't
        echo on your PATH either.
        echo Download it from https://ngrok.com/download, unzip ngrok.exe into this
        echo same folder as this .bat file, then run this again.
        echo See the README's "View from your phone" section for full setup steps.
        pause
        exit /b 1
    )
    set NGROK_CMD=ngrok
)

set NGROK_DOMAIN=
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="NGROK_DOMAIN" set NGROK_DOMAIN=%%B
)

start "Polymarket Dashboard" cmd /k python dashboard.py
timeout /t 2 /nobreak >nul

if "%NGROK_DOMAIN%"=="" (
    start "Polymarket Public Tunnel" cmd /k %NGROK_CMD% http 8765
) else (
    start "Polymarket Public Tunnel" cmd /k %NGROK_CMD% http 8765 --domain=%NGROK_DOMAIN%
)
