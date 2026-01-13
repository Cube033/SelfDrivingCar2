#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:0

rpicam-hello -t 0 \
  --viewfinder-width 1280 --viewfinder-height 720 \
  --post-process-file /usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json