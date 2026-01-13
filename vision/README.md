# Vision (Raspberry Pi AI Camera / IMX500)

This folder contains experiments and future perception modules for the RC Car project.

## Goals
1. Provide a safety layer: "free space ahead" / "stop" even for unknown objects.
2. Add optional semantics: detect known objects, pose, etc.
3. Keep camera code isolated from motor/steering until it is stable.

## Hardware / Software
- Raspberry Pi 5
- Raspberry Pi AI Camera (Sony IMX500)
- libcamera + rpicam-apps
- Picamera2 (Python)

## Quick start on Raspberry (recommended workflow)
1. Pull the repo on Raspberry:
   ```bash
   git pull