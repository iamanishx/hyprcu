from __future__ import annotations

import os
import shutil
import subprocess


def run() -> tuple[bool, list[tuple[str, bool, str]]]:
    rows: list[tuple[str, bool, str]] = []
    ok_all = True

    def add(name, ok, msg):
        nonlocal ok_all
        rows.append((name, ok, msg))
        if not ok:
            ok_all = False

    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    wd = os.environ.get("WAYLAND_DISPLAY")
    add("session", bool(sig and wd), f"HYPRLAND_INSTANCE_SIGNATURE={'set' if sig else 'MISSING'} WAYLAND_DISPLAY={wd or 'MISSING'}")

    for b, why in [("hyprctl", "required"), ("grim", "screenshots"), ("wtype", "typing/keys"),
                   ("wl-copy", "clipboard (optional)"), ("Hyprland", "nested agent desktop (optional)")]:
        p = shutil.which(b)
        add(b, p is not None or "optional" in why, f"{p or 'MISSING'}  ({why})")

    try:
        v = subprocess.run(["hyprctl", "version"], capture_output=True, text=True, timeout=5).stdout.splitlines()[0]
        add("hyprland", True, v.strip())
    except Exception as e:
        add("hyprland", False, f"hyprctl version failed: {e}")

    try:
        from . import hypr
        t = hypr.Target.host()
        mons = hypr.monitors(t)
        frac = [m for m in mons if m["scale"] != int(m["scale"])]
        add("monitors", True, ", ".join(f"{m['name']} {m['width']}x{m['height']}@{m['scale']} +{m['x']},{m['y']}" for m in mons)
            + ("  [fractional scale: coordinates still logical, images are scaled]" if frac else ""))
    except Exception as e:
        add("monitors", False, str(e))

    try:
        from .pointer import VirtualPointer
        p = VirtualPointer()
        p.close()
        add("virtual-pointer", True, "zwlr_virtual_pointer_manager_v1 bound (no uinput needed)")
    except Exception as e:
        add("virtual-pointer", False, str(e))

    try:
        p = subprocess.run(["grim", "-t", "png", "-"], capture_output=True, timeout=10)
        add("screencopy", p.returncode == 0 and len(p.stdout) > 1000,
            f"grim produced {len(p.stdout)} bytes" if p.returncode == 0 else p.stderr.decode().strip())
    except Exception as e:
        add("screencopy", False, str(e))

    try:
        from . import a11y
        if not a11y.AVAILABLE:
            raise RuntimeError(a11y.IMPORT_ERROR)
        desk = a11y.Atspi.get_desktop(0)
        n = desk.get_child_count()
        add("at-spi", True, f"bus reachable, {n} applications registered")
        gm = os.environ.get("GTK_MODULES", "")
        if "atk-bridge" not in gm:
            add("gtk3-a11y", True, "GTK_MODULES lacks atk-bridge (GTK3 apps may expose nothing); GTK4 is fine")
    except Exception as e:
        add("at-spi", False, f"{e}  -> install python3-gi gir1.2-atspi-2.0 at-spi2-core and use a venv with --system-site-packages")

    add("readonly", True, "HYPRCU_READONLY=" + os.environ.get("HYPRCU_READONLY", "0"))
    return ok_all, rows


def format_rows(rows) -> str:
    return "\n".join(f"{'OK ' if ok else 'ERR'}  {name:<16} {msg}" for name, ok, msg in rows)
