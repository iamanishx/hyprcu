"""Screenshots via grim (wlr-screencopy). Every capture returns the geometry it
covers in global logical coordinates plus `scale` = image pixels per logical
unit, so:  global_x = geometry.x + px / scale ;  global_y = geometry.y + py / scale."""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image

from . import hypr
from .hypr import Target

MAX_DIM = int(os.environ.get("HYPRCU_MAX_DIM", "1568"))


def outdir() -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hyprcu"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    return base


@dataclass
class Capture:
    path: str
    x: int
    y: int
    width: int   # logical
    height: int  # logical
    scale: float  # image px per logical unit
    image_width: int
    image_height: int
    format: str
    note: str = "global = (x + px/scale, y + py/scale)"

    def to_dict(self) -> dict:
        return asdict(self)


def _grim(target: Target, args: list[str], path: Path, lossless: bool = True) -> None:
    # Always PNG from grim (Ubuntu's build has no JPEG); Pillow re-encodes below.
    try:
        p = subprocess.run(["grim", "-t", "png", *args, str(path)], capture_output=True, text=True,
                           timeout=10, env=target.env())
    except FileNotFoundError:
        raise RuntimeError("grim not found: install the 'grim' package")
    if p.returncode != 0:
        raise RuntimeError(f"grim failed: {p.stderr.strip()}")


def _finish(path: Path, geom: tuple[int, int, int, int], native_scale: float, lossless: bool,
            max_dim: int | None) -> Capture:
    img = Image.open(path)
    iw, ih = img.size
    scale = native_scale
    limit = MAX_DIM if max_dim is None else max_dim
    if limit and max(iw, ih) > limit:
        f = limit / max(iw, ih)
        img = img.resize((max(1, round(iw * f)), max(1, round(ih * f))), Image.LANCZOS)
        iw, ih = img.size
        scale = native_scale * f
    x, y, w, h = geom
    if lossless:
        img.save(path, format="PNG")
        out = path
    else:
        out = path.with_suffix(".jpg")
        img.convert("RGB").save(out, format="JPEG", quality=88)
        path.unlink(missing_ok=True)
    return Capture(str(out), x, y, w, h, round(scale, 4), iw, ih, "png" if lossless else "jpeg")


def _region_args(x: int, y: int, w: int, h: int) -> list[str]:
    return ["-g", f"{x},{y} {w}x{h}"]


def _digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def capture(target: Target, what: str = "screen", region: tuple[int, int, int, int] | None = None,
            lossless: bool = False, stable: bool = False, upscale: float = 1.0,
            max_dim: int | None = None) -> Capture:
    """what: 'screen' (focused monitor), a monitor name, 'active', a window
    address/title, or 'region' with region=(x,y,w,h) in logical coordinates."""
    ts = time.strftime("%H%M%S") + f"{int(time.time()*1000)%1000:03d}"
    path = outdir() / f"{what.replace('/', '_')[:24]}-{ts}.png"
    mons = hypr.monitors(target)

    if region is not None or what == "region":
        if region is None:
            raise ValueError("region=(x,y,w,h) required")
        x, y, w, h = (int(v) for v in region)
        mon = hypr.monitor_at(target, x + w / 2, y + h / 2) or mons[0]
        args = _region_args(x, y, w, h)
        geom, native = (x, y, w, h), mon["scale"]
    elif what == "screen" or any(m["name"] == what for m in mons):
        mon = next((m for m in mons if m["name"] == what), None) or \
              next((m for m in mons if m["focused"]), mons[0])
        args = ["-o", mon["name"]]
        geom, native = (mon["x"], mon["y"], mon["width"], mon["height"]), mon["scale"]
    else:
        win = hypr.find_window(target, what)
        x, y, w, h = win["x"], win["y"], win["width"], win["height"]
        mon = hypr.monitor_at(target, x + w / 2, y + h / 2) or mons[0]
        args = _region_args(x, y, w, h)
        geom, native = (x, y, w, h), mon["scale"]

    if upscale and upscale != 1.0:
        args = ["-s", str(upscale), *args]
        native = native * upscale

    _grim(target, args, path, lossless)
    if stable:
        prev = _digest(path)
        for _ in range(6):
            time.sleep(0.15)
            _grim(target, args, path, lossless)
            cur = _digest(path)
            if cur == prev:
                break
            prev = cur
    return _finish(path, geom, native, lossless, max_dim)


def zoom(target: Target, x: int, y: int, radius: int = 120, lossless: bool = True) -> Capture:
    """Native-resolution (2x upscaled) crop around a global point, for hitting small targets."""
    mon = hypr.monitor_at(target, x, y)
    if not mon:
        raise ValueError(f"({x},{y}) is not on any monitor")
    rx = max(mon["x"], x - radius)
    ry = max(mon["y"], y - radius)
    rw = min(mon["x"] + mon["width"], x + radius) - rx
    rh = min(mon["y"] + mon["height"], y + radius) - ry
    return capture(target, "region", region=(rx, ry, rw, rh), lossless=lossless, upscale=2.0, max_dim=0)
