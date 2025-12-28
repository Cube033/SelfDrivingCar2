# app/main.py
from hardware.servo import Servo
from hardware.throttle import Throttle

from control.steering import SteeringMapper
from control.controller import SteeringController
from hardware.throttle_controller import ThrottleController

from input.keyboard_input import KeyboardSteeringInput
from input.keyboard_throttle_input import KeyboardThrottleInput

def main():
    servo = Servo(
        channel=0,
        center_us=1600,
        left_us=950,
        right_us=2200,
    )

    throttle = Throttle(
        channel=1,
        neutral_us=1600,
        reverse_us=1100,
        forward_us=1900,
    )

    mapper = SteeringMapper(dead_zone=0.03, invert=True)
    steering = SteeringController(mapper, servo)
    motor = ThrottleController(throttle, dead_zone=0.05)

    steering_input = KeyboardSteeringInput(step=0.05)
    throttle_input = KeyboardThrottleInput(step=0.05)

    try:
        # простой вариант: читаем по очереди (20 Гц на каждом)
        for s, t in zip(steering_input.values(), throttle_input.values()):
            steering.update(s)
            motor.update(t)

    except KeyboardInterrupt:
        print("\nВыход: центр + нейтраль")
    finally:
        servo.set_center()
        throttle.set_neutral()

if __name__ == "__main__":
    main()