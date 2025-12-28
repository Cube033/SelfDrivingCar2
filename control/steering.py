# control/steering.py

class SteeringMapper:
    def __init__(self, dead_zone=0.05, invert=False):
        self.dead_zone = dead_zone
        self.invert = invert

    def apply(self, value: float) -> float:
        # clamp
        value = max(-1.0, min(1.0, value))

        # dead zone
        if abs(value) < self.dead_zone:
            return 0.0

        # invert if needed
        if self.invert:
            value = -value

        return value