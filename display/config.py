from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DisplayConfig:
    # I2C
    i2c_bus: int = 1
    i2c_address: int = 0x3C  # у тебя i2cdetect показывает 3c

    # OLED SH1106 128x64
    width: int = 128
    height: int = 64

    # rotate: 0..3 (0=0°, 1=90°, 2=180°, 3=270°)
    rotate: int = 0

    # update rate limit
    max_fps: float = 10.0