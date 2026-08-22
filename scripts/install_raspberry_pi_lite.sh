#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
SERVICE_NAME="board-item-optimizer"
SERVICE_USER="$(id -un)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TEMP_SERVICE="$(mktemp)"
trap 'rm -f "${TEMP_SERVICE}"' EXIT

if [[ "${PROJECT_DIR}" == *" "* ]]; then
  echo "Project path must not contain spaces: ${PROJECT_DIR}" >&2
  exit 1
fi

sudo apt update
sudo apt install -y python3-full python3-venv fonts-dejavu-core ca-certificates

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
"${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/requirements-rpi.txt"

cat > "${TEMP_SERVICE}" <<EOF
[Unit]
Description=Board Item Optimizer Web GUI
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=BOARD_OPTIMIZER_MAX_MC_ITERATIONS=10000
Environment=BOARD_OPTIMIZER_MAX_UPLOAD_BYTES=8388608
ExecStart=${VENV_DIR}/bin/gunicorn --config ${PROJECT_DIR}/deploy/gunicorn.conf.py web_app:app
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
UMask=0027

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "${TEMP_SERVICE}" "${SERVICE_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo
echo "Board Item Optimizer is running."
echo "Open: http://$(hostname -I | awk '{print $1}'):5000"
echo "Status: sudo systemctl status ${SERVICE_NAME}"
echo "Logs:   journalctl -u ${SERVICE_NAME} -f"
