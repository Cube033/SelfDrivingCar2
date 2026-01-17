from dataclasses import dataclass
from typing import Optional
import argparse

from .stats import StopLogicConfig


@dataclass(frozen=True)
class AppConfig:
    model: str
    print_every: int
    roi_w: float
    roi_h_bottom: float
    ignore_zero: bool
    debug: bool
    max_fps: float

    # stop logic
    stop_cfg: StopLogicConfig


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="IMX500 segmentation ROI scoring + STOP/GO logic")

    p.add_argument("--model", default="/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk")
    p.add_argument("--print-every", type=int, default=10)

    p.add_argument("--roi-w", type=float, default=0.70)
    p.add_argument("--roi-h-bottom", type=float, default=0.45)

    p.add_argument("--ignore-zero", action="store_true", help="Ignore class 0 in top-k stats.")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--max-fps", type=float, default=0.0)

    # Stop logic
    p.add_argument("--bg-class", type=int, default=0, help="Class id treated as FREE/background.")
    p.add_argument("--stop-threshold", type=float, default=0.90)
    p.add_argument("--go-threshold", type=float, default=0.96)
    p.add_argument("--ema-alpha", type=float, default=0.20)
    p.add_argument("--min-stop-frames", type=int, default=2)
    p.add_argument("--min-go-frames", type=int, default=6)

    p.add_argument("--hard-stop-class", type=int, default=None)
    p.add_argument("--hard-stop-ratio", type=float, default=0.05)

    return p


def parse_config(argv=None) -> AppConfig:
    args = build_arg_parser().parse_args(argv)

    stop_cfg = StopLogicConfig(
        bg_class=args.bg_class,
        stop_threshold=args.stop_threshold,
        go_threshold=args.go_threshold,
        ema_alpha=args.ema_alpha,
        min_stop_frames=args.min_stop_frames,
        min_go_frames=args.min_go_frames,
        hard_stop_class=args.hard_stop_class,
        hard_stop_ratio=args.hard_stop_ratio,
    )

    return AppConfig(
        model=args.model,
        print_every=args.print_every,
        roi_w=args.roi_w,
        roi_h_bottom=args.roi_h_bottom,
        ignore_zero=args.ignore_zero,
        debug=args.debug,
        max_fps=args.max_fps,
        stop_cfg=stop_cfg,
    )