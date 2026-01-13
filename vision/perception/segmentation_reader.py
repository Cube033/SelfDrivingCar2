"""
Segmentation-based free-space estimation.

Идея:
- Запускаем IMX500 segmentation.
- Получаем маску/выходы.
- Считаем числовую метрику "свободно/занято" в ROI (нижний центр кадра).
- Используем как safety-сигнал STOP/GO.

Пока здесь только каркас и интерфейс.
"""

from dataclasses import dataclass


@dataclass
class FreeSpaceResult:
    free_space_ratio: float  # 0..1
    should_stop: bool


class SegmentationFreeSpaceEstimator:
    def __init__(self, stop_threshold: float = 0.35):
        """
        stop_threshold:
          если free_space_ratio ниже порога -> STOP.
          Порог подбирается экспериментально.
        """
        self.stop_threshold = stop_threshold

    def estimate_from_ratio(self, free_space_ratio: float) -> FreeSpaceResult:
        """
        Временный метод: позже free_space_ratio будет считаться по маске.
        Сейчас фиксируем интерфейс и тестируем логику.
        """
        return FreeSpaceResult(
            free_space_ratio=free_space_ratio,
            should_stop=free_space_ratio < self.stop_threshold
        )