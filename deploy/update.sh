#!/usr/bin/env bash
# =============================================================================
# ApexTrader — Update & Restart Script
# Pull latest code from main and restart the service.
#
# Usage: sudo /opt/apextrader/deploy/update.sh
# =============================================================================
set -euo pipefail

APP_DIR="/opt/apextrader"
APP_USER="apextrader"
SERVICE_NAME="apextrader"

echo "[1/4] Pulling latest code from main..."
sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin main
sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard origin/main

echo "[2/4] Updating Python dependencies..."
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

echo "[3/4] Restarting service..."
systemctl restart "${SERVICE_NAME}"

echo "[4/4] Status:"
systemctl status "${SERVICE_NAME}" --no-pager
echo ""
echo "Done. Tail logs with: sudo journalctl -u ${SERVICE_NAME} -f"
