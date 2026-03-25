#!/usr/bin/env bash
# =============================================================================
# ApexTrader — Oracle Cloud Free Tier Setup Script
# Tested on: Ubuntu 22.04 (AMD x86 or ARM Ampere A1)
#
# Usage (after SSH into VM):
#   git clone https://github.com/spolisetti-corp/apextrader.git /opt/apextrader
#   chmod +x /opt/apextrader/deploy/setup.sh
#   sudo /opt/apextrader/deploy/setup.sh
# =============================================================================
set -euo pipefail

APP_USER="apextrader"
APP_DIR="/opt/apextrader"
REPO_URL="https://github.com/spolisetti-corp/apextrader.git"
SERVICE_NAME="apextrader"
PYTHON="python3"

echo "======================================================"
echo " ApexTrader — Oracle Cloud Free Tier Setup"
echo "======================================================"

# ── 1. System packages ─────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    git python3 python3-pip python3-venv \
    curl wget tzdata

# Set timezone to US/Eastern so market-hours logic is correct
timedatectl set-timezone America/New_York
echo "  Timezone: $(timedatectl show -p Timezone --value)"

# ── 2. Create dedicated app user ───────────────────────
echo "[2/6] Creating app user '${APP_USER}'..."
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --shell /bin/bash --create-home "${APP_USER}"
fi

# ── 3. Clone / update repo ─────────────────────────────
echo "[3/6] Setting up repo at ${APP_DIR}..."
if [ -d "${APP_DIR}/.git" ]; then
    echo "  Repo exists — pulling latest..."
    sudo -u "${APP_USER}" git -C "${APP_DIR}" pull origin main
else
    git clone "${REPO_URL}" "${APP_DIR}"
    chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
fi

# ── 4. Python venv + dependencies ──────────────────────
echo "[4/6] Creating Python venv and installing dependencies..."
sudo -u "${APP_USER}" ${PYTHON} -m venv "${APP_DIR}/venv"
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install --upgrade pip -q
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q
echo "  Dependencies installed."

# ── 5. .env file ───────────────────────────────────────
echo "[5/6] Configuring environment..."
ENV_FILE="${APP_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    cp "${APP_DIR}/.env.example" "${ENV_FILE}"
    chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    echo ""
    echo "  *** ACTION REQUIRED ***"
    echo "  Edit ${ENV_FILE} and fill in your API keys:"
    echo "    nano ${ENV_FILE}"
    echo ""
else
    echo "  .env already exists — skipping."
fi

# ── 6. systemd service ─────────────────────────────────
echo "[6/6] Installing systemd service..."
SERVICE_FILE="${APP_DIR}/deploy/apextrader.service"
DEST="/etc/systemd/system/${SERVICE_NAME}.service"

# Substitute placeholders
sed \
    -e "s|APP_DIR|${APP_DIR}|g" \
    -e "s|APP_USER|${APP_USER}|g" \
    "${SERVICE_FILE}" > "${DEST}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

echo ""
echo "======================================================"
echo " Setup complete!"
echo "======================================================"
echo ""
echo " Next steps:"
echo "   1. Add your API keys:"
echo "      nano ${ENV_FILE}"
echo ""
echo "   2. Start the bot:"
echo "      sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "   3. Check status / logs:"
echo "      sudo systemctl status ${SERVICE_NAME}"
echo "      sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "   4. To update in future:"
echo "      sudo ${APP_DIR}/deploy/update.sh"
echo ""
