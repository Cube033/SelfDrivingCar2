#!/usr/bin/env python3
"""
IMX500 segmentation -> print tensor info + ROI stats + (optional) FREE/STOP.

This script DOES NOT run AI on Raspberry Pi CPU.
The neural network runs on the IMX500 inside the camera (model .rpk).
Raspberry Pi reads network outputs from frame metadata and does lightweight math.

Usage:
  # 1) Discover dominant class id on the floor (no FREE/STOP yet)
  python3 vision/demos/print_segmentation_score.py

  # 2) After you know floor class id:
  python3 vision/demos/print_segmentation_score.py --floor-class 7 --stop-threshold 0.35
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List

import numpy as np

from picamera2 import Picamera2
from picamera2.devices import IMX500


@dataclass(frozen=True)
class Roi:
    x0: int
    y0: int
    x1: int
    y1: int


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        default="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk",
        help="Path to IMX500 .rpk segmentation model",
    )
    p.add_argument(
        "--floor-class",
        type=int,
        default=None,
        help="Class id to treat as FREE space. First run without it to discover a good id.",
    )
    p.add_argument(
        "--stop-threshold",
        type=float,
        default=0.35,
        help="STOP if free_space_ratio < stop_threshold (only when --floor-class is set).",
    )
    p.add_argument("--width", type=int, default=640, help="Main stream width (default 640).")
    p.add_argument("--height", type=int, default=480, help="Main stream height (default 480).")
    p.add_argument("--roi-w", type=float, default=0.35, help="ROI width fraction (0..1).")
    p.add_argument("--roi-h-bottom", type=float, default=0.35, help="ROI height-from-bottom fraction (0..1).")
    p.add_argument("--print-every", type=int, default=10, help="Print every N frames.")
    p.add_argument("--debug-tensor", action="store_true", help="Print tensor info on startup and every print.")
    p.add_argument("--max-fps", type=float, default=0.0, help="If >0, sleep to limit loop rate.")
    return p.parse_args()


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def compute_roi(width: int, height: int, roi_w: float, roi_h_bottom: float) -> Roi:
    rw = int(width * roi_w)
    rh = int(height * roi_h_bottom)

    cx = width // 2
    x0 = clamp(cx - rw // 2, 0, width - 1)
    x1 = clamp(cx + rw // 2, 1, width)

    y1 = height
    y0 = clamp(height - rh, 0, height - 1)
    return Roi(x0=x0, y0=y0, x1=x1, y1=y1)


def tensor_info(t: np.ndarray) -> str:
    return f"shape={tuple(t.shape)} dtype={t.dtype} min={np.min(t):.3f} max={np.max(t):.3f}"


def outputs_to_class_map(outputs: List[np.ndarray]) -> np.ndarray:
    """
    Convert network outputs to a 2D class-id map.

    Common cases:
    - (H, W): already class ids
    - (H, W, C): logits/probabilities -> argmax over C
    - (C, H, W): logits -> argmax over C
    - With batch dimension: (1, ...): we squeeze it
    """
    if not outputs:
        raise RuntimeError("No outputs returned by IMX500.get_outputs().")

    t = outputs[0]

    # squeeze batch if present
    if t.ndim >= 3 and t.shape[0] == 1:
        t = np.squeeze(t, axis=0)

    if t.ndim == 2:
        return t.astype(np.int32, copy=False)

    if t.ndim == 3:
        # either (H, W, C) or (C, H, W)
        h, w = t.shape[0], t.shape[1]
        # heuristic: if last dim looks like classes (<=256 typically), treat as HWC
        if t.shape[-1] <= 512:
            return np.argmax(t, axis=-1).astype(np.int32, copy=False)
        # else treat as CHW
        return np.argmax(t, axis=0).astype(np.int32, copy=False)

    raise RuntimeError(f"Unexpected output tensor shape: {tuple(outputs[0].shape)}")


def topk_classes(roi_map: np.ndarray, k: int = 3) -> List[Tuple[int, float]]:
    flat = roi_map.reshape(-1)
    if flat.size == 0:
        return []
    counts = np.bincount(flat)
    total = float(flat.size)
    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if counts[c] > 0]


def main() -> None:
    args = parse_args()

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "XRGB8888"}
    )
    picam2.configure(config)

    imx500 = IMX500(args.model)
    imx500.show_network_fw_progress_bar()

    picam2.start()

    width, height = picam2.camera_configuration()["main"]["size"]
    roi = compute_roi(width, height, args.roi_w, args.roi_h_bottom)

    print("=== IMX500 Segmentation console demo ===")
    print(f"Model: {args.model}")
    print(f"Stream: {width}x{height}")
    print(f"ROI: x[{roi.x0}:{roi.x1}] y[{roi.y0}:{roi.y1}] (bottom-center)")
    print(f"floor_class: {args.floor_class}")
    if args.floor_class is not None:
        print(f"stop_threshold: {args.stop_threshold}")
    print("Press Ctrl+C to stop.")

    frame = 0
    t_start = time.time()
    printed_tensor_once = False

    try:
        while True:
            metadata = picam2.capture_metadata()
            outputs = imx500.get_outputs(metadata, add_batch=True)

            if outputs is None or len(outputs) == 0:
                continue

            # Print tensor info once right after outputs appear
            if args.debug_tensor and not printed_tensor_once:
                print("[tensor]", tensor_info(outputs[0]))
                printed_tensor_once = True

            class_map = outputs_to_class_map(outputs)
            roi_map = class_map[roi.y0:roi.y1, roi.x0:roi.x1]

            frame += 1
            if frame % args.print_every == 0:
                elapsed = time.time() - t_start
                fps = frame / elapsed if elapsed > 0 else 0.0

                top3 = topk_classes(roi_map, k=3)
                dom_id = top3[0][0] if top3 else -1
                dom_ratio = top3[0][1] if top3 else 0.0

                line = f"fps={fps:5.1f}  dominant={dom_id}({dom_ratio:.2f})  top3={top3}"

                if args.floor_class is not None:
                    free_ratio = float(np.mean(roi_map == args.floor_class))
                    stop = free_ratio < args.stop_threshold
                    line += f"  FREE={free_ratio:.2f}  STOP={stop}"
                else:
                    line += "  (set --floor-class <id> to enable FREE/STOP)"

                if args.debug_tensor:
                    line += f"  tensor={tensor_info(outputs[0])}"

                print(line, flush=True)

            if args.max_fps and args.max_fps > 0:
                time.sleep(max(0.0, 1.0 / args.max_fps))

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()