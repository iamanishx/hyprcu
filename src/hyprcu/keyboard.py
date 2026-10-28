"""Keyboard input through wtype (zwp_virtual_keyboard_v1 with a real XKB keymap,
so Unicode and non-US layouts just work). No uinput."""
from __future__ import annotations

import subprocess

from .hypr import Target

MODS = {
    "ctrl": "ctrl", "control": "ctrl",
    "shift": "shift",
    "alt": "alt", "option": "alt",
    "altgr": "altgr",
    "super": "logo", "win": "logo", "meta": "logo", "logo": "logo", "cmd": "logo",
    "capslock": "capslock",
}
KEYS = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "space": "space", "backspace": "BackSpace", "delete": "Delete",
    "del": "Delete", "insert": "Insert", "home": "Home", "end": "End",
    "pageup": "Page_Up", "pagedown": "Page_Down", "pgup": "Page_Up", "pgdn": "Page_Down",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "printscreen": "Print", "print": "Print", "menu": "Menu",
    "plus": "plus", "minus": "minus", "equal": "equal", "comma": "comma", "period": "period",
    "slash": "slash", "backslash": "backslash", "semicolon": "semicolon",
    "apostrophe": "apostrophe", "grave": "grave", "bracketleft": "bracketleft",
    "bracketright": "bracketright",
}
for _i in range(1, 25):
    KEYS[f"f{_i}"] = f"F{_i}"


class KeyError_(RuntimeError):
    pass


def _run(target: Target, args: list[str], timeout: float = 15.0) -> None:
    try:
        p = subprocess.run(["wtype", *args], capture_output=True, text=True,
                           timeout=timeout, env=target.env())
    except FileNotFoundError:
        raise KeyError_("wtype not found: install the 'wtype' package")
    if p.returncode != 0:
        raise KeyError_(f"wtype failed: {p.stderr.strip()}")


def type_text(target: Target, text: str, delay_ms: int = 4) -> None:
    """Type literal text. Newlines are sent as Return."""
    parts = text.split("\n")
    for i, part in enumerate(parts):
        if part:
            _run(target, ["-d", str(delay_ms), "--", part])
        if i + 1 < len(parts):
            _run(target, ["-k", "Return"])


def parse_combo(combo: str) -> tuple[list[str], str]:
    toks = [t.strip() for t in combo.replace("-", "+").split("+") if t.strip()] if combo != "+" else ["+"]
    if not toks:
        raise KeyError_("empty key combo")
    mods, key = [], None
    for t in toks:
        tl = t.lower()
        if tl in MODS and t is not toks[-1]:
            mods.append(MODS[tl])
        elif tl in MODS and len(toks) == 1:
            mods.append(MODS[tl])
        else:
            key = KEYS.get(tl, t)  # fallthrough: assume a valid XKB keysym name or char
    return mods, key


def press_combo(target: Target, combo: str) -> None:
    """'ctrl+shift+t', 'super+1', 'Return', 'alt+F4', 'ctrl+l' ..."""
    mods, key = parse_combo(combo)
    args: list[str] = []
    for m in mods:
        args += ["-M", m]
    if key is not None:
        args += ["-k", key] if len(key) > 1 or not key.isprintable() else ["-k", key]
    for m in reversed(mods):
        args += ["-m", m]
    _run(target, args)


def press_keys(target: Target, combos: list[str]) -> None:
    for c in combos:
        press_combo(target, c)
