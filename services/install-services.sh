#!/usr/bin/env bash
# Nexus AIOS - Systemd Services Installer (Phase 3)
# Configures and enables nexusd.service and nexus-guard.service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Nexus AIOS Service Installer ==="

# Check for systemd
if ! command -v systemctl &> /dev/null; then
    echo "[!] Error: systemctl not detected. This system does not use systemd."
    echo "    On Android/Termux, run the daemon directly: python -m nexusd.main"
    exit 1
fi

# Ensure running with sudo or root
if [ "$EUID" -ne 0 ]; then
    echo "[!] Please run as root: sudo bash $0"
    exit 1
fi

INSTALL_DIR="/opt/nexus-aios"
CONFIG_DIR="/etc/nexus"

echo "[+] Preparing directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${CONFIG_DIR}"
mkdir -p "${INSTALL_DIR}/logs"

# Copy repository if not running directly from /opt/nexus-aios
if [ "${REPO_DIR}" != "${INSTALL_DIR}" ]; then
    echo "[+] Syncing repository files to ${INSTALL_DIR}..."
    cp -r "${REPO_DIR}/"* "${INSTALL_DIR}/"
fi

# Ensure python venv exists in /opt/nexus-aios/venv
if [ ! -d "${INSTALL_DIR}/venv" ]; then
    echo "[+] Creating virtual environment at ${INSTALL_DIR}/venv..."
    python3 -m venv "${INSTALL_DIR}/venv"
    "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
    "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
fi

# Create default environment file if missing
ENV_FILE="${CONFIG_DIR}/nexus.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo "[+] Generating initial environment configuration at ${ENV_FILE}..."
    cat <<EOF > "${ENV_FILE}"
# Nexus AIOS Environment Configuration
NEXUS_API_HOST=0.0.0.0
NEXUS_API_PORT=8765
# NEXUS_API_KEY=your-api-key-here
EOF
    chmod 600 "${ENV_FILE}"
fi

echo "[+] Installing systemd service units..."
cp "${SCRIPT_DIR}/nexusd.service" /etc/systemd/system/
cp "${SCRIPT_DIR}/nexus-guard.service" /etc/systemd/system/

systemctl daemon-reload

echo "[+] Enabling and starting Nexus services..."
systemctl enable --now nexusd.service
systemctl enable --now nexus-guard.service

echo "=== Nexus AIOS Services Installed Successfully! ==="
echo "Check daemon status:  systemctl status nexusd"
echo "Check guard status:   systemctl status nexus-guard"
echo "Web UI reachable at:  http://127.0.0.1:8765"
