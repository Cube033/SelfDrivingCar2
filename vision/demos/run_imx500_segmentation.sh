#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:0

python3 /home/cube033/picamera2/examples/imx500/imx500_segmentation_demo.py \
  --model /usr/share/imx500-models/imx500_network_deeplabv3plus.rpk