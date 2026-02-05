import json
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Optional

try:
    from PIL import Image
except Exception:
    Image = None


def _safe(obj: Any) -> Any:
    """
    Convert dataclasses / tuples to JSON-serializable structures.
    """
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (list, dict, str, int, float, bool)):
        return obj
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


class SnapshotWriter:
    """
    Writes snapshots as JSON Lines (.jsonl).
    Optionally can be extended to store mask/image files later.
    """

    def __init__(self, out_dir: str = "logs/vision", filename: Optional[str] = None):
        os.makedirs(out_dir, exist_ok=True)
        self._img_dir = os.path.join(out_dir, "images")
        self._txt_dir = os.path.join(out_dir, "text")
        os.makedirs(self._img_dir, exist_ok=True)
        os.makedirs(self._txt_dir, exist_ok=True)
        if filename is None:
            filename = time.strftime("segscore_%Y%m%d_%H%M%S.jsonl")
        self.path = os.path.join(out_dir, filename)
        self._f = open(self.path, "a", buffering=1)
        print(f"[SNAP] Vision snapshots: {self.path}")

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass

    def write(self, event: str, state: Any, image: Optional[Any] = None, **extra: Any) -> None:
        rec = {
            "ts": time.time(),
            "event": event,
            "state": _safe(state),
        }
        img_path = None
        if image is not None and Image is not None:
            frame_id = getattr(state, "frame", None) if state is not None else None
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"{event}_{ts}"
            if frame_id is not None:
                fname += f"_f{frame_id}"
            fname += ".jpg"
            img_path = os.path.join(self._img_dir, fname)
            try:
                if hasattr(image, "save"):
                    image.save(img_path, format="JPEG", quality=85)
            except Exception:
                img_path = None
        if extra:
            rec["extra"] = {k: _safe(v) for k, v in extra.items()}
        if img_path:
            rec["image"] = img_path
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # also write a small text summary for quick inspection
        if img_path:
            txt_name = os.path.splitext(os.path.basename(img_path))[0] + ".txt"
        else:
            ts = time.strftime("%Y%m%d_%H%M%S")
            txt_name = f"{event}_{ts}.txt"
        txt_path = os.path.join(self._txt_dir, txt_name)
        try:
            lines = [
                f"event: {event}",
                f"ts: {rec['ts']}",
            ]
            if img_path:
                lines.append(f"image: {img_path}")
            st = rec.get("state", {}) or {}
            # include key metrics if present
            for k in [
                "frame",
                "is_stopped",
                "free_ratio",
                "ema_free",
                "weighted_free",
                "weighted_occ",
                "closest_norm",
                "occ_left",
                "occ_center",
                "occ_right",
            ]:
                if k in st:
                    lines.append(f"{k}: {st[k]}")
            if "extra" in rec:
                lines.append(f"extra: {rec['extra']}")
            with open(txt_path, "w") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass
