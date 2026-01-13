#!/usr/bin/env python3
"""
Print segmentation-based free-space score from Raspberry Pi AI Camera (IMX500).

Workflow:
1) First run WITHOUT --floor-class.
   Point the camera mostly at the floor and watch which class_id dominates in ROI.
2) Run again WITH --floor-class <that_id>.
   Then the script prints FREE ratio and STOP/GO.

Example:
  python3 vision/demos/print_segmentation_score.py

Then:
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
        help="Path to .rpk IMX500 segmentation model",
    )
    p.add_argument(
        "--floor-class",
        type=int,
        default=None,
        help="Class id considered 'free space' (e.g., floor/road). "
             "First run without it to discover a good id.",
    )
    p.add_argument(
        "--stop-threshold",
        type=float,
        default=0.35,
        help="STOP if free_space_ratio < stop_threshold (only when --floor-class is set).",
    )
    p.add_argument(
        "--roi-x",
        type=float,
        default=0.5,
        help="ROI center X as fraction of width (0..1). Default 0.5 (center).",
    )
    p.add_argument(
        "--roi-w",
        type=float,
        default=0.35,
        help="ROI width as fraction of width (0..1). Default 0.35.",
    )
    p.add_argument(
        "--roi-y-bottom",
        type=float,
        default=0.35,
        help="ROI height from bottom as fraction of height (0..1). Default 0.35.",
    )
    p.add_argument(
        "--print-every",
        type=int,
        default=10,
        help="Print every N frames. Default 10.",
    )
    p.add_argument(
        "--max-fps",
        type=float,
        default=0.0,
        help="If >0, limits print loop roughly to this FPS (sleep).",
    )
    return p.parse_args()


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def compute_roi(width: int, height: int, roi_x: float, roi_w: float, roi_y_bottom: float) -> Roi:
    roi_w_px = int(width * roi_w)
    cx = int(width * roi_x)
    x0 = clamp(cx - roi_w_px // 2, 0, width - 1)
    x1 = clamp(cx + roi_w_px // 2, 1, width)

    roi_h_px = int(height * roi_y_bottom)
    y1 = height
    y0 = clamp(height - roi_h_px, 0, height - 1)
    return Roi(x0=x0, y0=y0, x1=x1, y1=y1)


def outputs_to_class_map(outputs: List[np.ndarray]) -> np.ndarray:
    """
    Convert IMX500 segmentation network outputs to a 2D class-id map.

    The exact tensor shape can vary by model/export.
    We try to handle common cases:
    - (H, W) already class ids
    - (H, W, C) logits/probabilities -> argmax over C
    - (1, H, W) -> squeeze batch
    - (1, H, W, C) -> squeeze batch -> argmax
    """
    if not outputs:
        raise RuntimeError("No outputs returned by IMX500.get_outputs().")

    t = outputs[0]

    # Remove batch dimension if present
    if t.ndim == 4 and t.shape[0] == 1:
        t = t[0]
    if t.ndim == 3 and t.shape[0] == 1:
        t = t[0]

    # Now interpret
    if t.ndim == 2:
        # Already class ids
        class_map = t
    elif t.ndim == 3:
        # (H, W, C) -> argmax over C
        class_map = np.argmax(t, axis=-1)
    else:
        raise RuntimeError(f"Unexpected output tensor shape: {outputs[0].shape}")

    return class_map.astype(np.int32, copy=False)


def topk_classes(roi_map: np.ndarray, k: int = 3) -> List[Tuple[int, float]]:
    flat = roi_map.reshape(-1)
    if flat.size == 0:
        return []
    counts = np.bincount(flat)
    if counts.size == 0:
        return []
    total = float(flat.size)
    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if counts[c] > 0]


def main() -> None:
    args = parse_args()

    # Picamera2 + IMX500 setup
    picam2 = Picamera2()

    # Configure a small main stream (we only need metadata + reasonable speed)
    config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "XRGB8888"})
    picam2.configure(config)

    imx500 = IMX500(args.model)
    imx500.show_network_fw_progress_bar()

    picam2.start()

    # Determine ROI based on current stream size
    stream_cfg = picam2.camera_configuration()["main"]
    width, height = stream_cfg["size"]
    roi = compute_roi(width, height, args.roi_x, args.roi_w, args.roi_y_bottom)

    print("=== IMX500 Segmentation -> Free-space console demo ===")
    print(f"Model: {args.model}")
    print(f"Main stream: {width}x{height}")
    print(f"ROI: x[{roi.x0}:{roi.x1}] y[{roi.y0}:{roi.y1}] (bottom-center)")
    if args.floor_class is None:
        print("floor_class: NOT SET (first run mode).")
        print("Tip: point camera mostly at the floor; choose dominant class_id and rerun with --floor-class <id>.")
    else:
        print(f"floor_class: {args.floor_class}")
        print(f"stop_threshold: {args.stop_threshold}")

    frame = 0
    t0 = time.time()

    try:
        while True:
            # Capture only metadata (cheap); outputs are embedded there
            metadata = picam2.capture_metadata()
            outputs = imx500.get_outputs(metadata, add_batch=True)
            if outputs is None:
                # Sometimes first frames have no outputs; skip
                continue

            class_map = outputs_to_class_map(outputs)

            roi_map = class_map[roi.y0:roi.y1, roi.x0:roi.x1]
            top3 = topk_classes(roi_map, k=3)

            frame += 1
            if frame % args.print_every == 0:
                elapsed = time.time() - t0
                fps = frame / elapsed if elapsed > 0 else 0.0

                # Dominant class in ROI
                dominant_id = top3[0][0] if top3 else -1
                dominant_ratio = top3[0][1] if top3 else 0.0

                line = f"fps={fps:5.1f}  dominant={dominant_id}({dominant_ratio:.2f})  top3={top3}"

                if args.floor_class is not None:
                    free_ratio = float(np.mean(roi_map == args.floor_class))
                    stop = free_ratio < args.stop_threshold
                    line += f"  FREE={free_ratio:.2f}  STOP={stop}"

                print(line, flush=True)

            if args.max_fps and args.max_fps > 0:
                time.sleep(max(0.0, (1.0 / args.max_fps)))

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()