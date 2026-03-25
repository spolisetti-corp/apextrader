# ApexTrader local runner (Windows PowerShell)
$ErrorActionPreference = 'Stop'

$venvActivate = Join-Path $PSScriptRoot '.venv\Scripts\Activate.ps1'
if (Test-Path $venvActivate) {
    Write-Host "Activating venv: $venvActivate"
    . $venvActivate
} else {
    Write-Warning "Virtualenv activation script not found at $venvActivate"
}

Write-Host "Launching main.py"
python .\main.py
