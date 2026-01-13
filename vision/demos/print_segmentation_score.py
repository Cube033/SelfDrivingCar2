#!/usr/bin/env python3
"""
IMX500 segmentation console demo (production-ish).

- Inference runs on IMX500 (camera). Raspberry reads outputs from metadata.
- Computes ROI (bottom-center) on the segmentation output and prints:
  - FPS
  - dominant class id + ratio
  - top-k classes
  - FREE ratio for a chosen floor class and STOP decision

Works over SSH (no DISPLAY), show_preview=False.

Notes:
- Some models return class-id map as float32 (e.g. 0.0, 9.0...) -> we cast safely.
- Some models may return logits/probabilities -> we argmax to class map.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List

import numpy as np

from picamera2 import Picamera2, CompletedRequest
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics


@dataclass(frozen=True)
class Roi:
    x0: int
    y0: int
    x1: int
    y1: int


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--roi-w", type=float, default=0.35)
    p.add_argument("--roi-h-bottom", type=float, default=0.35)
    p.add_argument("--print-every", type=int, default=10)
    p.add_argument("--floor-class", type=int, default=None)
    p.add_argument("--stop-threshold", type=float, default=0.35)
    p.add_argument("--ignore-zero", action="store_true", help="Ignore class 0 in top-k stats (recommended).")
    p.add_argument("--max-fps", type=float, default=0.0, help="If >0, limit processing/printing loop rate.")
    p.add_argument("--debug", action="store_true", help="Print extra debug (unique classes head) sometimes.")
    return p.parse_args()


def as_class_map(mask: np.ndarray) -> np.ndarray:
    """
    Normalize IMX500 output to int32 class-id map of shape (H, W).

    Supported:
    - (H, W) class ids (int/float)
    - (H, W, C) logits/probabilities -> argmax over C
    - (C, H, W) logits -> argmax over C
    - (1, ...) batch -> squeeze
    """
    if mask is None:
        raise RuntimeError("Mask is None")

    t = mask
    if t.ndim >= 3 and t.shape[0] == 1:
        t = np.squeeze(t, axis=0)

    if t.ndim == 2:
        # sometimes float32 values like 0.0, 9.0, ...
        return np.rint(t).astype(np.int32, copy=False)

    if t.ndim == 3:
        # Heuristic: if last dim looks like classes -> HWC
        if t.shape[-1] <= 512:
            return np.argmax(t, axis=-1).astype(np.int32, copy=False)
        # else assume CHW
        return np.argmax(t, axis=0).astype(np.int32, copy=False)

    raise RuntimeError(f"Unexpected mask shape: {t.shape}")


def topk_classes(roi_map_int: np.ndarray, k: int = 3, ignore_zero: bool = True) -> List[Tuple[int, float]]:
    flat = roi_map_int.reshape(-1)
    if flat.size == 0:
        return []

    # bincount needs non-negative ints
    flat = flat.astype(np.int64, copy=False)
    flat = flat[flat >= 0]
    if flat.size == 0:
        return []

    counts = np.bincount(flat)
    if ignore_zero and counts.size > 0:
        counts[0] = 0

    total = float(roi_map_int.size)
    if total <= 0:
        return []

    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if c < counts.size and counts[c] > 0]


def safe_stop(picam2: Picamera2) -> None:
    try:
        picam2.stop()
    except Exception:
        # avoid hanging on stop if callback thread crashed
        try:
            picam2.close()
        except Exception:
            pass


def main() -> int:
    args = parse_args()

    # IMX500 must be created BEFORE Picamera2
    imx500 = IMX500(args.model)

    intr = imx500.network_intrinsics
    if not intr:
        intr = NetworkIntrinsics()
        intr.task = "segmentation"
    elif intr.task != "segmentation":
        raise RuntimeError(f"Network task is '{intr.task}', expected 'segmentation'.")

    intr.update_with_defaults()

    picam2 = Picamera2(imx500.camera_num)

    config = picam2.create_preview_configuration(
        main={"size": (args.width, args.height)},
        controls={"FrameRate": intr.inference_rate},
        buffer_count=12,
    )

    imx500.show_network_fw_progress_bar()

    # Shared stats from callback -> printed in main loop
    stats = {
        "frame": 0,
        "t0": time.time(),
        "top3": [],
        "dominant": -1,
        "dominant_ratio": 0.0,
        "free_ratio": None,
        "roi": None,
        "last_err": None,
    }

    roi: Optional[Roi] = None

    def on_frame(request: CompletedRequest):
        nonlocal roi
        try:
            stats["frame"] += 1

            outputs = imx500.get_outputs(metadata=request.get_metadata())
            if not outputs:
                return

            mask_raw = outputs[0]
            cls_map = as_class_map(mask_raw)

            if roi is None:
                # ROI in IMX500 output coordinates (typically 320x320 for deeplab)
                h, w = cls_map.shape[:2]
                roi = compute_roi(w, h, args.roi_w, args.roi_h_bottom)
                stats["roi"] = roi

            roi_map = cls_map[roi.y0:roi.y1, roi.x0:roi.x1]

            top3 = topk_classes(roi_map, k=3, ignore_zero=args.ignore_zero)
            dom_id = top3[0][0] if top3 else -1
            dom_ratio = top3[0][1] if top3 else 0.0

            stats["top3"] = top3
            stats["dominant"] = dom_id
            stats["dominant_ratio"] = dom_ratio

            if args.floor_class is not None:
                stats["free_ratio"] = float(np.mean(roi_map == args.floor_class))
            else:
                stats["free_ratio"] = None

            if args.debug and stats["frame"] % (args.print_every * 20) == 0:
                uniq = np.unique(cls_map)
                print(f"[debug] cls_map shape={cls_map.shape} uniq_count={len(uniq)} uniq_head={uniq[:12]}", flush=True)

        except Exception as e:
            stats["last_err"] = repr(e)
            # Let main loop print the error once; keep callback running if possible.

    picam2.pre_callback = on_frame
    picam2.start(config, show_preview=False)

    print("=== IMX500 segmentation score (AI runs on camera) ===")
    print(f"model: {args.model}")
    if args.floor_class is None:
        print("Run once to observe dominant class id on the FLOOR, then set --floor-class <id>.")
    else:
        print(f"floor_class={args.floor_class} stop_threshold={args.stop_threshold}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            frame = stats["frame"]
            if frame > 0 and frame % args.print_every == 0:
                elapsed = time.time() - stats["t0"]
                fps = frame / elapsed if elapsed > 0 else 0.0

                top3 = stats["top3"]
                dom_id = stats["dominant"]
                dom_ratio = stats["dominant_ratio"]

                line = f"fps={fps:5.1f}  dominant={dom_id}({dom_ratio:.2f})  top3={top3}"

                if args.floor_class is not None:
                    free = stats["free_ratio"] if stats["free_ratio"] is not None else 0.0
                    stop = free < args.stop_threshold
                    line += f"  FREE={free:.2f}  STOP={stop}"
                else:
                    line += "  (set --floor-class <id> to enable FREE/STOP)"

                if stats["last_err"]:
                    line += f"  last_err={stats['last_err']}"
                    stats["last_err"] = None

                print(line, flush=True)
                time.sleep(0.05)

            if args.max_fps and args.max_fps > 0:
                time.sleep(max(0.0, 1.0 / args.max_fps))
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        safe_stop(picam2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())