from dataclasses import dataclass


@dataclass(frozen=True)
class Roi:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def h(self) -> int:
        return max(0, self.y1 - self.y0)


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def compute_roi(width: int, height: int, roi_w: float, roi_h_bottom: float) -> Roi:
    """
    ROI centered horizontally, located at bottom of the frame.
    roi_w and roi_h_bottom are fractions of width/height.
    """
    rw = int(width * roi_w)
    rh = int(height * roi_h_bottom)

    cx = width // 2
    x0 = clamp(cx - rw // 2, 0, width - 1)
    x1 = clamp(cx + rw // 2, 1, width)

    y1 = height
    y0 = clamp(height - rh, 0, height - 1)

    # Ensure non-empty ROI
    if x1 <= x0:
        x1 = clamp(x0 + 1, 1, width)
    if y1 <= y0:
        y1 = clamp(y0 + 1, 1, height)

    return Roi(x0=x0, y0=y0, x1=x1, y1=y1)