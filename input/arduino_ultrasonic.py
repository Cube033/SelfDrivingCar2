from __future__ import annotations

from typing import Optional
import time

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover
    serial = None


class UltrasonicSerialReader:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.01):
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        self.port = port
        self.baud = int(baud)
        self.timeout = float(timeout)
        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._last_cm: Optional[float] = None
        self._last_ts: float = 0.0

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass

    def read_cm(self) -> Optional[float]:
        try:
            line = self._ser.readline().decode("ascii", errors="ignore").strip()
        except Exception:
            return None

        if not line:
            return None

        try:
            cm = float(line)
        except ValueError:
            return None

        if cm <= 0:
            return None

        self._last_cm = cm
        self._last_ts = time.time()
        return cm

    def last_cm(self) -> Optional[float]:
        return self._last_cm

    def last_ts(self) -> float:
        return self._last_ts
