"""
Perception layer for the RC Car project.

This package contains camera-based perception modules:
- object detection
- pose estimation
- segmentation / free-space estimation

At this stage, perception is completely decoupled from
motor and steering control.
"""

from .segmentation_reader import (
    SegmentationFreeSpaceEstimator,
    FreeSpaceResult,
)

from .imx500_models import (
    IMX500Paths,
    PATHS,
    assert_paths_exist,
)

__all__ = [
    "SegmentationFreeSpaceEstimator",
    "FreeSpaceResult",
    "IMX500Paths",
    "PATHS",
    "assert_paths_exist",
]