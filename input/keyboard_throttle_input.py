# input/keyboard_throttle_input.py

import sys
import termios
import tty
import select


class KeyboardThrottleInput:
    def __init__(self, step=0.05):
        self.step = step
        self.value = 0.0
        self.arm_event = None  # "arm" | "disarm" | None

        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def _read_key(self):
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def read(self) -> float:
        self.arm_event = None
        key = self._read_key()

        if key == "w":
            self.value += self.step
        elif key == "s":
            self.value -= self.step
        elif key == " ":
            self.value = 0.0
        elif key == "\r":  # Enter
            self.arm_event = "arm"
        elif key == "\x1b":  # Esc
            self.arm_event = "disarm"

        self.value = max(-1.0, min(1.0, self.value))
        return self.value