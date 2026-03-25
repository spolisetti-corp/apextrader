# Local run helper for ApexTrader
# Usage (PowerShell):
#   .\run_local_ps.ps1

$ErrorActionPreference = 'Stop'

$venvPath = Join-Path $PSScriptRoot '.venv\Scripts\Activate.ps1'
if (Test-Path $venvPath) {
    Write-Host "Activating virtualenv: $venvPath"
    . $venvPath
} else {
    Write-Warning "Virtualenv activation script not found at $venvPath"
}

Write-Host "Running main.py"
python .\main.py
