import board
import busio
from adafruit_pca9685 import PCA9685

class Servo:
    def __init__(
        self,
        channel=0,
        center_us=1550,
        left_us=1300,
        right_us=1700,
        frequency=50,
    ):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = PCA9685(i2c)
        self.pca.frequency = frequency
        self.servo = self.pca.channels[channel]

        self.center_us = center_us
        self.left_us = left_us
        self.right_us = right_us

        self.set_center()

    def _set_us(self, us):
        duty = int(us * 65535 / 20000)
        self.servo.duty_cycle = duty

    def set_center(self):
        self._set_us(self.center_us)

    def set_left(self):
        self._set_us(self.left_us)

    def set_right(self):
        self._set_us(self.right_us)

    def set_ratio(self, ratio):
        """
        ratio: -1.0 (лево) ... 0.0 (центр) ... 1.0 (право)
        """
        ratio = max(-1.0, min(1.0, ratio))
        if ratio < 0:
            us = self.center_us + ratio * (self.center_us - self.left_us)
        else:
            us = self.center_us + ratio * (self.right_us - self.center_us)
        self._set_us(int(us))

    def stop(self):
        self.servo.duty_cycle = 0
        self.pca.deinit()
    
    def set_normalized(self, value: float):
        """
        value ∈ [-1.0 … 1.0]
        """
        value = max(-1.0, min(1.0, value))

        if value == 0:
            us = self.center_us
        elif value < 0:
            us = self.center_us + value * (self.center_us - self.left_us)
        else:
            us = self.center_us + value * (self.right_us - self.center_us)

        # print(f"[SERVO] value={value:+.2f} → {us} µs")

        self._set_us(int(us))
