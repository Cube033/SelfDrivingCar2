from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image

# luma
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106


@dataclass(frozen=True)
class DisplayConfig:
    # I2C bus and address (у тебя: i2cdetect -y 1 показал 0x3c)
    i2c_bus: int = 1
    i2c_address: int = 0x3C

    # SH1106 128x64
    width: int = 128
    height: int = 64

    # rotate: 0/1/2/3 => 0, 90, 180, 270 градусов (в luma это rotate=0..3)
    rotate: int = 0

    # I2C speed (по умолчанию нормально; можно поднять при необходимости)
    i2c_port_speed_hz: Optional[int] = None  # None = default


class SH1106I2CDisplay:
    """
    Тонкая обертка над luma.oled для SH1106.
    """

    def __init__(self, cfg: DisplayConfig):
        self.cfg = cfg

        serial = i2c(
            port=cfg.i2c_bus,
            address=cfg.i2c_address,
        )

        # Примечание: luma берет width/height из драйвера.
        # rotate=0..3
        self.device = sh1106(serial, rotate=cfg.rotate)

        # Проверка ожидаемых размеров
        # (device.width/height могут совпасть с cfg)
        if self.device.width != cfg.width or self.device.height != cfg.height:
            # Это не критично, но лучше знать
            print(
                f"[DISPLAY] Warning: device size is {self.device.width}x{self.device.height}, "
                f"expected {cfg.width}x{cfg.height}"
            )

    @property
    def width(self) -> int:
        return int(self.device.width)

    @property
    def height(self) -> int:
        return int(self.device.height)

    def clear(self) -> None:
        self.device.clear()
        self.device.show()

    def show_image(self, img: Image.Image) -> None:
        """
        img должен быть mode '1' или 'L'. Мы приводим к '1'.
        """
        if img.mode != "1":
            img = img.convert("1")
        self.device.display(img)