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
    stop_threshold: float = 0.90      # STOP when EMA of weighted_free < stop_threshold
    go_threshold: float = 0.96        # GO when EMA of weighted_free >= go_threshold
    ema_alpha: float = 0.20          # EMA smoothing (0..1)
    min_stop_frames: int = 2         # debounce into STOP
    min_go_frames: int = 6           # debounce into GO
    hard_stop_class: Optional[int] = None
    hard_stop_ratio: float = 0.05    # if class ratio >= this => immediate STOP
    weight_power: float = 2.0        # y-weight exponent for bottom emphasis
    closest_stop: float = 0.82       # STOP if closest obstacle row >= this (0..1, 1=bottom)
    closest_go: float = 0.70         # GO if closest obstacle row < this (0..1)


@dataclass
class StopLogicState:
    is_stopped: bool = False
    ema_free: Optional[float] = None
    stop_streak: int = 0
    go_streak: int = 0


@dataclass
class ProximityStats:
    weighted_free: float
    weighted_occ: float
    closest_row: int
    closest_norm: float
    closest_any_norm: float
    occ_left: float
    occ_center: float
    occ_right: float


def _row_weights(h: int, power: float) -> np.ndarray:
    if h <= 0:
        return np.zeros((0,), dtype=np.float32)
    ys = (np.arange(h, dtype=np.float32) + 1.0) / float(h)
    return np.power(ys, float(power))


def _weighted_occ(obs: np.ndarray, weights: np.ndarray) -> float:
    if obs.size == 0:
        return 0.0
    w = weights.reshape(-1, 1)
    denom = float(w.sum())
    if denom <= 1e-9:
        return 0.0
    return float((obs.astype(np.float32) * w).sum() / denom)


def _zone_occ(obs: np.ndarray, weights: np.ndarray) -> Tuple[float, float, float]:
    h, w = obs.shape[:2]
    if w <= 0 or h <= 0:
        return 0.0, 0.0, 0.0
    x0 = w // 3
    x1 = (w * 2) // 3
    left = obs[:, :x0]
    center = obs[:, x0:x1]
    right = obs[:, x1:]
    wl = _weighted_occ(left, weights) if left.size else 0.0
    wc = _weighted_occ(center, weights) if center.size else 0.0
    wr = _weighted_occ(right, weights) if right.size else 0.0
    return wl, wc, wr


class StopDecider:
    def __init__(self, cfg: StopLogicConfig):
        self.cfg = cfg
        self.state = StopLogicState()

    def reset(self):
        self.state = StopLogicState()

    def update(self, roi_map: np.ndarray, top3: List[Tuple[int, float]]) -> Tuple[bool, float, ProximityStats]:
        """
        Returns (is_stopped, ema_free, proximity_stats).
        """
        cfg = self.cfg
        st = self.state

        roi_map = safe_class_map(roi_map)

        # FREE ratio by bg_class (unweighted, for reference/compat)
        if roi_map is None or roi_map.size == 0:
            free = 0.0
            weighted_free = 0.0
            weighted_occ = 0.0
            closest_row = -1
            closest_norm = 0.0
            closest_any_norm = 0.0
            occ_left = 0.0
            occ_center = 0.0
            occ_right = 0.0
        else:
            free = float(np.mean(roi_map == cfg.bg_class))
            obs = (roi_map != cfg.bg_class).astype(np.uint8)
            h = int(obs.shape[0])
            w = int(obs.shape[1]) if obs.ndim > 1 else 0
            weights = _row_weights(h, cfg.weight_power)
            weighted_occ = _weighted_occ(obs, weights)
            weighted_free = 1.0 - weighted_occ

            # closest obstacle in center band (for stop decision)
            x0 = w // 3 if w > 0 else 0
            x1 = (w * 2) // 3 if w > 0 else 0
            obs_center = obs[:, x0:x1] if w >= 3 else obs
            rows_center = np.where(obs_center.any(axis=1))[0]
            if rows_center.size > 0:
                closest_row = int(rows_center.max())
                closest_norm = float((closest_row + 1) / max(1, h))
            else:
                closest_row = -1
                closest_norm = 0.0

            # closest obstacle anywhere (debug)
            rows_any = np.where(obs.any(axis=1))[0]
            if rows_any.size > 0:
                closest_any_norm = float((int(rows_any.max()) + 1) / max(1, h))
            else:
                closest_any_norm = 0.0

            occ_left, occ_center, occ_right = _zone_occ(obs, weights)

        # EMA (weighted_free)
        if st.ema_free is None:
            st.ema_free = weighted_free
        else:
            a = float(cfg.ema_alpha)
            st.ema_free = (a * weighted_free) + ((1.0 - a) * st.ema_free)

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
                return st.is_stopped, st.ema_free, ProximityStats(
                    weighted_free=weighted_free,
                    weighted_occ=weighted_occ,
                    closest_row=closest_row,
                    closest_norm=closest_norm,
                    closest_any_norm=closest_any_norm,
                    occ_left=occ_left,
                    occ_center=occ_center,
                    occ_right=occ_right,
                )

        # Hysteresis with debouncing
        if st.is_stopped:
            if (st.ema_free >= cfg.go_threshold) and (closest_norm < cfg.closest_go):
                st.go_streak += 1
                if st.go_streak >= cfg.min_go_frames:
                    st.is_stopped = False
                    st.go_streak = 0
                    st.stop_streak = 0
            else:
                st.go_streak = 0
        else:
            if (st.ema_free < cfg.stop_threshold) or (closest_norm >= cfg.closest_stop):
                st.stop_streak += 1
                if st.stop_streak >= cfg.min_stop_frames:
                    st.is_stopped = True
                    st.stop_streak = 0
                    st.go_streak = 0
            else:
                st.stop_streak = 0

        return st.is_stopped, st.ema_free, ProximityStats(
            weighted_free=weighted_free,
            weighted_occ=weighted_occ,
            closest_row=closest_row,
            closest_norm=closest_norm,
            closest_any_norm=closest_any_norm,
            occ_left=occ_left,
            occ_center=occ_center,
            occ_right=occ_right,
        )
