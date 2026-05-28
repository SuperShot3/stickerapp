@echo off
cd /d "%~dp0"
title StickerNow Bot

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing / updating dependencies (includes rembg for background removal)...
call .venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 (
    echo pip install failed. Fix errors above and try again.
    pause
    exit /b 1
)

if not exist ".env" (
    echo Copying .env.example to .env - edit BOT_TOKEN before running.
    copy .env.example .env
)

echo.
echo Checking background removal...
.venv\Scripts\python.exe -c "from src.services.background import background_removal_available; import sys; sys.exit(0 if background_removal_available() else 1)"
if errorlevel 1 (
    echo.
    echo ERROR: rembg is not ready. Run: .venv\Scripts\pip install "rembg[cpu]"
    pause
    exit /b 1
)

echo Starting @stickernow_bot...
echo Press Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m src.main
pause
