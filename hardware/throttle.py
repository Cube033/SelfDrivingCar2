# hardware/throttle.py
import board
import busio
from adafruit_pca9685 import PCA9685


class Throttle:
    def __init__(
        self,
        channel: int = 1,
        neutral_us: int = 1600,
        reverse_us: int = 1100,
        forward_us: int = 1900,
        frequency: int = 50,
    ):
        self.neutral_us = neutral_us
        self.reverse_us = reverse_us
        self.forward_us = forward_us

        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = PCA9685(i2c)
        self.pca.frequency = frequency
        self.ch = self.pca.channels[channel]

        self._last_us = None
        self.set_neutral()

    def _set_us(self, us: int):
        us = int(us)
        duty = int(us * 65535 / 20000)
        self.ch.duty_cycle = duty

        if us != self._last_us:
            print(f"[THROTTLE] {us} µs")
            self._last_us = us

    def set_neutral(self):
        self._set_us(self.neutral_us)

    def set_normalized(self, value: float):
        value = max(-1.0, min(1.0, value))

        if abs(value) < 1e-6:
            self._set_us(self.neutral_us)
            return

        if value > 0:
            us = self.neutral_us + value * (self.forward_us - self.neutral_us)
        else:
            us = self.neutral_us + value * (self.neutral_us - self.reverse_us)

        self._set_us(us)