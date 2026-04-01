#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-paper}"
if [[ "$MODE" != "paper" && "$MODE" != "live" ]]; then
  echo "Usage: ./run_local_sh.sh [paper|live]"
  exit 1
fi

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
  echo "Virtualenv activated"
else
  echo "Warning: .venv/bin/activate not found"
fi

if [[ "$MODE" == "paper" ]]; then
  export ALPACA_PAPER=true
  export ALPACA_API_KEY="${PAPER_ALPACA_API_KEY}"
  export ALPACA_API_SECRET="${PAPER_ALPACA_API_SECRET}"
  export ALPACA_BASE_URL="${PAPER_ALPACA_BASE_URL:-https://paper-api.alpaca.markets/v2}"
else
  export ALPACA_PAPER=false
  export ALPACA_API_KEY="${LIVE_ALPACA_API_KEY}"
  export ALPACA_API_SECRET="${LIVE_ALPACA_API_SECRET}"
  export ALPACA_BASE_URL="${LIVE_ALPACA_BASE_URL:-https://api.alpaca.markets}"
fi

if [[ -z "$ALPACA_API_KEY" || -z "$ALPACA_API_SECRET" ]]; then
  echo "Warning: keys not set — define PAPER_ALPACA_API_KEY/PAPER_ALPACA_API_SECRET or LIVE_ALPACA_API_KEY/LIVE_ALPACA_API_SECRET in .env"
fi

echo "Running main.py in $MODE mode (ALPACA_PAPER=$ALPACA_PAPER)"
python main.py
