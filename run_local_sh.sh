#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
  echo "Activated venv"
else
  echo "Warning: .venv/bin/activate not found. Ensure your virtual environment is created."
fi

echo "Running main.py"
python "$SCRIPT_DIR/main.py"