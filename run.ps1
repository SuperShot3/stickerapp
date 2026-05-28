# StickerNow bot - run from PowerShell: .\run.ps1
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

Write-Host "Installing / updating dependencies (includes rembg)..."
& .\.venv\Scripts\pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Warning "Created .env from .env.example - set BOT_TOKEN first."
}

Write-Host "Checking background removal..."
& .\.venv\Scripts\python.exe -c "from src.services.background import background_removal_available; import sys; sys.exit(0 if background_removal_available() else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error 'rembg not ready. Run: .\.venv\Scripts\pip install "rembg[cpu]"'
    exit 1
}

Write-Host "Starting stickernow_bot. Press Ctrl+C to stop."
Write-Host ""
& .\.venv\Scripts\python.exe -m src.main
