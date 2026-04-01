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
    $env:ALPACA_API_KEY    = $env:PAPER_ALPACA_API_KEY
    $env:ALPACA_API_SECRET = $env:PAPER_ALPACA_API_SECRET
    $env:ALPACA_BASE_URL   = if ($env:PAPER_ALPACA_BASE_URL) { $env:PAPER_ALPACA_BASE_URL } else { 'https://paper-api.alpaca.markets/v2' }
} else {
    $env:ALPACA_PAPER = 'false'
    $env:ALPACA_API_KEY    = $env:LIVE_ALPACA_API_KEY
    $env:ALPACA_API_SECRET = $env:LIVE_ALPACA_API_SECRET
    $env:ALPACA_BASE_URL   = if ($env:LIVE_ALPACA_BASE_URL) { $env:LIVE_ALPACA_BASE_URL } else { 'https://api.alpaca.markets' }
}

if (-not $env:ALPACA_API_KEY -or -not $env:ALPACA_API_SECRET) {
    Write-Warning "Keys not set: define PAPER_ALPACA_API_KEY/PAPER_ALPACA_API_SECRET or LIVE_ALPACA_API_KEY/LIVE_ALPACA_API_SECRET in .env"
}

Write-Host "Launching main.py in $Mode mode (ALPACA_PAPER=$($env:ALPACA_PAPER))"
python .\main.py
