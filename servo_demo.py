import time
from hardware.servo import Servo

servo = Servo()

try:
    servo.set_left()
    time.sleep(1)

    servo.set_center()
    time.sleep(1)

    servo.set_right()
    time.sleep(1)

    servo.set_center()
    time.sleep(1)

finally:
    servo.stop()
