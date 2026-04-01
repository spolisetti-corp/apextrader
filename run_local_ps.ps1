# ApexTrader local runner (Windows PowerShell)
param(
    [ValidateSet('paper', 'live')]
    [string]$Mode = 'paper'
)

$ErrorActionPreference = 'Stop'

$venvActivate = Join-Path $PSScriptRoot '.venv\Scripts\Activate.ps1'
if (Test-Path $venvActivate) {
    Write-Host "Activating venv: $venvActivate"
    . $venvActivate
} else {
    Write-Warning "Virtualenv activation script not found at $venvActivate"
}

if ($Mode -eq 'paper') {
    $env:ALPACA_PAPER = 'true'
    $env:ALPACA_BASE_URL = 'https://paper-api.alpaca.markets/v2'
} else {
    $env:ALPACA_PAPER = 'false'
    $env:ALPACA_BASE_URL = 'https://api.alpaca.markets'
}

Write-Host "Launching main.py in $Mode mode (ALPACA_PAPER=$($env:ALPACA_PAPER))"
python .\main.py
