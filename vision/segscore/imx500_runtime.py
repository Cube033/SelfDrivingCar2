from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import numpy as np
from picamera2 import Picamera2, CompletedRequest
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics
from PIL import Image

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
    weighted_free: float
    weighted_occ: float
    closest_row: int
    closest_norm: float
    closest_any_norm: float
    occ_left: float
    occ_center: float
    occ_right: float
    mask_dtype: str
    uniq_head: List[int]
    uniq_count: int

    # --- for OLED grid
    grid_w: int
    grid_h: int
    grid_occ: List[int]  # 0/1 length grid_w*grid_h


def _downsample_occupancy(
    roi_map: np.ndarray,
    *,
    grid_w: int,
    grid_h: int,
    bg_class: int,
    occ_threshold: float = 0.20,
) -> List[int]:
    """
    Convert ROI class-id map into occupancy grid.
    occupancy=1 means obstacle (not background) dominates the cell.

    occ_threshold:
      share of non-bg pixels to mark cell as obstacle.
    """
    if roi_map is None or roi_map.size == 0:
        return [0] * (grid_w * grid_h)

    h, w = roi_map.shape[:2]
    if h < grid_h or w < grid_w:
        # if ROI слишком маленький — fallback простым сэмплингом
        ys = np.linspace(0, h - 1, grid_h).astype(int)
        xs = np.linspace(0, w - 1, grid_w).astype(int)
        occ = []
        for y in ys:
            for x in xs:
                occ.append(1 if int(roi_map[y, x]) != bg_class else 0)
        return occ

    # режем так, чтобы делилось на grid
    bh = h // grid_h
    bw = w // grid_w
    hh = bh * grid_h
    ww = bw * grid_w
    cropped = roi_map[:hh, :ww]

    # obstacle mask
    obs = (cropped != bg_class).astype(np.uint8)

    # reshape blocks: (grid_h, bh, grid_w, bw)
    blocks = obs.reshape(grid_h, bh, grid_w, bw)

    # mean over each cell
    cell_mean = blocks.mean(axis=(1, 3))  # shape: (grid_h, grid_w)

    occ = (cell_mean >= occ_threshold).astype(np.uint8)
    return [int(x) for x in occ.reshape(-1)]


class Imx500SegScoreRunner:
    def __init__(
        self,
        model_path: str,
        roi_w: float,
        roi_h_bottom: float,
        ignore_zero: bool,
        debug: bool,
        stop_cfg: StopLogicConfig,
        *,
        grid_w: int = 32,
        grid_h: int = 32,
        occ_threshold: float = 0.20,
        snapshot_images: bool = False,
        snapshot_size: Tuple[int, int] = (320, 240),
        snapshot_max_fps: float = 5.0,
    ):
        self.model_path = model_path
        self.roi_w = roi_w
        self.roi_h_bottom = roi_h_bottom
        self.ignore_zero = ignore_zero
        self.debug = debug
        self.stop_decider = StopDecider(stop_cfg)

        self.grid_w = int(grid_w)
        self.grid_h = int(grid_h)
        self.occ_threshold = float(occ_threshold)
        self.snapshot_images = bool(snapshot_images)
        self.snapshot_size = (int(snapshot_size[0]), int(snapshot_size[1]))
        self.snapshot_max_fps = float(snapshot_max_fps)

        self._imx500: Optional[IMX500] = None
        self._picam2: Optional[Picamera2] = None
        self._roi: Optional[Roi] = None

        self._frame = 0
        self._t0 = time.time()

        # latest stats (written by pre_callback)
        self._latest: Optional[FrameStats] = None
        self._last_img: Optional[Image.Image] = None
        self._last_img_frame: int = -1
        self._last_img_ts: float = 0.0
        self._snapshot_request: bool = False

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

            # free ratio + ema + stop + proximity stats
            is_stopped, ema_free, prox = self.stop_decider.update(roi_map, top3)
            bg = self.stop_decider.cfg.bg_class
            free_ratio = float(np.mean(roi_map == bg)) if roi_map.size else 0.0

            # grid for OLED
            grid_occ = _downsample_occupancy(
                roi_map,
                grid_w=self.grid_w,
                grid_h=self.grid_h,
                bg_class=bg,
                occ_threshold=self.occ_threshold,
            )

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
                weighted_free=float(getattr(prox, "weighted_free", 0.0)),
                weighted_occ=float(getattr(prox, "weighted_occ", 0.0)),
                closest_row=int(getattr(prox, "closest_row", -1)),
                closest_norm=float(getattr(prox, "closest_norm", 0.0)),
                closest_any_norm=float(getattr(prox, "closest_any_norm", 0.0)),
                occ_left=float(getattr(prox, "occ_left", 0.0)),
                occ_center=float(getattr(prox, "occ_center", 0.0)),
                occ_right=float(getattr(prox, "occ_right", 0.0)),
                mask_dtype=str(cls_map.dtype),
                uniq_head=uniq_head,
                uniq_count=uniq_count,
                grid_w=self.grid_w,
                grid_h=self.grid_h,
                grid_occ=grid_occ,
            )

            # capture snapshot image (small) if enabled
            if self.snapshot_images:
                try:
                    min_dt = 0.0 if self._snapshot_request else (1.0 / max(1e-6, self.snapshot_max_fps))
                    if (time.time() - self._last_img_ts) >= min_dt or self._snapshot_request:
                        img = request.make_image("main")
                        if img is not None and hasattr(img, "resize"):
                            img = img.resize(self.snapshot_size, Image.BILINEAR)
                            self._last_img = img
                            self._last_img_frame = frame
                            self._last_img_ts = time.time()
                        self._snapshot_request = False
                except Exception:
                    pass

        self._picam2.pre_callback = on_frame
        self._picam2.start(cfg, show_preview=False)

    def stop(self):
        if self._picam2 is not None:
            self._picam2.stop()

    def latest(self) -> Optional[FrameStats]:
        return self._latest

    def get_snapshot_image(self) -> Optional[Image.Image]:
        return self._last_img

    def get_snapshot_frame(self) -> int:
        return self._last_img_frame

    def request_snapshot(self) -> None:
        self._snapshot_request = True
