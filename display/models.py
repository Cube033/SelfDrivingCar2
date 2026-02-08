from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class DisplayState:
    # left grid (occupancy) — 0/1 list of size grid_w * grid_h
    grid_occ: Optional[List[int]] = None
    grid_w: int = 32
    grid_h: int = 32

    # right panel
    mode_big: str = "?"
    armed: bool = False
    is_stop: bool = True

    # optional small stats
    free_ratio: Optional[float] = None
    fps: Optional[float] = None

    # occupancy (weighted) for left/center/right
    occ_left: Optional[float] = None
    occ_center: Optional[float] = None
    occ_right: Optional[float] = None
    closest_norm: Optional[float] = None

    # optional message (e.g., startup/shutdown)
    message: Optional[str] = None
