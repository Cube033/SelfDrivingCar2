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

    # --- left grid
    if state.grid_occ and len(state.grid_occ) >= (state.grid_w * state.grid_h):
        cell = cfg.cell_px
        max_x = cfg.left_w - 1
        max_y = cfg.height - 1

        idx = 0
        for gy in range(state.grid_h):
            y = gy * cell
            for gx in range(state.grid_w):
                x = gx * cell
                occ = int(state.grid_occ[idx])
                idx += 1
                if occ:
                    x1 = min(x + cell - 1, max_x)
                    y1 = min(y + cell - 1, max_y)
                    draw.rectangle([x, y, x1, y1], fill=fg)
    else:
        draw.text((2, 2), "NO GRID", font=font, fill=fg)

    # --- right panel
    mode = (state.mode_big or "?")[:2].upper()
    arm_txt = "ARM" if state.armed else "DIS"
    stop_txt = "STOP" if state.is_stop else "GO"

    # big mode (right side)
    draw.text((cfg.split_x + 44, 2), mode, font=font, fill=fg)

    # occupancy bars (L/C/R)
    if state.occ_left is not None and state.occ_center is not None and state.occ_right is not None:
        bar_x0 = cfg.split_x + 2
        bar_y0 = 2
        bar_h = 20
        bar_w = 8
        gap = 4

        vals = [state.occ_left, state.occ_center, state.occ_right]
        for i, v in enumerate(vals):
            v = max(0.0, min(1.0, float(v)))
            x0 = bar_x0 + i * (bar_w + gap)
            x1 = x0 + bar_w
            y1 = bar_y0 + bar_h
            y0 = y1 - int(bar_h * v)
            # outline
            draw.rectangle([x0, bar_y0, x1, y1], outline=fg)
            # fill
            if v > 0.0:
                draw.rectangle([x0 + 1, y0, x1 - 1, y1 - 1], fill=fg)
        draw.text((bar_x0, bar_y0 + bar_h + 2), "L C R", font=font, fill=fg)

    # message or status
    if state.message:
        lines = [s for s in state.message.split("\n") if s][:3]
        y = 28
        for line in lines:
            draw.text((cfg.split_x + 2, y), line[:9], font=font, fill=fg)
            y += 10
    else:
        draw.text((cfg.split_x + 2, 38), f"{arm_txt} {stop_txt}", font=font, fill=fg)

        parts = []
        if state.free_ratio is not None:
            parts.append(f"F:{state.free_ratio:.2f}")
        if state.closest_norm is not None:
            parts.append(f"C:{state.closest_norm:.2f}")
        if state.fps is not None:
            parts.append(f"{state.fps:.1f}fps")
        if parts:
            draw.text((cfg.split_x + 2, 50), " ".join(parts), font=font, fill=fg)

    return img
