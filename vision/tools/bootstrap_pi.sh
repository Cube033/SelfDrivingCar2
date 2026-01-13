#!/usr/bin/env bash
set -euo pipefail

echo "[bootstrap] Installing packages..."
sudo apt update
sudo apt install -y imx500-all python3-opencv python3-munkres

echo "[bootstrap] Making scripts executable (chmod +x)..."
chmod +x vision/demos/*.sh 2>/dev/null || true
chmod +x vision/tools/*.sh 2>/dev/null || true

echo "[bootstrap] Checking IMX500 model zoo..."
if [ ! -d "/usr/share/imx500-models" ]; then
  echo "[bootstrap] ERROR: /usr/share/imx500-models not found"
  echo "Try: sudo apt install -y imx500-all"
  exit 1
fi

echo "[bootstrap] Done."
echo "Try running: ./vision/demos/run_imx500_segmentation.sh"