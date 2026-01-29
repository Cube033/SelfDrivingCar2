from __future__ import annotations

import threading
import time
from typing import Optional

from .config import DisplayConfig
from .device import OLEDDevice
from .models import DisplayState
from .renderer import render


class DisplayService:
    """
    Background renderer for SH1106.
    Call update(...) from main loop.
    """

    def __init__(self, cfg: Optional[DisplayConfig] = None, enabled: bool = True):
        self.cfg = cfg or DisplayConfig()
        self.enabled = enabled

        self._dev: Optional[OLEDDevice] = None
        self._th: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        self._lock = threading.Lock()
        self._state = DisplayState()
        self._dirty = True

        self._last_draw = 0.0

    def start(self) -> None:
        if not self.enabled:
            return
        if self._th is not None:
            return

        self._dev = OLEDDevice(self.cfg)
        self._stop_evt.clear()

        self._th = threading.Thread(target=self._run, name="DisplayService", daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop_evt.set()
        th = self._th
        self._th = None
        if th:
            th.join(timeout=2.0)

        if self._dev:
            try:
                self._dev.clear()
            except Exception:
                pass
        self._dev = None

    def update(self, state: DisplayState) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._state = state
            self._dirty = True

    def _run(self) -> None:
        assert self._dev is not None

        max_fps = float(self.cfg.max_fps) if self.cfg.max_fps and self.cfg.max_fps > 0 else 10.0
        min_dt = 1.0 / max_fps

        while not self._stop_evt.is_set():
            now = time.time()
            if (now - self._last_draw) < min_dt:
                time.sleep(0.01)
                continue

            with self._lock:
                if not self._dirty:
                    st = None
                else:
                    st = self._state
                    self._dirty = False

            if st is None:
                time.sleep(0.01)
                continue

            try:
                img = render(st)
                self._dev.show(img)
                self._last_draw = time.time()
            except Exception as e:
                print("[DISPLAY] render/show failed:", e)
                time.sleep(0.2)