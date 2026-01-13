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


def topk_classes_int(roi_map: np.ndarray, k: int = 3, ignore_zero: bool = True) -> List[Tuple[int, float]]:
    """
    roi_map must contain integer class ids.
    Returns [(class_id, ratio), ...] sorted by ratio desc.
    """
    flat = roi_map.reshape(-1)
    if flat.size == 0:
        return []
    # ensure int for bincount
    flat = flat.astype(np.int32, copy=False)
    counts = np.bincount(flat)
    if ignore_zero and counts.size > 0:
        counts[0] = 0
    total = float(flat.size)
    if counts.size == 0:
        return []
    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if counts[c] > 0]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk")
    p.add_argument("--print-every", type=int, default=10)
    p.add_argument("--roi-w", type=float, default=0.35)
    p.add_argument("--roi-h-bottom", type=float, default=0.35)

    # New naming: background class (default 0)
    p.add_argument("--bg-class", type=int, default=0, help="Class id considered as FREE/background. Default: 0")

    # Backward-compatible alias (your old flag name)
    p.add_argument("--floor-class", type=int, default=None,
                   help="Alias for --bg-class (kept for compatibility).")

    # Thresholds
    p.add_argument("--stop-threshold", type=float, default=0.90,
                   help="Enter STOP if FREE(ema) < stop_threshold.")
    p.add_argument("--go-threshold", type=float, default=0.94,
                   help="Exit STOP if FREE(ema) >= go_threshold (hysteresis).")

    # Filtering
    p.add_argument("--ema-alpha", type=float, default=0.2,
                   help="EMA alpha for FREE smoothing. 0 disables EMA (raw only).")
    p.add_argument("--min-stop-frames", type=int, default=2,
                   help="Need this many consecutive 'stop' decisions before switching into STOP.")
    p.add_argument("--min-go-frames", type=int, default=4,
                   help="Need this many consecutive 'go' decisions before switching out of STOP.")

    p.add_argument("--ignore-zero", action="store_true",
                   help="Ignore class 0 in top-k stats (recommended).")

    p.add_argument("--debug", action="store_true")
    p.add_argument("--max-fps", type=float, default=0.0)
    return p.parse_args()


def main():
    args = parse_args()

    # Backward compat: if --floor-class passed, it overrides bg-class
    if args.floor_class is not None:
        args.bg_class = args.floor_class

    if args.go_threshold < args.stop_threshold:
        raise ValueError("--go-threshold must be >= --stop-threshold (hysteresis)")

    imx500 = IMX500(args.model)

    intrinsics = imx500.network_intrinsics
    if not intrinsics:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "segmentation"
    elif intrinsics.task != "segmentation":
        raise RuntimeError("Network is not a segmentation task")

    intrinsics.update_with_defaults()

    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(
        controls={"FrameRate": intrinsics.inference_rate},
        buffer_count=12,
    )

    imx500.show_network_fw_progress_bar()

    roi: Optional[Roi] = None

    # Shared state
    frame_count = 0
    t0 = time.time()

    # Metrics
    free_raw = 0.0
    free_ema = None  # type: Optional[float]
    top3 = []
    dominant = -1
    dominant_ratio = 0.0

    # State machine
    stop_state = False
    stop_streak = 0
    go_streak = 0

    def on_frame(request: CompletedRequest):
        nonlocal roi, frame_count, free_raw, free_ema, top3, dominant, dominant_ratio
        nonlocal stop_state, stop_streak, go_streak

        frame_count += 1

        np_outputs = imx500.get_outputs(metadata=request.get_metadata())
        if np_outputs is None:
            return

        cls_map = np_outputs[0]
        if cls_map is None:
            return

        # Important: ensure integer class ids (some outputs may appear as float32)
        # In practice IMX500 segmentation is class-id map; casting is safe.
        if cls_map.dtype != np.uint8 and cls_map.dtype != np.int32 and cls_map.dtype != np.int64:
            cls_map = cls_map.astype(np.uint8, copy=False)

        if roi is None:
            input_w, input_h = imx500.get_input_size()
            roi = compute_roi(input_w, input_h, args.roi_w, args.roi_h_bottom)

        roi_map = cls_map[roi.y0:roi.y1, roi.x0:roi.x1]
        if roi_map.size == 0:
            return

        # Stats
        top3 = topk_classes_int(roi_map, k=3, ignore_zero=args.ignore_zero)
        dominant = top3[0][0] if top3 else -1
        dominant_ratio = top3[0][1] if top3 else 0.0

        # FREE = ratio of bg_class
        free_raw = float(np.mean(roi_map == args.bg_class))

        # EMA smoothing
        if args.ema_alpha and args.ema_alpha > 0:
            if free_ema is None:
                free_ema = free_raw
            else:
                a = float(args.ema_alpha)
                free_ema = a * free_raw + (1.0 - a) * free_ema
        else:
            free_ema = free_raw

        # Hysteresis + debounce
        # Decision inputs are based on EMA value
        f = float(free_ema) if free_ema is not None else free_raw

        want_stop = f < args.stop_threshold
        want_go = f >= args.go_threshold

        if stop_state:
            # currently stopped: wait for GO confirmation
            if want_go:
                go_streak += 1
                stop_streak = 0
                if go_streak >= args.min_go_frames:
                    stop_state = False
                    go_streak = 0
            else:
                go_streak = 0
        else:
            # currently going: wait for STOP confirmation
            if want_stop:
                stop_streak += 1
                go_streak = 0
                if stop_streak >= args.min_stop_frames:
                    stop_state = True
                    stop_streak = 0
            else:
                stop_streak = 0

        # Debug dump of unique classes occasionally
        if args.debug and (frame_count % (args.print_every * 10) == 0):
            uniq = np.unique(cls_map)
            head = uniq[:10].tolist()
            print(f"[debug] cls_map shape={cls_map.shape} dtype={cls_map.dtype} uniq_count={len(uniq)} uniq_head={head}", flush=True)

    picam2.pre_callback = on_frame
    picam2.start(config, show_preview=False)

    print("=== IMX500 segmentation score (AI runs on camera) ===")
    print(f"model: {args.model}")
    print(f"bg_class={args.bg_class} stop_threshold={args.stop_threshold} go_threshold={args.go_threshold}")
    print(f"ema_alpha={args.ema_alpha} min_stop_frames={args.min_stop_frames} min_go_frames={args.min_go_frames}")
    print("Press Ctrl+C to stop.", flush=True)

    last_print_frame = -1

    try:
        while True:
            if frame_count > 0 and (frame_count % args.print_every == 0) and frame_count != last_print_frame:
                last_print_frame = frame_count

                elapsed = time.time() - t0
                fps = frame_count / elapsed if elapsed > 0 else 0.0

                fraw = free_raw
                fema = free_ema if free_ema is not None else free_raw

                line = (
                    f"fps={fps:5.1f}  dominant={dominant}({dominant_ratio:.2f})  top3={top3}  "
                    f"FREE={fraw:.2f}  EMA={fema:.2f}  STOP={stop_state}"
                )
                print(line, flush=True)

            if args.max_fps and args.max_fps > 0:
                time.sleep(max(0.0, 1.0 / args.max_fps))
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            picam2.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()