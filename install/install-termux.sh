#!/usr/bin/env bash
# ==============================================================================
# Nexus AIOS - Termux / proot Debian Installer (Phase 1)
# Tailored for low RAM, ARM64 phones and tablets. No root required.
# ==============================================================================

set -euo pipefail

echo "==> [Nexus AIOS] Starting Termux / proot Debian installation..."

# 1. Detect environment and update system packages
if command -v apt-get >/dev/null 2>&1; then
    echo "==> Updating apt repositories and installing Python 3 + venv..."
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv curl git
elif command -v pkg >/dev/null 2>&1; then
    echo "==> Native Termux detected. Installing python and dependencies..."
    pkg update -y
    pkg install -y python python-pip git curl
else
    echo "==> Warning: Neither apt-get nor pkg found. Assuming Python is already installed."
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

echo "==> Upgrading pip and installing Phase 1 requirements..."
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
echo " [Nexus AIOS] Phase 1 Installation Complete!"
echo "==================================================================="
echo " To start Nexus AIOS on your phone:"
echo ""
echo " 1. Activate the environment:"
echo "    source .venv/bin/activate"
echo ""
echo " 2. (Optional) Set your Cloud LLM API key if using cloud models:"
echo "    export NEXUS_API_KEY=\"your_key_here\""
echo ""
echo " 3. Start the nexusd daemon in the background:"
echo "    python3 -m nexusd.main &"
echo ""
echo " 4. Launch the Nexus interactive terminal:"
echo "    python3 cli/nexus.py"
echo "==================================================================="
