# input/keyboard_throttle_input.py
import time
import keyboard

class KeyboardThrottleInput:
    def __init__(self, step=0.05, rate_hz=20):
        self.step = step
        self.dt = 1.0 / rate_hz
        self.value = 0.0

    def values(self):
        print("Управление газом:")
        print("  w/s    : вперед/назад")
        print("  space  : нейтраль")
        print("  q      : выход")

        while True:
            if keyboard.is_pressed("q"):
                return

            if keyboard.is_pressed("space"):
                self.value = 0.0
            else:
                if keyboard.is_pressed("w"):
                    self.value = min(1.0, self.value + self.step)
                elif keyboard.is_pressed("s"):
                    self.value = max(-1.0, self.value - self.step)
                else:
                    # авто-возврат к нейтрали понемногу
                    if self.value > 0:
                        self.value = max(0.0, self.value - self.step)
                    elif self.value < 0:
                        self.value = min(0.0, self.value + self.step)

            yield self.value
            time.sleep(self.dt)