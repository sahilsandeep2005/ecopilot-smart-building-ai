$ErrorActionPreference = "Stop"

Write-Host "EcoPilot Windows setup" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example" -ForegroundColor Green
}

Write-Host ""
Write-Host "NEXT: open .env and set ENERGYPLUS_HOME to your EnergyPlus installation folder." -ForegroundColor Yellow
Write-Host "Example: ENERGYPLUS_HOME=C:\EnergyPlusV26-2-0"
