import time
from dataclasses import dataclass
from typing import Optional, List, Tuple, Callable

import numpy as np
from picamera2 import Picamera2, CompletedRequest
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics

from .roi import Roi, compute_roi
from .stats import topk_classes, safe_class_map, StopDecider, StopLogicConfig


@dataclass
class FrameStats:
    frame: int
    fps: float
    roi: Roi
    top3: List[Tuple[int, float]]
    dominant: int
    dominant_ratio: float
    free_ratio: float
    ema_free: float
    is_stopped: bool
    mask_dtype: str
    uniq_head: List[int]
    uniq_count: int


class Imx500SegScoreRunner:
    def __init__(
        self,
        model_path: str,
        roi_w: float,
        roi_h_bottom: float,
        ignore_zero: bool,
        debug: bool,
        stop_cfg: StopLogicConfig,
    ):
        self.model_path = model_path
        self.roi_w = roi_w
        self.roi_h_bottom = roi_h_bottom
        self.ignore_zero = ignore_zero
        self.debug = debug
        self.stop_decider = StopDecider(stop_cfg)

        self._imx500: Optional[IMX500] = None
        self._picam2: Optional[Picamera2] = None
        self._roi: Optional[Roi] = None

        self._frame = 0
        self._t0 = time.time()

        # latest stats (written by pre_callback)
        self._latest: Optional[FrameStats] = None

    def start(self):
        # 1) IMX500 must be created before Picamera2
        self._imx500 = IMX500(self.model_path)

        intr = self._imx500.network_intrinsics
        if not intr:
            intr = NetworkIntrinsics()
            intr.task = "segmentation"
        elif intr.task != "segmentation":
            raise RuntimeError("Network is not a segmentation task")
        intr.update_with_defaults()

        # 2) Picamera2 for that camera
        self._picam2 = Picamera2(self._imx500.camera_num)

        cfg = self._picam2.create_preview_configuration(
            controls={"FrameRate": intr.inference_rate},
            buffer_count=12,
        )

        self._imx500.show_network_fw_progress_bar()

        def on_frame(request: CompletedRequest):
            self._frame += 1
            frame = self._frame

            np_outputs = self._imx500.get_outputs(metadata=request.get_metadata())
            if not np_outputs:
                return
            mask = np_outputs[0]
            if mask is None:
                return

            cls_map = safe_class_map(mask)

            if self._roi is None:
                input_w, input_h = self._imx500.get_input_size()
                self._roi = compute_roi(input_w, input_h, self.roi_w, self.roi_h_bottom)

            r = self._roi
            roi_map = cls_map[r.y0:r.y1, r.x0:r.x1]

            # top-k
            top3 = topk_classes(roi_map, k=3, ignore_zero=self.ignore_zero)
            dom_id = top3[0][0] if top3 else -1
            dom_ratio = top3[0][1] if top3 else 0.0

            # free ratio + ema + stop
            is_stopped, ema_free = self.stop_decider.update(roi_map, top3)
            free_ratio = float(np.mean(roi_map == self.stop_decider.cfg.bg_class)) if roi_map.size else 0.0

            elapsed = time.time() - self._t0
            fps = frame / elapsed if elapsed > 0 else 0.0

            uniq = np.unique(cls_map)
            uniq_head = [int(x) for x in uniq[:10]]
            uniq_count = int(len(uniq))

            self._latest = FrameStats(
                frame=frame,
                fps=fps,
                roi=r,
                top3=top3,
                dominant=dom_id,
                dominant_ratio=dom_ratio,
                free_ratio=free_ratio,
                ema_free=float(ema_free if ema_free is not None else free_ratio),
                is_stopped=bool(is_stopped),
                mask_dtype=str(cls_map.dtype),
                uniq_head=uniq_head,
                uniq_count=uniq_count,
            )

        self._picam2.pre_callback = on_frame
        self._picam2.start(cfg, show_preview=False)

    def stop(self):
        if self._picam2 is not None:
            self._picam2.stop()

    def latest(self) -> Optional[FrameStats]:
        return self._latest