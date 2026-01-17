from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np


def safe_class_map(mask: np.ndarray) -> np.ndarray:
    """
    Ensure mask is integer (class-id map). Some pipelines can output float32.
    We round and cast safely.
    """
    if mask is None:
        return mask
    if np.issubdtype(mask.dtype, np.floating):
        # For class-id maps, values should be near integers
        return np.rint(mask).astype(np.int32, copy=False)
    if not np.issubdtype(mask.dtype, np.integer):
        return mask.astype(np.int32, copy=False)
    return mask


def topk_classes(roi_map: np.ndarray, k: int = 3, ignore_zero: bool = True) -> List[Tuple[int, float]]:
    """
    Returns list of (class_id, ratio) in ROI, sorted descending by ratio.
    """
    if roi_map is None:
        return []
    flat = roi_map.reshape(-1)
    if flat.size == 0:
        return []

    # bincount requires non-negative ints
    flat = safe_class_map(flat)
    flat = flat.astype(np.int32, copy=False)

    # Defensive: filter negatives (shouldn't exist)
    if np.any(flat < 0):
        flat = flat[flat >= 0]
        if flat.size == 0:
            return []

    counts = np.bincount(flat)
    if ignore_zero and counts.size > 0:
        counts[0] = 0

    total = float(flat.size)
    top = np.argsort(counts)[::-1][:k]
    return [(int(c), float(counts[c]) / total) for c in top if counts[c] > 0]


@dataclass
class StopLogicConfig:
    bg_class: int = 0                 # "free" class id
    stop_threshold: float = 0.90      # STOP when EMA < stop_threshold
    go_threshold: float = 0.96        # GO when EMA >= go_threshold
    ema_alpha: float = 0.20          # EMA smoothing (0..1)
    min_stop_frames: int = 2         # debounce into STOP
    min_go_frames: int = 6           # debounce into GO
    hard_stop_class: Optional[int] = None
    hard_stop_ratio: float = 0.05    # if class ratio >= this => immediate STOP


@dataclass
class StopLogicState:
    is_stopped: bool = False
    ema_free: Optional[float] = None
    stop_streak: int = 0
    go_streak: int = 0


class StopDecider:
    def __init__(self, cfg: StopLogicConfig):
        self.cfg = cfg
        self.state = StopLogicState()

    def reset(self):
        self.state = StopLogicState()

    def update(self, roi_map: np.ndarray, top3: List[Tuple[int, float]]) -> Tuple[bool, float]:
        """
        Returns (is_stopped, ema_free).
        """
        cfg = self.cfg
        st = self.state

        roi_map = safe_class_map(roi_map)

        # FREE ratio by bg_class
        if roi_map is None or roi_map.size == 0:
            free = 0.0
        else:
            free = float(np.mean(roi_map == cfg.bg_class))

        # EMA
        if st.ema_free is None:
            st.ema_free = free
        else:
            a = float(cfg.ema_alpha)
            st.ema_free = (a * free) + ((1.0 - a) * st.ema_free)

        # Hard stop (optional)
        if cfg.hard_stop_class is not None:
            ratio = 0.0
            for cid, r in top3:
                if cid == cfg.hard_stop_class:
                    ratio = r
                    break
            if ratio >= cfg.hard_stop_ratio:
                st.is_stopped = True
                st.stop_streak = cfg.min_stop_frames
                st.go_streak = 0
                return st.is_stopped, st.ema_free

        # Hysteresis with debouncing
        if st.is_stopped:
            if st.ema_free >= cfg.go_threshold:
                st.go_streak += 1
                if st.go_streak >= cfg.min_go_frames:
                    st.is_stopped = False
                    st.go_streak = 0
                    st.stop_streak = 0
            else:
                st.go_streak = 0
        else:
            if st.ema_free < cfg.stop_threshold:
                st.stop_streak += 1
                if st.stop_streak >= cfg.min_stop_frames:
                    st.is_stopped = True
                    st.stop_streak = 0
                    st.go_streak = 0
            else:
                st.stop_streak = 0

        return st.is_stopped, st.ema_free