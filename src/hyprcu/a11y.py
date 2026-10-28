"""AT-SPI accessibility tree: read a window as text, find elements, act on them.

On Wayland, apps cannot know their global position, so AT-SPI reports element
extents relative to the toplevel. We add the window's position from hyprctl to
get global logical coordinates. Refs ("e12") are stable for the lifetime of the
server process; call tree()/find() again if a ref goes stale.
"""
from __future__ import annotations

import itertools
import os
from dataclasses import dataclass

from . import hypr
from .hypr import Target

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi  # type: ignore
    Atspi.set_timeout(int(os.environ.get("HYPRCU_A11Y_TIMEOUT_MS", "800")), 1500)
    AVAILABLE = True
    IMPORT_ERROR = ""
except Exception as e:  # pragma: no cover
    Atspi = None
    AVAILABLE = False
    IMPORT_ERROR = str(e)

_refs: dict[str, object] = {}
_ref_meta: dict[str, dict] = {}
_counter = itertools.count(1)

INTERESTING_STATES = ("focused", "checked", "selected", "pressed", "expanded", "editable", "focusable", "sensitive")
SKIP_ROLES = {"filler", "panel", "section", "scroll pane", "viewport", "redundant object", "unknown"}


def _require():
    if not AVAILABLE:
        raise RuntimeError(
            "AT-SPI unavailable: " + IMPORT_ERROR +
            ". Install python3-gi + gir1.2-atspi-2.0 (Debian/Ubuntu) or python-gobject + at-spi2-core (Arch) "
            "and run hyprcu with a Python that can import 'gi' (uv venv --system-site-packages)."
        )


@dataclass
class Node:
    ref: str
    role: str
    name: str
    x: int
    y: int
    width: int
    height: int
    states: list[str]
    depth: int
    value: str = ""

    def line(self) -> str:
        st = ("{" + ",".join(self.states) + "}") if self.states else ""
        val = f" = {self.value!r}" if self.value else ""
        geo = f"({self.x},{self.y} {self.width}x{self.height})" if self.width > 0 else "(offscreen)"
        return f"{'  ' * self.depth}[{self.ref}] {self.role} {self.name!r}{val} {geo} {st}".rstrip()


def _states(acc) -> list[str]:
    try:
        ss = acc.get_state_set()
    except Exception:
        return []
    out = []
    for name in INTERESTING_STATES:
        st = getattr(Atspi.StateType, name.upper(), None)
        if st is not None and ss.contains(st):
            out.append(name)
    return out


def _visible(acc) -> bool:
    try:
        ss = acc.get_state_set()
        return ss.contains(Atspi.StateType.SHOWING) and ss.contains(Atspi.StateType.VISIBLE)
    except Exception:
        return True


def _value(acc) -> str:
    try:
        role = acc.get_role()
        if role in (Atspi.Role.TEXT, Atspi.Role.ENTRY, Atspi.Role.PASSWORD_TEXT, Atspi.Role.TERMINAL,
                    Atspi.Role.PARAGRAPH, Atspi.Role.LABEL, Atspi.Role.STATIC, Atspi.Role.HEADING):
            t = Atspi.Accessible.get_text_iface(acc)
            if t:
                n = Atspi.Text.get_character_count(t)
                if n and n < 400:
                    s = Atspi.Text.get_text(t, 0, n)
                    if s and s != acc.get_name():
                        return s
        v = Atspi.Accessible.get_value_iface(acc)
        if v:
            return str(Atspi.Value.get_current_value(v))
    except Exception:
        pass
    return ""


def _register(acc, meta: dict) -> str:
    ref = f"e{next(_counter)}"
    _refs[ref] = acc
    _ref_meta[ref] = meta
    return ref


def _toplevels():
    """Yield (app_name, toolkit, frame_accessible) for every toplevel AT-SPI knows."""
    _require()
    desk = Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if app is None:
            continue
        try:
            an = app.get_name() or ""
            tk = app.get_toolkit_name() or ""
            for j in range(app.get_child_count()):
                w = app.get_child_at_index(j)
                if w is not None:
                    yield an, tk, w
        except Exception:
            continue


def resolve_window(target: Target, window: str):
    """Match a Hyprland client to its AT-SPI frame. Returns (client, frame, offset)."""
    client = hypr.find_window(target, window)
    title = client["title"]
    cls = client["class"].lower()
    best = None
    for an, tk, w in _toplevels():
        try:
            wn = w.get_name() or ""
        except Exception:
            continue
        if wn == title:
            best = w
            break
        if best is None and (an.lower() in cls or cls in an.lower() or
                             (title and wn and (title in wn or wn in title))):
            best = w
    if best is None:
        raise RuntimeError(
            f"window {title!r} ({client['class']}) exposes no accessibility tree. "
            "Chromium/Electron apps need --force-renderer-accessibility, terminals and canvas apps expose nothing; "
            "use screenshot() instead."
        )
    return client, best


def _extents(acc, ox: int, oy: int) -> tuple[int, int, int, int]:
    try:
        e = acc.get_extents(Atspi.CoordType.WINDOW)
        if e.width <= 0 and e.height <= 0:
            e = acc.get_extents(Atspi.CoordType.SCREEN)
        return ox + e.x, oy + e.y, e.width, e.height
    except Exception:
        return ox, oy, 0, 0


def tree(target: Target, window: str = "active", max_depth: int = 12, max_nodes: int = 400,
         include_all: bool = False) -> tuple[dict, list[Node]]:
    client, frame = resolve_window(target, window)
    ox, oy = client["x"], client["y"]
    nodes: list[Node] = []

    def walk(acc, depth: int):
        if len(nodes) >= max_nodes or depth > max_depth:
            return
        try:
            role = acc.get_role_name()
            name = acc.get_name() or ""
        except Exception:
            return
        if not include_all and not _visible(acc):
            return
        x, y, w, h = _extents(acc, ox, oy)
        boring = (role in SKIP_ROLES and not name)
        if not boring or depth == 0:
            ref = _register(acc, {"window": client["address"], "ox": ox, "oy": oy})
            nodes.append(Node(ref, role, name, x, y, w, h, _states(acc), depth, _value(acc)))
            child_depth = depth + 1
        else:
            child_depth = depth  # collapse boring containers
        try:
            n = acc.get_child_count()
        except Exception:
            return
        for i in range(min(n, 200)):
            c = acc.get_child_at_index(i)
            if c is not None:
                walk(c, child_depth)

    walk(frame, 0)
    return client, nodes


def find(target: Target, window: str = "active", role: str | None = None, name: str | None = None,
         exact: bool = False, limit: int = 30) -> tuple[dict, list[Node]]:
    client, nodes = tree(target, window, max_depth=30, max_nodes=3000)
    r = role.lower() if role else None
    q = name.lower() if name else None
    out = []
    for n in nodes:
        if r and r not in n.role.lower():
            continue
        if q:
            hay = (n.name + " " + n.value).lower()
            if (exact and q != n.name.lower()) or (not exact and q not in hay):
                continue
        out.append(n)
        if len(out) >= limit:
            break
    return client, out


def get(ref: str):
    if ref not in _refs:
        raise RuntimeError(f"unknown ref {ref!r}; call tree()/find() first (refs are not stable across calls)")
    return _refs[ref], _ref_meta[ref]


def center(ref: str) -> tuple[int, int]:
    acc, meta = get(ref)
    x, y, w, h = _extents(acc, meta["ox"], meta["oy"])
    if w <= 0 or h <= 0:
        raise RuntimeError(f"{ref} has no on-screen extents (offscreen/collapsed?)")
    return x + w // 2, y + h // 2


def actions(ref: str) -> list[str]:
    acc, _ = get(ref)
    a = Atspi.Accessible.get_action_iface(acc)
    if not a:
        return []
    return [Atspi.Action.get_action_name(a, i) for i in range(Atspi.Action.get_n_actions(a))]


def do_action(ref: str, index: int = 0) -> bool:
    acc, _ = get(ref)
    a = Atspi.Accessible.get_action_iface(acc)
    if not a or Atspi.Action.get_n_actions(a) == 0:
        raise RuntimeError(f"{ref} has no AT-SPI actions; use click on its center instead")
    return bool(Atspi.Action.do_action(a, index))


def text(ref: str, max_chars: int = 20000) -> str:
    acc, _ = get(ref)
    t = Atspi.Accessible.get_text_iface(acc)
    if not t:
        raise RuntimeError(f"{ref} has no text interface")
    n = Atspi.Text.get_character_count(t)
    return Atspi.Text.get_text(t, 0, min(n, max_chars))


def set_text(ref: str, value: str) -> bool:
    acc, _ = get(ref)
    et = Atspi.Accessible.get_editable_text_iface(acc)
    if not et:
        raise RuntimeError(f"{ref} is not editable text")
    return bool(Atspi.EditableText.set_text_contents(et, value))


def focus(ref: str) -> bool:
    acc, _ = get(ref)
    comp = Atspi.Accessible.get_component_iface(acc)
    if not comp:
        return False
    return bool(Atspi.Component.grab_focus(comp))
