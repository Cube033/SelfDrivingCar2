import json
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Optional


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

    def write(self, event: str, state: Any, **extra: Any) -> None:
        rec = {
            "ts": time.time(),
            "event": event,
            "state": _safe(state),
        }
        if extra:
            rec["extra"] = {k: _safe(v) for k, v in extra.items()}
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")