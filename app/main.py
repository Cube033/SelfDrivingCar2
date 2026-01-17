import os
import sys
import time
import signal
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

from app.autopilot import Autopilot, AutoCruiseConfig
from app.event_logger import EventLogger

from vision.segscore.service import SegScoreService


def gamepad_available(device_path: str) -> bool:
    return bool(device_path) and os.path.exists(device_path)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def main():
    has_tty = sys.stdin.isatty()
    pid = os.getpid()

    # -----------------------
    # Logging
    # -----------------------
    logger = EventLogger(log_dir=getattr(config, "LOG_DIR", "logs"))
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
    # Vision (IMX500 seg score)
    # -----------------------
    vision = SegScoreService()
    vision_ok = False
    try:
        vision.start()
        vision_ok = True
        logger.write("vision_started")
        print("[SYSTEM] Vision runner started")
    except Exception as e:
        # Главное: не падаем. Просто запрещаем круиз (stop=True по умолчанию).
        logger.write("vision_failed", err=str(e), tb=traceback.format_exc()[-2000:])
        print("[WARN] Vision start failed:", e)

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

    logger.write("main_loop_start", mode=ap.mode, cruise_speed=ap.cruise_speed, vision_ok=vision_ok)
    print("[SYSTEM] Main loop started")

    last_stop = None
    last_mode = ap.mode
    last_debug = 0.0

    # watchdog: если нет никаких “ручных” действий — можно стопить вперёд (опционально)
    last_manual_activity = time.time()
    MANUAL_ACTIVITY_TIMEOUT = getattr(config, "MANUAL_ACTIVITY_TIMEOUT", 999999.0)  # выключен по умолчанию

    try:
        while not stopping["flag"]:
            now = time.time()

            steer = 0.0
            manual_throttle = 0.0
            mode_event = None
            cruise_delta = 0

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
                    ls, rs, gp_throttle, gp_arm_event, mode_event, cruise_delta = next(gamepad_iter)
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
                # Vision может временно глючить — не валим всё приложение.
                logger.write("vision_runtime_error", err=str(e))
                st = None

            is_stop = bool(st.is_stopped) if st is not None else True
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
            # HARD safety layer:
            # stop=True => запрещаем движение вперед, но оставляем возможность тормозить/сдавать назад
            # -----------------------
            if is_stop and final_throttle > 0.0:
                final_throttle = 0.0

            # optional watchdog: если давно нет ручной активности — тоже не едем вперед
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

        # Vision stop
        try:
            if vision_ok:
                vision.stop()
        except Exception:
            pass

        # Reset hardware
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