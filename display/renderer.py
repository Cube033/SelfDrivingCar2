from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from PIL import Image, ImageDraw, ImageFont

from .models import DisplayState


@dataclass(frozen=True)
class RenderConfig:
    width: int = 128
    height: int = 64

    # split: left 64x64 grid + right 64px text panel
    left_w: int = 64
    split_x: int = 64

    # grid scaling: 32x32 => 2px cell => 64x64
    grid_w: int = 32
    grid_h: int = 32
    cell_px: int = 2

    invert: bool = False


def _font() -> ImageFont.ImageFont:
    return ImageFont.load_default()


def render(state: DisplayState, cfg: RenderConfig = RenderConfig()) -> Image.Image:
    bg = 0 if not cfg.invert else 1
    fg = 1 if not cfg.invert else 0

    img = Image.new("1", (cfg.width, cfg.height), bg)
    draw = ImageDraw.Draw(img)
    font = _font()

    # split line
    draw.line([(cfg.split_x, 0), (cfg.split_x, cfg.height - 1)], fill=fg)

    # --- left grid (use top 48px for grid)
    if state.grid_occ and len(state.grid_occ) >= (state.grid_w * state.grid_h):
        cell = cfg.cell_px
        max_x = cfg.left_w - 1
        grid_area_h = 48
        max_y = grid_area_h - 1

        # show bottom part of grid (closest area) to fit 48px height
        grid_rows = min(state.grid_h, max_y // cell + 1)
        start_row = max(0, state.grid_h - grid_rows)

        for gy in range(grid_rows):
            src_y = start_row + gy
            y = gy * cell
            for gx in range(state.grid_w):
                x = gx * cell
                idx = (src_y * state.grid_w) + gx
                occ = int(state.grid_occ[idx])
                if occ:
                    x1 = min(x + cell - 1, max_x)
                    y1 = min(y + cell - 1, max_y)
                    draw.rectangle([x, y, x1, y1], fill=fg)
    else:
        left_msg = "NO GRID"
        if state.message and "VISION" in state.message.upper():
            left_msg = "NO VISION"
        draw.text((2, 2), left_msg, font=font, fill=fg)

    # --- right panel
    mode = (state.mode_big or "?")[:2].upper()
    arm_txt = "ARM" if state.armed else "DIS"
    stop_txt = "STOP" if state.is_stop else "GO"

    # right panel layout (top 48px)
    if state.message:
        lines = [s for s in state.message.split("\n") if s][:3]
        y = 6
        for line in lines:
            draw.text((cfg.split_x + 2, y), line[:10], font=font, fill=fg)
            y += 10
    else:
        # top status line: mode + arm/stop
        draw.text((cfg.split_x + 2, 0), f"{mode} {arm_txt[:3]} {stop_txt}", font=font, fill=fg)

        # occupancy bars (L/C/R)
        if state.occ_left is not None and state.occ_center is not None and state.occ_right is not None:
            bar_x0 = cfg.split_x + 6
            bar_y0 = 12
            bar_h = 22
            bar_w = 8
            gap = 4

            vals = [state.occ_left, state.occ_center, state.occ_right]
            for i, v in enumerate(vals):
                v = max(0.0, min(1.0, float(v)))
                x0 = bar_x0 + i * (bar_w + gap)
                x1 = x0 + bar_w
                y1 = bar_y0 + bar_h
                y0 = y1 - int(bar_h * v)
                draw.rectangle([x0, bar_y0, x1, y1], outline=fg)
                if v > 0.0:
                    draw.rectangle([x0 + 1, y0, x1 - 1, y1 - 1], fill=fg)
            draw.text((bar_x0, bar_y0 + bar_h + 2), "L C R", font=font, fill=fg)

    # bottom metrics row (full width, fixed positions)
    # Use placeholders to keep layout stable.
    d_txt = "--"
    if state.distance_cm is not None:
        d_txt = f"{state.distance_cm:3.0f}"
    f_txt = "--"
    if state.free_ratio is not None:
        f_txt = f"{state.free_ratio*100:3.0f}"
    c_txt = "--"
    if state.closest_norm is not None:
        c_txt = f"{state.closest_norm*100:3.0f}"

    y_metrics = 52
    draw.text((2, y_metrics), f"D:{d_txt}", font=font, fill=fg)
    draw.text((44, y_metrics), f"F:{f_txt}", font=font, fill=fg)
    draw.text((86, y_metrics), f"C:{c_txt}", font=font, fill=fg)

    return img
