from __future__ import annotations

import json
import os
import time
from pathlib import Path


def path() -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hyprcu"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base / "journal.jsonl"


def log(tool: str, **kw) -> None:
    rec = {"t": round(time.time(), 3), "tool": tool, **kw}
    try:
        with path().open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass
