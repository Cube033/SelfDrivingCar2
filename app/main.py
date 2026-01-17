import time
import sys
import os
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

from app.autopilot import Autopilot, AutoCruiseConfig, DriveMode
from app.event_logger import EventLogger

from vision.segscore.service import SegScoreService


def gamepad_available(device_path: str) -> bool:
    return bool(device_path) and os.path.exists(device_path)


def main():
    has_tty = sys.stdin.isatty()

    # -----------------------
    # Hardware
    # -----------------------
    try:
        servo = Servo(
            channel=0,
            center_us=config.SERVO_CENTER_US,
            left_us=config.SERVO_LEFT_US,
            right_us=config.SERVO_RIGHT_US,
        )
    except Exception as e:
        print("[WARN] Servo not available:", e)
        servo = None

    try:
        throttle = Throttle(
            channel=1,
            neutral_us=config.THROTTLE_NEUTRAL_US,
            forward_us=config.THROTTLE_FORWARD_US,
            reverse_us=config.THROTTLE_REVERSE_US,
        )
    except Exception as e:
        print("[WARN] Throttle not available:", e)
        throttle = None

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
        print("[SYSTEM] Keyboard input enabled")
    else:
        print("[SYSTEM] Keyboard input disabled (no TTY)")

    gamepad = None
    gamepad_iter = None
    last_gamepad_check = 0.0
    GAMEPAD_RETRY_INTERVAL = 2.0

    if not config.GAMEPAD_ENABLED:
        print("[SYSTEM] Gamepad disabled in config")

    # -----------------------
    # Vision (IMX500 seg score)
    # -----------------------
    # Берём конфиг точно такой же, как в демо: python -m vision.demos.print_segmentation_score ...
    vision = SegScoreService()
    vision.start()
    print("[SYSTEM] Vision runner started")

    # -----------------------
    # Autopilot + logging
    # -----------------------
    ap = Autopilot(AutoCruiseConfig(
        speed_default=getattr(config, "AUTO_CRUISE_SPEED_DEFAULT", 0.15),
        speed_min=getattr(config, "AUTO_CRUISE_SPEED_MIN", 0.05),
        speed_max=getattr(config, "AUTO_CRUISE_SPEED_MAX", 0.35),
        speed_step=getattr(config, "AUTO_CRUISE_SPEED_STEP", 0.02),
    ))
    logger = EventLogger(log_dir=getattr(config, "LOG_DIR", "logs"))

    logger.write("boot", mode=ap.mode)

    print("[SYSTEM] Main loop started")

    last_stop = None
    last_mode = ap.mode

    try:
        while True:
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
                            print("[SYSTEM] Gamepad connected")
                            logger.write("gamepad_connected")
                        except Exception as e:
                            print("[WARN] Failed to init gamepad:", e)

                elif gamepad is not None and not gamepad_available(config.GAMEPAD_DEVICE):
                    print("[WARN] Gamepad disconnected")
                    logger.write("gamepad_disconnected")
                    gamepad = None
                    gamepad_iter = None

            # -----------------------
            # Read gamepad
            # -----------------------
            if gamepad_iter:
                try:
                    ls, rs, gp_throttle, gp_arm_event, mode_event, cruise_delta = next(gamepad_iter)
                except StopIteration:
                    print("[WARN] Gamepad input stopped (device lost)")
                    logger.write("gamepad_input_stopped")
                    gamepad = None
                    gamepad_iter = None
                    continue

                steer = rs if abs(rs) > abs(ls) else ls
                manual_throttle = gp_throttle

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
                steer += keyboard_steer.read()
                manual_throttle += keyboard_throttle.read()

                if keyboard_throttle.arm_event == "arm":
                    arm.arm()
                    logger.write("arm", source="keyboard")
                elif keyboard_throttle.arm_event == "disarm":
                    arm.disarm()
                    logger.write("disarm", source="keyboard")

            # -----------------------
            # Mode + cruise speed updates
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
            st = vision.get()
            vision.maybe_snapshot_on_change(event_prefix="stopgo")
            is_stop = bool(st.is_stopped) if st is not None else False
            free = float(st.free_ratio) if st is not None else None
            ema = float(st.ema_free) if st is not None else None

            # log STOP edge
            if last_stop is None:
                last_stop = is_stop
            elif is_stop != last_stop:
                logger.write("stop_change", stop=is_stop, free=free, ema=ema, dominant=getattr(st, "dominant", None))
                last_stop = is_stop

            # -----------------------
            # Clamp steer & manual throttle
            # -----------------------
            steer = max(-1.0, min(1.0, steer))
            manual_throttle = max(-1.0, min(1.0, manual_throttle))

            # -----------------------
            # Compute final throttle (manual vs auto)
            # -----------------------
            final_throttle = ap.compute_throttle(
                manual_throttle=manual_throttle,
                stop=is_stop,
                armed=arm.armed,
            )

            # -----------------------
            # Apply to hardware
            # -----------------------
            if steering:
                steering.update(steer)

            if motor:
                if arm.armed:
                    motor.update(final_throttle)
                else:
                    motor.stop()

            # -----------------------
            # Console debug (light)
            # -----------------------
            if not hasattr(main, "_last_log"):
                main._last_log = 0.0

            if now - main._last_log > 0.5:
                if ap.mode != last_mode:
                    last_mode = ap.mode
                print(
                    f"[DEBUG] mode={ap.mode} "
                    f"cruise={ap.cruise_speed:.2f} "
                    f"stop={is_stop} free={free if free is not None else 'NA'} "
                    f"steer={steer:+.2f} "
                    f"thr={final_throttle:+.2f} "
                    f"armed={arm.armed}"
                )
                main._last_log = now

            time.sleep(0.02)  # 50 Hz

    except KeyboardInterrupt:
        print("[SYSTEM] Keyboard interrupt")

    finally:
        print("[SYSTEM] Shutting down safely")
        logger.write("shutdown")
        logger.close()

        try:
            vision.stop()
        except Exception:
            pass

        if servo:
            servo.set_center()
        if throttle:
            throttle.set_neutral()


if __name__ == "__main__":
    main()