@echo off
cd /d "%~dp0"
title StickerNow - Install

python -m venv .venv
call .venv\Scripts\pip install -r requirements.txt

if not exist ".env" copy .env.example .env

echo.
echo Done. Edit .env with your BOT_TOKEN, then run: run.bat
pause
