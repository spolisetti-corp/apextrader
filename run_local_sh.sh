#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
  echo "Virtualenv activated"
else
  echo "Warning: .venv/bin/activate not found"
fi

echo "Running main.py"
python main.py
