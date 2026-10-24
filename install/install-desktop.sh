#!/usr/bin/env bash
# ==============================================================================
# Nexus AIOS - Linux Desktop / Laptop Installer (Phase 1)
# Works on Debian, Ubuntu, Fedora, and Arch distributions.
# ==============================================================================

set -euo pipefail

echo "==> [Nexus AIOS] Starting Linux Desktop installation..."

# 1. Package manager detection and dependency installation
if command -v apt-get >/dev/null 2>&1; then
    echo "==> Debian/Ubuntu detected. Installing Python 3 and venv..."
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git curl
elif command -v dnf >/dev/null 2>&1; then
    echo "==> Fedora/RHEL detected. Installing Python 3..."
    sudo dnf install -y python3 python3-pip git curl
elif command -v pacman >/dev/null 2>&1; then
    echo "==> Arch Linux detected. Installing Python..."
    sudo pacman -Sy --noconfirm python python-pip git curl
else
    echo "==> Warning: Unknown package manager. Please ensure Python 3.11+ is installed."
fi

# 2. Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

# 3. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "==> Creating Python virtual environment in .venv..."
    python3 -m venv .venv
else
    echo "==> Existing virtual environment found in .venv."
fi

# 4. Activate virtual environment and install requirements
echo "==> Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip and installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Ensure configuration and log directories
mkdir -p logs config
if [ ! -f "config/nexus.yaml" ]; then
    echo "==> Creating default config/nexus.yaml..."
    cat << 'EOF' > config/nexus.yaml
api:
  host: "127.0.0.1"
  port: 8765
  debug: false

router:
  prefer: "local"
  timeout_seconds: 15

model:
  local_type: "ollama"
  local_url: "http://127.0.0.1:11434"
  local_model: "llama3.2:1b"
  local_path: ""
  cloud_provider: "openai"
  cloud_url: "https://api.openai.com/v1"
  cloud_model: "gpt-4o-mini"
EOF
fi

echo ""
echo "==================================================================="
echo " [Nexus AIOS] Desktop Installation Complete!"
echo "==================================================================="
echo " 1. Activate your virtual environment:"
echo "    source .venv/bin/activate"
echo ""
echo " 2. (Optional) Set your Cloud LLM API key:"
echo "    export NEXUS_API_KEY=\"your_key_here\""
echo ""
echo " 3. Run the daemon in one terminal:"
echo "    python3 -m nexusd.main"
echo ""
echo " 4. Run the natural language terminal in another:"
echo "    python3 cli/nexus.py"
echo "==================================================================="
