import os
import sys
import time
import signal
import subprocess
import math
from collections import deque
import traceback

import config

from hardware.servo import Servo
from hardware.throttle import Throttle

from control.steering import SteeringMapper
from control.controller import SteeringController
from control.throttle_controller import ThrottleController
from control.arm_controller import ArmController

from input.keyboard_input import KeyboardSteeringInput
from input.keyboard_throttle_input import KeyboardThrottleInput
from input.dualshock_input import DualShockInput
from input.arduino_ultrasonic import UltrasonicSerialReader

from app.autopilot import Autopilot, AutoCruiseConfig, DriveMode
from app.event_logger import EventLogger

from vision.segscore.service import SegScoreService, SegScoreServiceConfig

# DISPLAY
from display import DisplayService, DisplayState, DisplayConfig
from control.ultrasonic import UltrasonicFilter


def gamepad_available(device_path: str) -> bool:
    return bool(device_path) and os.path.exists(device_path)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def move_towards(cur: float, target: float, max_delta: float) -> float:
    if cur < target:
        return min(cur + max_delta, target)
    if cur > target:
        return max(cur - max_delta, target)
    return cur


def _mode_to_big_label(ap_mode: str) -> str:
    """
    Маппинг режима на 1-2 символа справа на OLED.
    Я НЕ знаю точные значения ap.mode в твоём Autopilot, поэтому делаю безопасно:
    - если содержит 'auto' => 'A'
    - если содержит 'manual' => 'M'
    - иначе первые 2 символа.
    """
    m = (ap_mode or "").lower()
    if "auto" in m:
        return "A"
    if "man" in m:
        return "M"
    if len(ap_mode or "") == 0:
        return "?"
    return (ap_mode[:2]).upper()


def _trigger_shutdown(reason: str):
    try:
        subprocess.Popen(["/sbin/shutdown", "-h", "now", reason])
    except Exception as e:
        print("[WARN] Failed to trigger shutdown:", e)


def main():
    has_tty = sys.stdin.isatty()
    pid = os.getpid()

    # -----------------------
    # Logging
    # -----------------------
    logger = EventLogger(log_dir=getattr(config, "LOG_DIR", "logs"), version=getattr(config, "APP_VERSION", None))
    logger.write("boot", pid=pid, tty=has_tty)

    # -----------------------
    # Graceful shutdown
    # -----------------------
    stopping = {"flag": False}

    def request_stop(reason: str):
        if not stopping["flag"]:
            stopping["flag"] = True
            logger.write("stop_requested", reason=reason)

    def _sigterm(_signum, _frame):
        request_stop("SIGTERM")

    def _sigint(_signum, _frame):
        request_stop("SIGINT")

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigint)

    # -----------------------
    # Hardware
    # -----------------------
    servo = None
    throttle = None

    try:
        servo = Servo(
            channel=0,
            center_us=config.SERVO_CENTER_US,
            left_us=config.SERVO_LEFT_US,
            right_us=config.SERVO_RIGHT_US,
        )
        logger.write("servo_ok")
    except Exception as e:
        logger.write("servo_fail", err=str(e))
        print("[WARN] Servo not available:", e)

    try:
        throttle = Throttle(
            channel=1,
            neutral_us=config.THROTTLE_NEUTRAL_US,
            forward_us=config.THROTTLE_FORWARD_US,
            reverse_us=config.THROTTLE_REVERSE_US,
        )
        logger.write("throttle_ok")
    except Exception as e:
        logger.write("throttle_fail", err=str(e))
        print("[WARN] Throttle not available:", e)

    # -----------------------
    # Controllers
    # -----------------------
    steering_mapper = SteeringMapper(
        dead_zone=config.STEERING_DEAD_ZONE,
        invert=config.STEERING_INVERT,
    )
    steering = SteeringController(steering_mapper, servo) if servo else None

    motor = (
        ThrottleController(
            throttle,
            dead_zone=config.THROTTLE_DEAD_ZONE,
            invert=config.THROTTLE_INVERT,
        )
        if throttle
        else None
    )

    arm = ArmController()

    # -----------------------
    # Inputs
    # -----------------------
    keyboard_steer = None
    keyboard_throttle = None
    if config.KEYBOARD_ENABLED and has_tty:
        keyboard_steer = KeyboardSteeringInput(step=0.1)
        keyboard_throttle = KeyboardThrottleInput(step=0.1)
        logger.write("keyboard_enabled")
        print("[SYSTEM] Keyboard input enabled")
    else:
        logger.write("keyboard_disabled", reason="no_tty_or_disabled")
        print("[SYSTEM] Keyboard input disabled (no TTY or disabled)")

    gamepad = None
    gamepad_iter = None
    last_gamepad_check = 0.0
    GAMEPAD_RETRY_INTERVAL = 2.0

    if not config.GAMEPAD_ENABLED:
        logger.write("gamepad_disabled_in_config")
        print("[SYSTEM] Gamepad disabled in config")

    # -----------------------
    # Autopilot config
    # -----------------------
    ap = Autopilot(
        AutoCruiseConfig(
            speed_default=getattr(config, "AUTO_CRUISE_SPEED_DEFAULT", 0.15),
            speed_min=getattr(config, "AUTO_CRUISE_SPEED_MIN", 0.05),
            speed_max=getattr(config, "AUTO_CRUISE_SPEED_MAX", 0.35),
            speed_step=getattr(config, "AUTO_CRUISE_SPEED_STEP", 0.02),
        )
    )

    # -----------------------
    # Vision (IMX500 seg score)
    # -----------------------
    log_root = getattr(config, "LOG_DIR", "logs")

    vision = SegScoreService(
        SegScoreServiceConfig(
            snapshot_dir=os.path.join(log_root, "vision"),
            snapshot_enabled=getattr(config, "SNAPSHOT_ENABLED", True),
            snapshot_images=getattr(config, "SNAPSHOT_IMAGES", True),
            snapshot_image_w=getattr(config, "SNAPSHOT_IMAGE_W", 320),
            snapshot_image_h=getattr(config, "SNAPSHOT_IMAGE_H", 240),
            snapshot_image_max_fps=getattr(config, "SNAPSHOT_IMAGE_MAX_FPS", 5.0),
            snapshot_on_stop=getattr(config, "SNAPSHOT_ON_STOP_DECISION", True),
            snapshot_on_turn=getattr(config, "SNAPSHOT_ON_TURN_DECISION", False),
            version=getattr(config, "APP_VERSION", None),
        )
    )
    vision_ok = False
    last_vision_error = None
    try:
        vision.start()
        vision_ok = True
        logger.write("vision_started")
        print("[SYSTEM] Vision runner started")
    except Exception as e:
        last_vision_error = str(e)
        logger.write("vision_failed", err=str(e), tb=traceback.format_exc()[-2000:])
        print("[WARN] Vision start failed:", e)

    # -----------------------
    # Display
    # -----------------------
    display = None
    display_ok = False
    try:
        display = DisplayService(DisplayConfig(i2c_bus=1, i2c_address=0x3C, rotate=0, max_fps=10.0), enabled=True)
        display.start()
        display_ok = True
        logger.write("display_started")
        print("[SYSTEM] Display started")
        display.update(
            DisplayState(
                mode_big=_mode_to_big_label(ap.mode),
                armed=arm.armed,
                is_stop=True,
                message="RC CAR\nREADY",
            )
        )
    except Exception as e:
        logger.write("display_failed", err=str(e))
        print("[WARN] Display start failed:", e)

    # -----------------------
    # Ultrasonic (Arduino over USB serial)
    # -----------------------
    us_reader = None
    us_filter = UltrasonicFilter(
        stop_cm=getattr(config, "US_STOP_CM", 35.0),
        go_cm=getattr(config, "US_GO_CM", 45.0),
        ema_alpha=getattr(config, "US_EMA_ALPHA", 0.3),
        min_cm=getattr(config, "US_MIN_CM", 2.0),
        max_cm=getattr(config, "US_MAX_CM", 400.0),
        stale_sec=getattr(config, "US_STALE_SEC", 0.5),
    )
    if getattr(config, "US_ENABLED", True):
        try:
            us_reader = UltrasonicSerialReader(
                port=getattr(config, "US_SERIAL_PORT", "/dev/ttyACM0"),
                baud=getattr(config, "US_BAUD", 115200),
            )
            logger.write("ultrasonic_ok")
            print("[SYSTEM] Ultrasonic serial connected")
        except Exception as e:
            logger.write("ultrasonic_fail", err=str(e))
            print("[WARN] Ultrasonic serial failed:", e)

    # -----------------------
    # Camera history (FIFO) for turn decision
    # -----------------------
    cam_hist = deque()
    cam_hist_max = float(getattr(config, "CAM_HISTORY_MAX_SEC", 3.0))
    cam_hist_tau = float(getattr(config, "CAM_HISTORY_TAU_SEC", 1.0))
    cam_hist_min_w = float(getattr(config, "CAM_HISTORY_MIN_WEIGHT", 0.5))

    def _cam_hist_push(ts: float, left: float, center: float, right: float):
        cam_hist.append((ts, left, center, right))
        # drop old
        cutoff = ts - cam_hist_max
        while cam_hist and cam_hist[0][0] < cutoff:
            cam_hist.popleft()

    def _cam_hist_weighted(ts: float):
        if not cam_hist:
            return None, 0.0
        wl = wc = wr = 0.0
        wsum = 0.0
        for t, l, c, r in cam_hist:
            age = max(0.0, ts - t)
            w = math.exp(-age / max(1e-6, cam_hist_tau))
            wl += l * w
            wc += c * w
            wr += r * w
            wsum += w
        if wsum <= 1e-6:
            return None, 0.0
        return (wl / wsum, wc / wsum, wr / wsum), wsum

    logger.write("main_loop_start", mode=ap.mode, cruise_speed=ap.cruise_speed, vision_ok=vision_ok)
    print("[SYSTEM] Main loop started")

    last_stop = None
    last_turn_decision = None
    last_mode = ap.mode
    last_debug = 0.0
    last_loop_time = time.time()
    auto_turn_steer = 0.0
    shutdown_requested = False
    last_us_display_cm = None
    last_us_display_ts = 0.0

    last_manual_activity = time.time()
    MANUAL_ACTIVITY_TIMEOUT = getattr(config, "MANUAL_ACTIVITY_TIMEOUT", 999999.0)

    try:
        while not stopping["flag"]:
            now = time.time()
            dt = max(0.0, now - last_loop_time)
            last_loop_time = now

            steer = 0.0
            manual_throttle = 0.0
            mode_event = None
            cruise_delta = 0
            turn_decision = "none"
            turn_changed = False
            turn_occ_left = None
            turn_occ_center = None
            turn_occ_right = None

            # -----------------------
            # Ultrasonic read (Arduino)
            # -----------------------
            raw_cm = us_reader.read_cm() if us_reader else None
            us_state = us_filter.update(raw_cm, ts=now)
            if us_state.is_valid and us_state.filtered_cm is not None:
                last_us_display_cm = us_state.filtered_cm
                last_us_display_ts = now
            # If ultrasonic invalid, fall back to vision for forward stop
            us_stop = None if us_reader is None else (us_state.is_stop if us_state.is_valid else None)

            # -----------------------
            # Gamepad hot-plug
            # -----------------------
            if config.GAMEPAD_ENABLED:
                if gamepad is None and now - last_gamepad_check > GAMEPAD_RETRY_INTERVAL:
                    last_gamepad_check = now
                    if gamepad_available(config.GAMEPAD_DEVICE):
                        try:
                            gamepad = DualShockInput(config.GAMEPAD_DEVICE)
                            gamepad_iter = gamepad.values()  # IMPORTANT: create once!
                            logger.write("gamepad_connected")
                            print("[SYSTEM] Gamepad connected")
                        except Exception as e:
                            logger.write("gamepad_init_failed", err=str(e))
                            print("[WARN] Failed to init gamepad:", e)

                elif gamepad is not None and not gamepad_available(config.GAMEPAD_DEVICE):
                    logger.write("gamepad_disconnected")
                    print("[WARN] Gamepad disconnected")
                    gamepad = None
                    gamepad_iter = None

            # -----------------------
            # Read gamepad
            # -----------------------
            if gamepad_iter:
                try:
                    (
                        ls,
                        rs,
                        gp_throttle,
                        gp_arm_event,
                        mode_event,
                        cruise_delta,
                        shutdown_event,
                    ) = next(gamepad_iter)
                except StopIteration:
                    logger.write("gamepad_input_stopped")
                    print("[WARN] Gamepad input stopped (device lost)")
                    gamepad = None
                    gamepad_iter = None
                    continue

                steer = rs if abs(rs) > abs(ls) else ls
                manual_throttle = gp_throttle

                if abs(steer) > 0.02 or abs(manual_throttle) > 0.02 or gp_arm_event:
                    last_manual_activity = now

                if gp_arm_event == "arm":
                    arm.arm()
                    logger.write("arm", source="gamepad")
                elif gp_arm_event == "disarm":
                    arm.disarm()
                    logger.write("disarm", source="gamepad")

                if shutdown_event and not shutdown_requested:
                    shutdown_requested = True
                    logger.write("shutdown_requested", source="gamepad")
                    request_stop("shutdown_requested")
                    if display_ok and display:
                        display.update(
                            DisplayState(
                                mode_big=_mode_to_big_label(ap.mode),
                                armed=arm.armed,
                                is_stop=is_stop,
                                message="SHUTDOWN",
                            )
                        )
                    _trigger_shutdown("RC Car shutdown")

            # -----------------------
            # Keyboard (optional)
            # -----------------------
            if keyboard_steer and keyboard_throttle:
                ks = keyboard_steer.read()
                kt = keyboard_throttle.read()
                steer += ks
                manual_throttle += kt

                if abs(ks) > 0.0 or abs(kt) > 0.0 or keyboard_throttle.arm_event:
                    last_manual_activity = now

                if keyboard_throttle.arm_event == "arm":
                    arm.arm()
                    logger.write("arm", source="keyboard")
                elif keyboard_throttle.arm_event == "disarm":
                    arm.disarm()
                    logger.write("disarm", source="keyboard")

            # -----------------------
            # Mode + cruise updates
            # -----------------------
            if mode_event == "toggle_auto_cruise":
                ap.toggle_auto_cruise()
                logger.write("mode_change", mode=ap.mode, cruise_speed=ap.cruise_speed)

            if cruise_delta != 0:
                ap.apply_cruise_delta(cruise_delta)
                logger.write("cruise_speed", mode=ap.mode, cruise_speed=ap.cruise_speed, delta=cruise_delta)

            # -----------------------
            # Vision latest
            # -----------------------
            st = None
            try:
                st = vision.get() if vision_ok else None
                if vision_ok:
                    vision.maybe_snapshot_on_change(event_prefix="stopgo")
            except Exception as e:
                last_vision_error = str(e)
                logger.write("vision_runtime_error", err=str(e))
                st = None

            if st is None:
                vision_stop = bool(last_stop) if last_stop is not None else True
            else:
                vision_stop = bool(st.is_stopped)

            # forward motion: ultrasonic if valid, else camera
            is_stop = us_stop if us_stop is not None else vision_stop
            free = float(st.free_ratio) if st is not None else None
            ema = float(st.ema_free) if st is not None else None

            # log STOP edge
            if last_stop is None:
                last_stop = is_stop
            elif is_stop != last_stop:
                logger.write(
                    "stop_change",
                    stop=is_stop,
                    free=free,
                    ema=ema,
                    dominant=getattr(st, "dominant", None) if st else None,
                )
                last_stop = is_stop

            # -----------------------
            # Turn decision (camera, with FIFO history)
            # -----------------------
            center_thresh = getattr(config, "TURN_CENTER_THRESHOLD", 0.35)
            diff_thresh = getattr(config, "TURN_DIFF_THRESHOLD", 0.08)

            occ_left = occ_center = occ_right = None
            if st is not None:
                occ_left = float(getattr(st, "occ_left", 0.0))
                occ_center = float(getattr(st, "occ_center", 0.0))
                occ_right = float(getattr(st, "occ_right", 0.0))
                _cam_hist_push(now, occ_left, occ_center, occ_right)
            else:
                hist_vals, hist_w = _cam_hist_weighted(now)
                if hist_vals is not None and hist_w >= cam_hist_min_w:
                    occ_left, occ_center, occ_right = hist_vals

            if occ_left is not None and occ_center is not None and occ_right is not None:
                turn_occ_left, turn_occ_center, turn_occ_right = occ_left, occ_center, occ_right
                if occ_center >= float(center_thresh):
                    if (occ_left + diff_thresh) < occ_right:
                        turn_decision = "left"
                    elif (occ_right + diff_thresh) < occ_left:
                        turn_decision = "right"
                    else:
                        turn_decision = "none"
                else:
                    turn_decision = "none"

                if turn_decision != last_turn_decision:
                    last_turn_decision = turn_decision
                    turn_changed = True

            # -----------------------
            # Display update (always, even if vision is unavailable)
            # -----------------------
            if display_ok and display:
                try:
                    mode_big = _mode_to_big_label(ap.mode)
                    msg = None
                    if not vision_ok or st is None:
                        msg = "VISION\nERROR"
                    hold_sec = float(getattr(config, "US_DISPLAY_HOLD_SEC", 1.0))
                    display_cm = None
                    if last_us_display_cm is not None and (now - last_us_display_ts) <= hold_sec:
                        display_cm = last_us_display_cm
                    elif us_state.is_valid:
                        display_cm = us_state.filtered_cm

                    display.update(
                        DisplayState(
                            grid_occ=getattr(st, "grid_occ", None) if st is not None else None,
                            grid_w=getattr(st, "grid_w", 32) if st is not None else 32,
                            grid_h=getattr(st, "grid_h", 32) if st is not None else 32,
                            mode_big=mode_big,
                            armed=arm.armed,
                            is_stop=is_stop,
                            free_ratio=free if st is not None else None,
                            occ_left=getattr(st, "occ_left", None) if st is not None else None,
                            occ_center=getattr(st, "occ_center", None) if st is not None else None,
                            occ_right=getattr(st, "occ_right", None) if st is not None else None,
                            closest_norm=getattr(st, "closest_norm", None) if st is not None else None,
                            fps=float(getattr(st, "fps", 0.0)) if st is not None and getattr(st, "fps", None) is not None else None,
                            message=msg,
                            distance_cm=display_cm,
                        )
                    )
                except Exception as e:
                    # дисплей не должен валить main loop
                    logger.write("display_runtime_error", err=str(e))

            # -----------------------
            # Clamp inputs
            # -----------------------
            steer = clamp(steer, -1.0, 1.0)
            manual_throttle = clamp(manual_throttle, -1.0, 1.0)

            # -----------------------
            # Compute final throttle (manual vs auto)
            # -----------------------
            final_throttle = ap.compute_throttle(
                manual_throttle=manual_throttle,
                stop=is_stop,
                armed=arm.armed,
            )

            # -----------------------
            # Forward motion gated by ultrasonic (AUTO only)
            # -----------------------
            if ap.mode == DriveMode.AUTO_CRUISE and final_throttle > 0.0:
                if is_stop:
                    final_throttle = 0.0

            # -----------------------
            # Auto speed scaling (turning / obstacles)
            # -----------------------
            if ap.mode == DriveMode.AUTO_CRUISE and final_throttle > 0.0 and st is not None:
                scale = 1.0

                turn_thresh = getattr(config, "AUTO_TURN_STEER_THRESHOLD", 0.35)
                turn_scale = getattr(config, "AUTO_TURN_SPEED_SCALE", 0.65)
                if abs(steer) >= float(turn_thresh):
                    scale *= float(turn_scale)

                occ_center = float(getattr(st, "occ_center", 0.0))
                closest_norm = float(getattr(st, "closest_norm", 0.0))
                occ_thresh = getattr(config, "AUTO_OBS_CENTER_THRESHOLD", 0.35)
                close_thresh = getattr(config, "AUTO_CLOSEST_THRESHOLD", 0.75)
                obs_scale = getattr(config, "AUTO_OBS_SPEED_SCALE", 0.50)

                if occ_center >= float(occ_thresh) or closest_norm >= float(close_thresh):
                    scale *= float(obs_scale)

                final_throttle *= max(0.0, min(1.0, scale))

            # -----------------------
            # Auto turn control (avoidance)
            # -----------------------
            if ap.mode == DriveMode.AUTO_CRUISE:
                manual_override = float(getattr(config, "AUTO_TURN_MANUAL_OVERRIDE", 0.15))
                ramp_per_sec = float(getattr(config, "AUTO_TURN_RAMP_PER_SEC", 2.0))
                max_delta = ramp_per_sec * dt

                if abs(steer) >= manual_override:
                    auto_turn_steer = steer
                else:
                    if turn_decision in ("left", "right"):
                        turn_val = float(getattr(config, "AUTO_TURN_STEER_VALUE", 0.60))
                        target = -abs(turn_val) if turn_decision == "left" else abs(turn_val)
                    else:
                        target = 0.0
                    auto_turn_steer = move_towards(auto_turn_steer, target, max_delta)
                steer = auto_turn_steer

            # -----------------------
            # Speed-based steering limit (AUTO only)
            # -----------------------
            if ap.mode == DriveMode.AUTO_CRUISE and final_throttle > 0.0:
                s_low = float(getattr(config, "AUTO_STEER_SPEED_LOW", 0.10))
                s_high = float(getattr(config, "AUTO_STEER_SPEED_HIGH", 0.35))
                max_low = float(getattr(config, "AUTO_STEER_MAX_LOW", 1.00))
                max_high = float(getattr(config, "AUTO_STEER_MAX_HIGH", 0.50))

                if s_high > s_low:
                    t = (final_throttle - s_low) / (s_high - s_low)
                else:
                    t = 1.0
                t = clamp(t, 0.0, 1.0)
                max_steer = max_low + (max_high - max_low) * t
                steer = clamp(steer, -abs(max_steer), abs(max_steer))

            # -----------------------
            # Turn decision snapshot (after final steer)
            # -----------------------
            if turn_changed and getattr(config, "SNAPSHOT_ON_TURN_DECISION", False):
                vision.snapshot_event(
                    f"turn_{turn_decision}",
                    st,
                    occ_left=float(turn_occ_left) if turn_occ_left is not None else None,
                    occ_center=float(turn_occ_center) if turn_occ_center is not None else None,
                    occ_right=float(turn_occ_right) if turn_occ_right is not None else None,
                    steer_applied=float(steer),
                    throttle_final=float(final_throttle),
                )

            # -----------------------
            # HARD safety layer (AUTO only)
            # -----------------------
            if ap.mode != DriveMode.MANUAL:
                if is_stop and final_throttle > 0.0:
                    final_throttle = 0.0

                if now - last_manual_activity > MANUAL_ACTIVITY_TIMEOUT and final_throttle > 0.0:
                    final_throttle = 0.0

            # -----------------------
            # Apply hardware
            # -----------------------
            if steering:
                steering.update(steer)

            if motor:
                if arm.armed:
                    motor.update(final_throttle)
                else:
                    motor.stop()

            # -----------------------
            # Console debug
            # -----------------------
            if now - last_debug > 0.5:
                if ap.mode != last_mode:
                    last_mode = ap.mode
                print(
                    f"[DEBUG] mode={ap.mode} "
                    f"cruise={ap.cruise_speed:.2f} "
                    f"stop={is_stop} free={free if free is not None else 'NA'} "
                    f"steer={steer:+.2f} "
                    f"thr={final_throttle:+.2f} "
                    f"armed={arm.armed} "
                    f"vision_ok={vision_ok}"
                )
                last_debug = now

            time.sleep(0.02)  # 50 Hz

    except Exception as e:
        logger.write("fatal_error", err=str(e), tb=traceback.format_exc()[-4000:])
        raise

    finally:
        print("[SYSTEM] Shutting down safely")
        logger.write("shutdown")

        # STOP MOTOR FIRST
        try:
            if motor:
                motor.stop()
        except Exception:
            pass

        # Display stop
        try:
            if display_ok and display:
                display.stop()
        except Exception:
            pass

        # Vision stop
        try:
            if vision_ok:
                vision.stop()
        except Exception:
            pass

        # Reset hardware.
        try:
            if servo:
                servo.set_center()
        except Exception:
            pass

        try:
            if throttle:
                throttle.set_neutral()
        except Exception:
            pass

        try:
            logger.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
