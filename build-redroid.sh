#!/usr/bin/env bash
set -euo pipefail

# Build a custom redroid image with MindTheGapps and Magisk
# Uses third_party/redroid-script

ANDROID_VERSION="${1:-12.0.0}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$ROOT_DIR/third_party/redroid-script"

echo "==> Installing system dependencies..."
if command -v brew &>/dev/null; then
    brew list lzip &>/dev/null || brew install lzip
elif command -v apt-get &>/dev/null; then
    sudo apt-get install -y lzip
fi

# Use a virtualenv to avoid polluting global packages
VENV_DIR="$ROOT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtualenv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"

echo "==> Building redroid image (Android ${ANDROID_VERSION}) with MindTheGapps + Magisk..."
cd "$SCRIPT_DIR"
python3 redroid.py -a "$ANDROID_VERSION" -mtg -m

echo "==> Done! Run the container with:"
echo ""
echo "docker run -itd --rm --privileged \\"
echo "    -v ~/data:/data \\"
echo "    -p 5555:5555 \\"
echo "    redroid/redroid:${ANDROID_VERSION}_mindthegapps_magisk"
