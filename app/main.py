# app/main.py

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


# =========================================================
# Helpers
# =========================================================

def gamepad_available(device_path: str) -> bool:
    return bool(device_path) and os.path.exists(device_path)


# =========================================================
# Main
# =========================================================

def main():
    has_tty = sys.stdin.isatty()

    # =========================================================
    # Hardware
    # =========================================================

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

    # =========================================================
    # Controllers
    # =========================================================

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

    # =========================================================
    # Inputs
    # =========================================================

    keyboard_steer = None
    keyboard_throttle = None

    if config.KEYBOARD_ENABLED and has_tty:
        keyboard_steer = KeyboardSteeringInput(step=0.1)
        keyboard_throttle = KeyboardThrottleInput(step=0.1)
        print("[SYSTEM] Keyboard input enabled")
    else:
        print("[SYSTEM] Keyboard input disabled (no TTY)")

    gamepad = None
    last_gamepad_check = 0.0
    GAMEPAD_RETRY_INTERVAL = 2.0  # seconds

    if not config.GAMEPAD_ENABLED:
        print("[SYSTEM] Gamepad disabled in config")

    print("[SYSTEM] Main loop started")

    # =========================================================
    # Main loop
    # =========================================================

    try:
        while True:
            now = time.time()

            steer = 0.0
            throttle_value = 0.0

            # -----------------------------------------------------
            # Gamepad hot-plug / reconnect
            # -----------------------------------------------------

            if config.GAMEPAD_ENABLED:
                # Try to connect if missing
                if gamepad is None and now - last_gamepad_check > GAMEPAD_RETRY_INTERVAL:
                    last_gamepad_check = now

                    if gamepad_available(config.GAMEPAD_DEVICE):
                        try:
                            gamepad = DualShockInput(config.GAMEPAD_DEVICE)
                            print("[SYSTEM] Gamepad connected")
                        except Exception as e:
                            print("[WARN] Failed to init gamepad:", e)

                # Detect disconnect
                elif gamepad is not None and not gamepad_available(config.GAMEPAD_DEVICE):
                    print("[WARN] Gamepad disconnected")
                    gamepad = None

            # -----------------------------------------------------
            # Gamepad input
            # -----------------------------------------------------

            if gamepad:
                try:
                    ls, rs, gp_throttle, gp_arm_event = next(gamepad.values())
                except StopIteration:
                    print("[WARN] Gamepad input stopped (device lost)")
                    gamepad = None
                    continue

                steer = rs if abs(rs) > abs(ls) else ls
                throttle_value = gp_throttle

                if gp_arm_event == "arm":
                    arm.arm()
                elif gp_arm_event == "disarm":
                    arm.disarm()

            # -----------------------------------------------------
            # Keyboard input
            # -----------------------------------------------------

            if keyboard_steer and keyboard_throttle:
                steer += keyboard_steer.read()
                throttle_value += keyboard_throttle.read()

                if keyboard_throttle.arm_event == "arm":
                    arm.arm()
                elif keyboard_throttle.arm_event == "disarm":
                    arm.disarm()

            # -----------------------------------------------------
            # Clamp
            # -----------------------------------------------------

            steer = max(-1.0, min(1.0, steer))
            throttle_value = max(-1.0, min(1.0, throttle_value))

            # -----------------------------------------------------
            # Apply
            # -----------------------------------------------------

            if steering:
                steering.update(steer)

            if motor:
                if arm.armed:
                    motor.update(throttle_value)
                else:
                    motor.stop()

            # -----------------------------------------------------
            # Debug
            # -----------------------------------------------------

            if not hasattr(main, "_last_log"):
                main._last_log = 0.0

            if now - main._last_log > 0.5:
                print(
                    f"[DEBUG] steer={steer:+.2f} "
                    f"throttle={throttle_value:+.2f} "
                    f"armed={arm.armed}"
                )
                main._last_log = now

            time.sleep(0.02)  # 50 Hz

    except KeyboardInterrupt:
        print("[SYSTEM] Keyboard interrupt")

    finally:
        print("[SYSTEM] Shutting down safely")

        if servo:
            servo.set_center()

        if throttle:
            throttle.set_neutral()


if __name__ == "__main__":
    main()