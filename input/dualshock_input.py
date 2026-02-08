from evdev import InputDevice, ecodes
from select import select


class DualShockInput:
    """
    DualShock 4 input reader (Linux evdev).

    Emits (generator values()):
        left_steer  : -1.0 .. +1.0
        right_steer : -1.0 .. +1.0
        throttle    : -1.0 .. +1.0
        arm_event   : "arm" | "disarm" | None
        mode_event  : "toggle_auto_cruise" | None
        cruise_delta: -1 | 0 | +1
    """

    def __init__(self, device_path: str):
        print(f"[DS] Opening input device: {device_path}")
        self.dev = InputDevice(device_path)

        self.left_x = 0.0
        self.right_x = 0.0
        self.forward = 0.0
        self.reverse = 0.0

        # D-pad state (for EV_ABS hats)
        self._hat_y = 0

        print(f"🎮 DualShock подключён: {self.dev.name}")

    @staticmethod
    def _norm_axis(value: int, center=128, span=128) -> float:
        return max(-1.0, min(1.0, (value - center) / span))

    @staticmethod
    def _norm_trigger(value: int) -> float:
        return max(0.0, min(1.0, value / 255.0))

    def values(self):
        while True:
            arm_event = None
            mode_event = None
            cruise_delta = 0
            shutdown_event = False

            try:
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

                            # D-pad on many Linux setups comes as ABS_HAT0Y: -1 up, +1 down
                            elif event.code == ecodes.ABS_HAT0Y:
                                # react only on transitions to up/down
                                if event.value == -1 and self._hat_y != -1:
                                    cruise_delta = +1
                                elif event.value == +1 and self._hat_y != +1:
                                    cruise_delta = -1
                                self._hat_y = event.value

                        # ----- buttons -----
                        elif event.type == ecodes.EV_KEY:
                            # print(f"[KEY] code={event.code} value={event.value}")

                            if event.value == 1:  # press
                                # X → ARM
                                if event.code == ecodes.BTN_SOUTH:
                                    arm_event = "arm"
                                    print("[ARM] ON (gamepad)")

                                # PS → DISARM
                                elif event.code == ecodes.BTN_MODE:
                                    arm_event = "disarm"
                                    print("[ARM] OFF (gamepad)")

                                # O / Circle → toggle auto cruise
                                elif event.code == ecodes.BTN_EAST:
                                    mode_event = "toggle_auto_cruise"
                                    print("[MODE] Toggle AUTO_CRUISE")

                                # Some setups expose D-pad as buttons:
                                elif hasattr(ecodes, "BTN_DPAD_UP") and event.code == ecodes.BTN_DPAD_UP:
                                    cruise_delta = +1
                                elif hasattr(ecodes, "BTN_DPAD_DOWN") and event.code == ecodes.BTN_DPAD_DOWN:
                                    cruise_delta = -1
                                # Share → safe shutdown
                                elif event.code == ecodes.BTN_SELECT:
                                    shutdown_event = True
                                    print("[SYSTEM] Shutdown requested (gamepad)")

            except OSError as e:
                print(f"[WARN] Gamepad disconnected: {e}")
                return

            throttle = self.forward - self.reverse
            throttle = max(-1.0, min(1.0, throttle))

            yield (
                self.left_x,
                self.right_x,
                throttle,
                arm_event,
                mode_event,
                cruise_delta,
                shutdown_event,
            )
