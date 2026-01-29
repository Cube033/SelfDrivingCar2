from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image

from luma.core.interface.serial import i2c
from luma.oled.device import sh1106

from .config import DisplayConfig


class OLEDDevice:
    """
    SH1106 128x64 over I2C using luma.oled
    """

    def __init__(self, cfg: DisplayConfig):
        self.cfg = cfg
        serial = i2c(port=cfg.i2c_bus, address=cfg.i2c_address)
        self.dev = sh1106(serial, rotate=cfg.rotate)

        # sanity
        if (self.dev.width, self.dev.height) != (cfg.width, cfg.height):
            print(
                f"[DISPLAY] Warning: device reports {self.dev.width}x{self.dev.height}, "
                f"expected {cfg.width}x{cfg.height}"
            )

    @property
    def width(self) -> int:
        return int(self.dev.width)

    @property
    def height(self) -> int:
        return int(self.dev.height)

    def clear(self) -> None:
        self.dev.clear()
        self.dev.show()

    def show(self, img: Image.Image) -> None:
        if img.mode != "1":
            img = img.convert("1")
        self.dev.display(img)