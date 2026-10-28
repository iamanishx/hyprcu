"""Thin hyprctl layer. All coordinates are Hyprland *global logical* coordinates,
the same space hyprctl uses for `clients[].at`, `cursorpos` and `movecursor`."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """Which Hyprland instance to talk to. Host = the session we were started in."""
    signature: str
    wayland_display: str
    name: str = "host"

    @classmethod
    def host(cls) -> "Target":
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        wd = os.environ.get("WAYLAND_DISPLAY")
        if not sig or not wd:
            raise RuntimeError(
                "HYPRLAND_INSTANCE_SIGNATURE / WAYLAND_DISPLAY not set: "
                "hyprcu must be started inside a Hyprland session"
            )
        return cls(sig, wd, "host")

    def env(self) -> dict[str, str]:
        e = dict(os.environ)
        e["HYPRLAND_INSTANCE_SIGNATURE"] = self.signature
        e["WAYLAND_DISPLAY"] = self.wayland_display
        return e


class HyprError(RuntimeError):
    pass


def hyprctl(target: Target, *args: str, as_json: bool = True, timeout: float = 5.0):
    cmd = ["hyprctl", "--instance", target.signature]
    if as_json:
        cmd.append("-j")
    cmd += list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=target.env())
    except FileNotFoundError:
        raise HyprError("hyprctl not found in PATH")
    except subprocess.TimeoutExpired:
        raise HyprError(f"hyprctl {' '.join(args)} timed out")
    out = p.stdout.strip()
    if p.returncode != 0:
        raise HyprError(f"hyprctl {' '.join(args)} failed: {p.stderr.strip() or out}")
    if not as_json:
        return out
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise HyprError(f"hyprctl {' '.join(args)} returned non-JSON: {out[:200]}")


def dispatch(target: Target, *args: str) -> str:
    out = hyprctl(target, "dispatch", *args, as_json=False)
    if out.lower() not in ("ok", ""):
        raise HyprError(f"dispatch {' '.join(args)}: {out}")
    return out


# ---- queries ---------------------------------------------------------------

def monitors(target: Target) -> list[dict]:
    res = []
    for m in hyprctl(target, "monitors"):
        scale = float(m.get("scale") or 1.0)
        w, h = m["width"], m["height"]
        if m.get("transform", 0) in (1, 3, 5, 7):  # 90/270 degree rotations
            w, h = h, w
        res.append({
            "name": m["name"],
            "x": m["x"], "y": m["y"],
            "width": round(w / scale), "height": round(h / scale),  # logical
            "pixel_width": w, "pixel_height": h,
            "scale": scale,
            "focused": bool(m.get("focused")),
            "active_workspace": (m.get("activeWorkspace") or {}).get("id"),
        })
    return res


def monitor_at(target: Target, x: float, y: float) -> dict | None:
    for m in monitors(target):
        if m["x"] <= x < m["x"] + m["width"] and m["y"] <= y < m["y"] + m["height"]:
            return m
    return None


def clients(target: Target, mapped_only: bool = True) -> list[dict]:
    res = []
    for c in hyprctl(target, "clients"):
        if mapped_only and not c.get("mapped", True):
            continue
        res.append({
            "address": c["address"],
            "title": c.get("title", ""),
            "class": c.get("class", ""),
            "pid": c.get("pid"),
            "x": c["at"][0], "y": c["at"][1],
            "width": c["size"][0], "height": c["size"][1],
            "workspace": (c.get("workspace") or {}).get("id"),
            "monitor": c.get("monitor"),
            "floating": bool(c.get("floating")),
            "fullscreen": c.get("fullscreen", 0),
            "focus_order": c.get("focusHistoryID"),
            "hidden": bool(c.get("hidden")),
        })
    res.sort(key=lambda c: (c["focus_order"] if c["focus_order"] is not None else 999))
    return res


def active_window(target: Target) -> dict | None:
    c = hyprctl(target, "activewindow")
    if not c or "address" not in c:
        return None
    return {
        "address": c["address"], "title": c.get("title", ""), "class": c.get("class", ""),
        "pid": c.get("pid"),
        "x": c["at"][0], "y": c["at"][1], "width": c["size"][0], "height": c["size"][1],
        "workspace": (c.get("workspace") or {}).get("id"),
    }


def find_window(target: Target, ref: str) -> dict:
    """Resolve 'active', an address (0x...), or a case-insensitive title/class substring."""
    if ref in ("active", "focused", ""):
        w = active_window(target)
        if not w:
            raise HyprError("no active window")
        return w
    cs = clients(target)
    if ref.startswith("0x"):
        for c in cs:
            if c["address"] == ref:
                return c
        raise HyprError(f"no window with address {ref}")
    r = ref.lower()
    for c in cs:
        if r == c["class"].lower() or r == c["title"].lower():
            return c
    for c in cs:
        if r in c["title"].lower() or r in c["class"].lower():
            return c
    raise HyprError(f"no window matching {ref!r}; call windows() to list them")


def cursor_pos(target: Target) -> tuple[int, int]:
    c = hyprctl(target, "cursorpos")
    return int(c["x"]), int(c["y"])


# ---- actions ---------------------------------------------------------------

def move_cursor(target: Target, x: float, y: float) -> None:
    dispatch(target, "movecursor", str(int(round(x))), str(int(round(y))))


def focus_window(target: Target, address: str) -> None:
    dispatch(target, "focuswindow", f"address:{address}")
    time.sleep(0.05)


def switch_workspace(target: Target, ws: int | str) -> None:
    dispatch(target, "workspace", str(ws))


def instances() -> list[dict]:
    p = subprocess.run(["hyprctl", "instances", "-j"], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return []
