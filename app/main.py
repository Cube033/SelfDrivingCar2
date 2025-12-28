# app/main.py

import time
import config

from hardware.servo import Servo
from hardware.throttle import Throttle

from control.steering import SteeringMapper
from control.controller import SteeringController
from hardware.throttle_controller import ThrottleController

from input.keyboard_input import KeyboardSteeringInput
from input.keyboard_throttle_input import KeyboardThrottleInput
from input.dualshock_input import DualShockInput


def main():
    servo = None
    throttle = None
    steering = None
    motor = None

    # ===== Hardware init (safe) =====
    try:
        servo = Servo(
            channel=0,
            center_us=config.SERVO_CENTER_US,
            left_us=config.SERVO_LEFT_US,
            right_us=config.SERVO_RIGHT_US,
        )

        steering_mapper = SteeringMapper(
            dead_zone=config.STEERING_DEAD_ZONE,
            invert=config.STEERING_INVERT,
        )

        steering = SteeringController(steering_mapper, servo)
        print("[INIT] Servo OK")

    except Exception as e:
        print("[WARN] Servo not available:", e)

    try:
        throttle = Throttle(
            channel=1,
            neutral_us=config.THROTTLE_NEUTRAL_US,
            forward_us=config.THROTTLE_FORWARD_US,
            reverse_us=config.THROTTLE_REVERSE_US,
            invert=config.THROTTLE_INVERT,
        )

        motor = ThrottleController(
            throttle,
            dead_zone=config.THROTTLE_DEAD_ZONE,
        )
        print("[INIT] Throttle OK")

    except Exception as e:
        print("[WARN] Throttle not available:", e)

    # ===== Inputs =====
    keyboard_steer = KeyboardSteeringInput(step=0.05)
    keyboard_throttle = KeyboardThrottleInput(step=0.05)

    gamepad = None
    if config.GAMEPAD_ENABLED:
        try:
            gamepad = DualShockInput(config.GAMEPAD_DEVICE)
        except Exception as e:
            print("[WARN] Gamepad not available:", e)

    armed = False

    print("[SYSTEM] Main loop started")

    try:
        while True:
            steer = 0.0
            throttle_value = 0.0

            # --- Gamepad ---
            if gamepad:
                try:
                    ls, rs, gp_throttle, gp_armed = next(gamepad.values())
                    steer = rs if abs(rs) > abs(ls) else ls
                    throttle_value = gp_throttle
                    armed = armed or gp_armed
                except Exception as e:
                    print("[WARN] Gamepad lost:", e)
                    gamepad = None

            # --- Keyboard fallback ---
            if config.KEYBOARD_ENABLED:
                steer += keyboard_steer.read()
                throttle_value += keyboard_throttle.read()
                armed = armed or keyboard_throttle.armed

            steer = max(-1.0, min(1.0, steer))
            throttle_value = max(-1.0, min(1.0, throttle_value))

            if steering:
                steering.update(steer)

            if motor:
                if armed:
                    motor.update(throttle_value)
                else:
                    motor.stop()

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("[SYSTEM] Exit requested")

    finally:
        print("[SYSTEM] Shutting down safely")
        if steering:
            servo.set_center()
        if motor:
            throttle.set_neutral()


if __name__ == "__main__":
    main()