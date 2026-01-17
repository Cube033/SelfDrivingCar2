from dataclasses import dataclass


class DriveMode:
    MANUAL = "manual"
    AUTO_CRUISE = "auto_cruise"


@dataclass
class AutoCruiseConfig:
    speed_default: float = 0.15
    speed_min: float = 0.05
    speed_max: float = 0.35
    speed_step: float = 0.02


class Autopilot:
    def __init__(self, cfg: AutoCruiseConfig):
        self.cfg = cfg
        self.mode = DriveMode.MANUAL
        self.cruise_speed = cfg.speed_default

    def toggle_auto_cruise(self) -> None:
        self.mode = (
            DriveMode.AUTO_CRUISE
            if self.mode == DriveMode.MANUAL
            else DriveMode.MANUAL
        )

    def apply_cruise_delta(self, delta: int) -> None:
        if delta == 0:
            return
        self.cruise_speed += delta * self.cfg.speed_step
        self.cruise_speed = max(self.cfg.speed_min, min(self.cfg.speed_max, self.cruise_speed))

    def compute_throttle(self, manual_throttle: float, stop: bool, armed: bool) -> float:
        if not armed:
            return 0.0

        if self.mode == DriveMode.MANUAL:
            return manual_throttle

        # AUTO_CRUISE
        return 0.0 if stop else self.cruise_speed