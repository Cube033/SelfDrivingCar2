from evdev import InputDevice, ecodes
from select import select


class DualShockInput:
    """
    DualShock 4 input reader (Linux evdev).

    Emits (через generator values()):
        left_steer  : -1.0 .. +1.0
        right_steer : -1.0 .. +1.0
        throttle    : -1.0 .. +1.0
        arm_event   : "arm" | "disarm" | None
    """

    def __init__(self, device_path: str):
        print(f"[DS] Opening input device: {device_path}")

        # ❗ Никакого grab — он ломает Bluetooth + systemd
        self.dev = InputDevice(device_path)

        # --- state ---
        self.left_x = 0.0
        self.right_x = 0.0
        self.forward = 0.0
        self.reverse = 0.0

        print(f"🎮 DualShock подключён: {self.dev.name}")

    # ---------- helpers ----------

    @staticmethod
    def _norm_axis(value: int, center=128, span=128) -> float:
        """
        ABS axis (0..255) → -1.0 .. +1.0
        """
        return max(-1.0, min(1.0, (value - center) / span))

    @staticmethod
    def _norm_trigger(value: int) -> float:
        """
        Trigger (0..255) → 0.0 .. 1.0
        """
        return max(0.0, min(1.0, value / 255.0))

    # ---------- main generator ----------

    def values(self):
        """
        Generator of gamepad state.
        Cleanly stops if device disappears.
        """
        while True:
            arm_event = None

            try:
                # Ждём события от устройства (20 мс)
                r, _, _ = select([self.dev], [], [], 0.02)

                if r:
                    for event in self.dev.read():

                        # ----- axes -----
                        if event.type == ecodes.EV_ABS:
                            if event.code == ecodes.ABS_X:
                                self.left_x = self._norm_axis(event.value)

                            elif event.code == ecodes.ABS_RX:
                                self.right_x = self._norm_axis(event.value)

                            elif event.code == ecodes.ABS_RZ:   # R2 → forward
                                self.forward = self._norm_trigger(event.value)

                            elif event.code == ecodes.ABS_Z:    # L2 → reverse
                                self.reverse = self._norm_trigger(event.value)

                        # ----- buttons -----
                        elif event.type == ecodes.EV_KEY:
                            print(f"[KEY] code={event.code} value={event.value}")

                            # реагируем только на нажатие
                            if event.value == 1:
                                # ❌ X → ARM
                                if event.code == ecodes.BTN_SOUTH:
                                    arm_event = "arm"
                                    print("[ARM] ON (gamepad)")

                                # PS → DISARM
                                elif event.code == ecodes.BTN_MODE:
                                    arm_event = "disarm"
                                    print("[ARM] OFF (gamepad)")

            except OSError as e:
                # Bluetooth-устройство пропало
                print(f"[WARN] Gamepad disconnected: {e}")
                return  # корректно завершаем генератор

            # ----- compute throttle -----
            throttle = self.forward - self.reverse
            throttle = max(-1.0, min(1.0, throttle))

            yield (
                self.left_x,
                self.right_x,
                throttle,
                arm_event,
            )