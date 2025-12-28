# input/keyboard_input.py

import sys
import termios
import tty
import select


class KeyboardSteeringInput:
    def __init__(self, step=0.05):
        self.step = step
        self.current = 0.0

        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def _read_key(self):
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def read(self) -> float:
        """
        Возвращает текущее значение руля [-1.0 .. 1.0]
        """
        key = self._read_key()

        if key == "a":
            self.current -= self.step
        elif key == "d":
            self.current += self.step
        elif key == " ":
            self.current = 0.0

        self.current = max(-1.0, min(1.0, self.current))
        return self.current

    def close(self):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)