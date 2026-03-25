#!/usr/bin/env bash
set -euo pipefail

# Local helper to deploy to a provisioned Oracle Cloud instance.
# Required env vars:
# - OCI_SSH_USER, OCI_SSH_HOST, OCI_SSH_KEY_PATH
# - (optional) deployment branch default: main

BRANCH=${1:-main}
if [ -z "${OCI_SSH_USER:-}" ] || [ -z "${OCI_SSH_HOST:-}" ] || [ -z "${OCI_SSH_KEY_PATH:-}" ]; then
  echo "Missing required OCI SSH env vars (OCI_SSH_USER, OCI_SSH_HOST, OCI_SSH_KEY_PATH)"
  exit 1
fi

ssh -o StrictHostKeyChecking=no -i "${OCI_SSH_KEY_PATH}" "${OCI_SSH_USER}@${OCI_SSH_HOST}" <<'EOF'
set -euo pipefail
cd /home/${OCI_SSH_USER}/apextrader
if [ -d .git ]; then
  git fetch --all
  git checkout ${BRANCH}
  git pull origin ${BRANCH}
else
  git clone https://github.com/spolisetti-corp/apextrader.git .
  git checkout ${BRANCH}
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart apextrader || true
EOF

echo "Oracle deploy script completed."