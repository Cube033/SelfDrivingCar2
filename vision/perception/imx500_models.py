
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IMX500Paths:
    # Official assets/pipelines for rpicam-apps
    camera_assets_dir: Path = Path("/usr/share/rpi-camera-assets")
    object_detection_json: Path = Path("/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json")
    posenet_json: Path = Path("/usr/share/rpi-camera-assets/imx500_posenet.json")

    # Model zoo (installed by package imx500-all / imx500-models)
    model_zoo_dir: Path = Path("/usr/share/imx500-models")
    deeplabv3plus_rpk: Path = Path("/usr/share/imx500-models/imx500_network_deeplabv3plus.rpk")


PATHS = IMX500Paths()


def assert_paths_exist() -> None:
    missing = []
    for p in [
        PATHS.camera_assets_dir,
        PATHS.object_detection_json,
        PATHS.posenet_json,
        PATHS.model_zoo_dir,
        PATHS.deeplabv3plus_rpk,
    ]:
        if not p.exists():
            missing.append(str(p))

    if missing:
        raise FileNotFoundError(
            "Missing IMX500 files on this system:\n"
            + "\n".join(missing)
            + "\n\nTip: on Raspberry run: sudo apt install -y imx500-all"
        )