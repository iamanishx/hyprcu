"""Nested Hyprland = an isolated agent desktop that appears as one window on the
host. The agent gets its own cursor, focus and clipboard; the user keeps working.
Experimental: it depends on Hyprland's Wayland backend behaving when nested."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import hypr
from .hypr import Target

CONF = """
monitor=,{w}x{h},auto,1
misc {{
    disable_hyprland_logo = true
    disable_splash_rendering = true
    force_default_wallpaper = 0
}}
animations {{ enabled = false }}
decoration {{ blur {{ enabled = false }} }}
general {{ gaps_in = 2
    gaps_out = 4
    border_size = 1 }}
input {{ follow_mouse = 1 }}
bind = SUPER, Q, killactive
bind = SUPER, RETURN, exec, {term}
{extra}
"""

_proc: subprocess.Popen | None = None
_target: Target | None = None


def status() -> dict:
    alive = _proc is not None and _proc.poll() is None
    return {"running": alive, "pid": _proc.pid if alive else None,
            "target": _target.__dict__ if (alive and _target) else None}


def start(host: Target, width: int = 1280, height: int = 800, extra_conf: str = "") -> Target:
    global _proc, _target
    if status()["running"]:
        return _target  # type: ignore
    rt = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hyprcu"
    rt.mkdir(parents=True, exist_ok=True, mode=0o700)
    conf = rt / "nested.conf"
    term = os.environ.get("HYPRCU_NESTED_TERMINAL", "kitty")
    conf.write_text(CONF.format(w=width, h=height, term=term, extra=extra_conf))
    before = {i["instance"] for i in hypr.instances()}
    env = host.env()
    log = (rt / "nested.log").open("ab")
    _proc = subprocess.Popen(["Hyprland", "--config", str(conf)], env=env,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + 15
    new = None
    while time.time() < deadline:
        if _proc.poll() is not None:
            raise RuntimeError(f"nested Hyprland exited with {_proc.returncode}; see {rt/'nested.log'}")
        for i in hypr.instances():
            if i["instance"] not in before:
                new = i
        if new and new.get("wl_socket"):
            try:
                hypr.monitors(Target(new["instance"], new["wl_socket"], "agent"))
                break
            except Exception:
                pass
        time.sleep(0.3)
    if not new:
        raise RuntimeError("nested Hyprland did not register an instance in 15s")
    _target = Target(new["instance"], new["wl_socket"], "agent")
    return _target


def stop() -> bool:
    global _proc, _target
    if _proc is None:
        return False
    try:
        hypr.dispatch(_target, "exit") if _target else None
    except Exception:
        pass
    try:
        _proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        _proc.kill()
    _proc, _target = None, None
    return True


def target() -> Target | None:
    return _target if status()["running"] else None
