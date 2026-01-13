#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$HOME/picamera2/examples/imx500"
MODEL="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk"

cd "$DEMO_DIR"
DISPLAY="${DISPLAY:-:0}" python3 imx500_segmentation_demo.py --model "$MODEL"