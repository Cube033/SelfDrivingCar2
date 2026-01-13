#!/usr/bin/env python3
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


def topk_classes(roi_map: np.ndarray, k: int = 3, ignore_zero: bool = True) -> List[Tuple[int, float]]:
    flat = roi_map.reshape(-1)
    if flat.size == 0:
        return []
    counts = np.bincount(flat)
    if ignore_zero and counts.size > 0:
        counts[0] = 0
    total = float(flat.size)
    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if counts[c] > 0]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk")
    p.add_argument("--print-every", type=int, default=10)
    p.add_argument("--roi-w", type=float, default=0.35)
    p.add_argument("--roi-h-bottom", type=float, default=0.35)
    p.add_argument("--floor-class", type=int, default=None)
    p.add_argument("--stop-threshold", type=float, default=0.35)
    p.add_argument("--ignore-zero", action="store_true", help="Ignore class 0 in top-k stats (recommended).")
    p.add_argument("--max-fps", type=float, default=0.0)
    return p.parse_args()


# Глобальные переменные, чтобы pre_callback мог писать, а main-loop печатать
_last_stats = {
    "frame": 0,
    "t0": time.time(),
    "top3": [],
    "dominant": -1,
    "dominant_ratio": 0.0,
    "free_ratio": None,
}


def main():
    args = parse_args()

    # 1) ВАЖНО: IMX500 создаётся ДО Picamera2
    imx500 = IMX500(args.model)

    # 2) Intrinsics — как в официальном примере
    intrinsics = imx500.network_intrinsics
    if not intrinsics:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "segmentation"
    elif intrinsics.task != "segmentation":
        raise RuntimeError("Network is not a segmentation task")

    intrinsics.update_with_defaults()

    # 3) ВАЖНО: Picamera2 открываем через imx500.camera_num
    picam2 = Picamera2(imx500.camera_num)

    # В консольном режиме preview не нужен, но конфиг нужен
    config = picam2.create_preview_configuration(
        controls={"FrameRate": intrinsics.inference_rate},
        buffer_count=12,
    )

    imx500.show_network_fw_progress_bar()

    # pre_callback вызывается на каждый кадр
    roi: Optional[Roi] = None

    def on_frame(request: CompletedRequest):
        nonlocal roi

        _last_stats["frame"] += 1

        # Получаем mask (у segmentation_demo mask уже class-id карта)
        np_outputs = imx500.get_outputs(metadata=request.get_metadata())
        if np_outputs is None:
            return
        mask = np_outputs[0]
        if mask is None:
            return

        # ROI считаем один раз (маска в координатах input_size IMX500)
        if roi is None:
            input_w, input_h = imx500.get_input_size()
            roi = compute_roi(input_w, input_h, args.roi_w, args.roi_h_bottom)

        roi_map = mask[roi.y0:roi.y1, roi.x0:roi.x1]
        top3 = topk_classes(roi_map, k=3, ignore_zero=args.ignore_zero)
        dom_id = top3[0][0] if top3 else -1
        dom_ratio = top3[0][1] if top3 else 0.0

        _last_stats["top3"] = top3
        _last_stats["dominant"] = dom_id
        _last_stats["dominant_ratio"] = dom_ratio

        if args.floor_class is not None:
            _last_stats["free_ratio"] = float(np.mean(roi_map == args.floor_class))
        else:
            _last_stats["free_ratio"] = None

    picam2.pre_callback = on_frame

    # show_preview=False => отлично работает по SSH без DISPLAY
    picam2.start(config, show_preview=False)

    print("=== IMX500 segmentation score (AI runs on camera) ===")
    print(f"model: {args.model}")
    if args.floor_class is None:
        print("Run once to observe dominant class id on the FLOOR, then set --floor-class <id>.")
    else:
        print(f"floor_class={args.floor_class} stop_threshold={args.stop_threshold}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            frame = _last_stats["frame"]
            if frame > 0 and frame % args.print_every == 0:
                elapsed = time.time() - _last_stats["t0"]
                fps = frame / elapsed if elapsed > 0 else 0.0

                top3 = _last_stats["top3"]
                dom_id = _last_stats["dominant"]
                dom_ratio = _last_stats["dominant_ratio"]

                line = f"fps={fps:5.1f}  dominant={dom_id}({dom_ratio:.2f})  top3={top3}"

                if args.floor_class is not None:
                    free = _last_stats["free_ratio"] or 0.0
                    stop = free < args.stop_threshold
                    line += f"  FREE={free:.2f}  STOP={stop}"
                else:
                    line += "  (set --floor-class <id> to enable FREE/STOP)"

                print(line, flush=True)

                # чтобы не печатать одну и ту же строку много раз подряд на одном frame
                time.sleep(0.05)

            if args.max_fps and args.max_fps > 0:
                time.sleep(max(0.0, 1.0 / args.max_fps))
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()