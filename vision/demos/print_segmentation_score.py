#!/usr/bin/env python3
import time

from vision.segscore.cli import parse_config
from vision.segscore.imx500_runtime import Imx500SegScoreRunner


def main():
    cfg = parse_config()

    runner = Imx500SegScoreRunner(
        model_path=cfg.model,
        roi_w=cfg.roi_w,
        roi_h_bottom=cfg.roi_h_bottom,
        ignore_zero=cfg.ignore_zero,
        debug=cfg.debug,
        stop_cfg=cfg.stop_cfg,
    )

    runner.start()

    print("=== IMX500 segmentation score (AI runs on camera) ===")
    print(f"model: {cfg.model}")
    print(
        f"ROI: w={cfg.roi_w:.2f} h_bottom={cfg.roi_h_bottom:.2f} "
        f"bg_class={cfg.stop_cfg.bg_class} stop<{cfg.stop_cfg.stop_threshold:.2f} go>={cfg.stop_cfg.go_threshold:.2f} "
        f"ema_alpha={cfg.stop_cfg.ema_alpha:.2f} "
        f"min_stop_frames={cfg.stop_cfg.min_stop_frames} min_go_frames={cfg.stop_cfg.min_go_frames}"
    )
    if cfg.stop_cfg.hard_stop_class is not None:
        print(f"hard_stop: class={cfg.stop_cfg.hard_stop_class} ratio>={cfg.stop_cfg.hard_stop_ratio:.2f}")
    print("Press Ctrl+C to stop.\n")

    last_printed_frame = 0
    debug_every = max(1, cfg.print_every * 10)

    try:
        while True:
            st = runner.latest()
            if st is None:
                time.sleep(0.01)
                continue

            if st.frame != last_printed_frame and st.frame % cfg.print_every == 0:
                last_printed_frame = st.frame

                line = (
                    f"fps={st.fps:5.1f}  "
                    f"dominant={st.dominant}({st.dominant_ratio:.2f})  "
                    f"top3={st.top3}  "
                    f"FREE={st.free_ratio:.2f}  W_FREE={st.weighted_free:.2f}  "
                    f"CLOSE={st.closest_norm:.2f}  "
                    f"OCC L/C/R={st.occ_left:.2f}/{st.occ_center:.2f}/{st.occ_right:.2f}  "
                    f"EMA={st.ema_free:.2f}  STOP={st.is_stopped}"
                )
                print(line, flush=True)

            if cfg.debug and st.frame % debug_every == 0 and st.frame != 0:
                print(
                    f"[debug] cls_map shape=(?, ?) dtype={st.mask_dtype} "
                    f"uniq_count={st.uniq_count} uniq_head={st.uniq_head}",
                    flush=True,
                )

            if cfg.max_fps and cfg.max_fps > 0:
                time.sleep(max(0.0, 1.0 / cfg.max_fps))
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        runner.stop()


if __name__ == "__main__":
    main()
