# control/throttle_controller.py

class ThrottleController:
    def __init__(self, throttle, dead_zone=0.05, invert=False):
        self.throttle = throttle
        self.dead_zone = dead_zone
        self.invert = invert
        self._last = 0.0

    def update(self, value: float):
        value = max(-1.0, min(1.0, value))

        # логический реверс (НЕ в железе)
        if self.invert:
            value = -value

        if abs(value) < self.dead_zone:
            value = 0.0

        # запрет мгновенного реверса
        if (self._last > 0 and value < 0) or (self._last < 0 and value > 0):
            self.throttle.set_neutral()
            self._last = 0.0
            return

        self.throttle.set_normalized(value)
        self._last = value

    def stop(self):
        self.throttle.set_neutral()
        self._last = 0.0