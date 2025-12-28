import time
import board
import busio
from adafruit_pca9685 import PCA9685

print("Initializing I2C...")
i2c = busio.I2C(board.SCL, board.SDA)

print("Initializing PCA9685...")
pca = PCA9685(i2c)
pca.frequency = 50

servo = pca.channels[0]

def set_us(microseconds):
    # 20 ms period = 20000 µs
    duty = int(microseconds * 65535 / 20000)
    servo.duty_cycle = duty

print("Servo calibration test")
print("Ctrl+C to stop")

try:
    print("Center (1550 µs)")
    set_us(1550)
    time.sleep(3)

    print("Left (1300 µs)")
    set_us(1300)
    time.sleep(3)

    print("Right (1700 µs)")
    set_us(1700)
    time.sleep(3)

    print("Back to center (1550 µs)")
    set_us(1550)
    time.sleep(3)

except KeyboardInterrupt:
    pass
finally:
    servo.duty_cycle = 0
    pca.deinit()
    print("Stopped")
