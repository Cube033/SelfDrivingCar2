# input/keyboard_input.py
import time
import keyboard

class KeyboardSteeringInput:
    def __init__(self, step=0.05):
        self.value = 0.0
        self.step = step

    def values(self):
        print("Управление:")
        print("  ← / →  : поворот")
        print("  space  : центр")
        print("  q      : выход")

        while True:
            if keyboard.is_pressed("left"):
                self.value -= self.step
            elif keyboard.is_pressed("right"):
                self.value += self.step
            elif keyboard.is_pressed("space"):
                self.value = 0.0
            elif keyboard.is_pressed("q"):
                raise KeyboardInterrupt

            self.value = max(-1.0, min(1.0, self.value))
            yield self.value
            time.sleep(0.05)