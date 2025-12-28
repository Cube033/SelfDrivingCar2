# input/dualshock_input.py

from evdev import InputDevice, ecodes
from select import select


class DualShockInput:
    """
    DualShock 4 input reader.
    Emits:
        left_steer  : -1.0 .. +1.0
        right_steer : -1.0 .. +1.0
        throttle    : -1.0 .. +1.0
        armed       : bool
    """

    def __init__(self, device_path: str):
        self.dev = InputDevice(device_path)
        self.dev.grab()  # эксклюзивный доступ

        # состояния
        self.left_x = 0.0
        self.right_x = 0.0
        self.forward = 0.0
        self.reverse = 0.0
        self.armed = False

        print(f"🎮 DualShock подключён: {self.dev.name}")

    # --- helpers ---

    @staticmethod
    def _norm_axis(value: int, center=128, span=128) -> float:
        """ABS axis → -1.0 .. +1.0"""
        return max(-1.0, min(1.0, (value - center) / span))

    @staticmethod
    def _norm_trigger(value: int) -> float:
        """Trigger → 0.0 .. 1.0"""
        return max(0.0, min(1.0, value / 255.0))

    # --- generator ---

    def values(self):
        while True:
            r, _, _ = select([self.dev], [], [], 0.02)
            if not r:
                yield self.left_x, self.right_x, self.forward - self.reverse, self.armed
                continue

            for event in self.dev.read():
                if event.type == ecodes.EV_ABS:
                    if event.code == ecodes.ABS_X:
                        self.left_x = self._norm_axis(event.value)

                    elif event.code == ecodes.ABS_RX:
                        self.right_x = self._norm_axis(event.value)

                    elif event.code == ecodes.ABS_RZ:   # R2
                        self.forward = self._norm_trigger(event.value)

                    elif event.code == ecodes.ABS_Z:    # L2
                        self.reverse = self._norm_trigger(event.value)

                elif event.type == ecodes.EV_KEY:
                    if event.code == ecodes.BTN_START and event.value == 1:
                        self.armed = not self.armed
                        print(f"[ARM] {'ON' if self.armed else 'OFF'}")

            yield self.left_x, self.right_x, self.forward - self.reverse, self.armed