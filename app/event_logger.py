import json
import os
import time


class EventLogger:
    def __init__(self, log_dir: str = "logs", filename: str | None = None):
        os.makedirs(log_dir, exist_ok=True)
        if filename is None:
            filename = time.strftime("drive_%Y%m%d_%H%M%S.jsonl")
        self.path = os.path.join(log_dir, filename)
        self._f = open(self.path, "a", buffering=1)  # line-buffered
        print(f"[LOG] Writing events to: {self.path}")

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

    def write(self, event: str, **fields):
        rec = {
            "ts": time.time(),
            "event": event,
            **fields,
        }
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")