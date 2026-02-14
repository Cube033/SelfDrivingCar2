from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time


@dataclass
class UltrasonicReading:
    raw_cm: Optional[float]
    filtered_cm: Optional[float]
    is_stop: bool
    is_valid: bool
    ts: float


class UltrasonicFilter:
    def __init__(
        self,
        *,
        stop_cm: float = 35.0,
        go_cm: float = 45.0,
        ema_alpha: float = 0.3,
        min_cm: float = 2.0,
        max_cm: float = 400.0,
        stale_sec: float = 0.5,
    ):
        self.stop_cm = float(stop_cm)
        self.go_cm = float(go_cm)
        self.ema_alpha = float(ema_alpha)
        self.min_cm = float(min_cm)
        self.max_cm = float(max_cm)
        self.stale_sec = float(stale_sec)

        self._ema: Optional[float] = None
        self._is_stop = True
        self._last_ts: float = 0.0

    def update(self, raw_cm: Optional[float], ts: Optional[float] = None) -> UltrasonicReading:
        now = time.time() if ts is None else float(ts)
        is_valid = False

        if raw_cm is not None and self.min_cm <= raw_cm <= self.max_cm:
            is_valid = True
            self._last_ts = now
            if self._ema is None:
                self._ema = raw_cm
            else:
                a = self.ema_alpha
                self._ema = (a * raw_cm) + ((1.0 - a) * self._ema)

        # stale data -> treat as invalid
        if (now - self._last_ts) > self.stale_sec:
            is_valid = False

        filtered = self._ema if is_valid else None

        # hysteresis on filtered value when valid
        if filtered is not None:
            if self._is_stop:
                if filtered >= self.go_cm:
                    self._is_stop = False
            else:
                if filtered <= self.stop_cm:
                    self._is_stop = True

        return UltrasonicReading(
            raw_cm=raw_cm if is_valid else None,
            filtered_cm=filtered,
            is_stop=self._is_stop,
            is_valid=is_valid,
            ts=now,
        )
