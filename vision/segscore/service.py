from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from vision.segscore.cli import parse_config
from vision.segscore.imx500_runtime import Imx500SegScoreRunner
from vision.segscore.snapshot import SnapshotWriter


@dataclass
class SegScoreServiceConfig:
    snapshot_dir: str = "logs/vision"
    snapshot_enabled: bool = True
    snapshot_images: bool = True
    snapshot_image_w: int = 320
    snapshot_image_h: int = 240
    snapshot_image_max_fps: float = 5.0
    snapshot_on_stop: bool = True
    snapshot_on_turn: bool = False

    # OLED grid
    grid_w: int = 32
    grid_h: int = 32
    occ_threshold: float = 0.20


class SegScoreService:
    """
    High-level service around Imx500SegScoreRunner:
    - owns runner lifecycle
    - provides get()/should_stop()
    - can write snapshots on decision changes
    """

    def __init__(self, cfg: Optional[SegScoreServiceConfig] = None):
        self.cfg = cfg or SegScoreServiceConfig()

        self.cli_cfg = parse_config()
        self.runner = Imx500SegScoreRunner(
            model_path=self.cli_cfg.model,
            roi_w=self.cli_cfg.roi_w,
            roi_h_bottom=self.cli_cfg.roi_h_bottom,
            ignore_zero=self.cli_cfg.ignore_zero,
            debug=self.cli_cfg.debug,
            stop_cfg=self.cli_cfg.stop_cfg,
            grid_w=self.cfg.grid_w,
            grid_h=self.cfg.grid_h,
            occ_threshold=self.cfg.occ_threshold,
            snapshot_images=self.cfg.snapshot_images,
            snapshot_size=(self.cfg.snapshot_image_w, self.cfg.snapshot_image_h),
            snapshot_max_fps=self.cfg.snapshot_image_max_fps,
        )

        self.snap = SnapshotWriter(self.cfg.snapshot_dir) if self.cfg.snapshot_enabled else None
        self._last_stop: Optional[bool] = None

    def start(self) -> None:
        self.runner.start()

    def stop(self) -> None:
        try:
            self.runner.stop()
        finally:
            if self.snap:
                self.snap.close()

    def get(self):
        return self.runner.latest()

    def should_stop(self) -> bool:
        st = self.get()
        return bool(st.is_stopped) if st is not None else False

    def maybe_snapshot_on_change(self, event_prefix: str = "decision") -> Optional[bool]:
        """
        If STOP/GO decision changed, write a snapshot and return new decision.
        Otherwise return None.
        """
        st = self.get()
        if st is None:
            return None

        stop = bool(st.is_stopped)

        if self._last_stop is None:
            self._last_stop = stop
            if self.snap and self.cfg.snapshot_on_stop:
                if self.cfg.snapshot_images:
                    self.runner.request_snapshot()
                img = self.runner.get_snapshot_image() if self.cfg.snapshot_images else None
                self.snap.write(
                    f"{event_prefix}_init",
                    st,
                    image=img,
                    image_frame=self.runner.get_snapshot_frame(),
                )
            return stop

        if stop != self._last_stop:
            self._last_stop = stop
            if self.snap and self.cfg.snapshot_on_stop:
                if self.cfg.snapshot_images:
                    self.runner.request_snapshot()
                img = self.runner.get_snapshot_image() if self.cfg.snapshot_images else None
                self.snap.write(
                    f"{event_prefix}_change",
                    st,
                    image=img,
                    image_frame=self.runner.get_snapshot_frame(),
                )
            return stop

        return None

    def snapshot_event(self, event: str, state=None, **extra):
        if not self.snap:
            return
        if state is None:
            state = self.get()
        if state is None:
            return
        if self.cfg.snapshot_images:
            self.runner.request_snapshot()
        img = self.runner.get_snapshot_image() if self.cfg.snapshot_images else None
        self.snap.write(
            event,
            state,
            image=img,
            image_frame=self.runner.get_snapshot_frame(),
            **extra,
        )
