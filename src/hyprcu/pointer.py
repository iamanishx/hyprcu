"""Virtual pointer over the Wayland wire (zwlr_virtual_pointer_v1).

No uinput, no root, no daemon: we are an ordinary Wayland client of the
compositor we were started under. Absolute positioning is deliberately NOT
done with motion_absolute (it is buggy across multi-monitor layouts in
Hyprland); callers position the cursor with `hyprctl dispatch movecursor`
and use this class only for buttons and scroll.
"""
from __future__ import annotations

import os
import time

from pywayland.client import Display
from pywayland.protocol.wayland import WlSeat

from .protocols.gen.wlr_virtual_pointer_unstable_v1 import ZwlrVirtualPointerManagerV1

BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
BTN_SIDE, BTN_EXTRA = 0x113, 0x114
BUTTONS = {
    "left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE,
    "back": BTN_SIDE, "forward": BTN_EXTRA,
}
AXIS_V, AXIS_H = 0, 1
PRESSED, RELEASED = 1, 0


def _now_ms() -> int:
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


class VirtualPointer:
    """One connection + one virtual pointer. Create lazily, reuse, close on exit."""

    def __init__(self, wayland_display: str | None = None):
        if wayland_display:
            os.environ["WAYLAND_DISPLAY"] = wayland_display
        self.display = Display(wayland_display)
        self.display.connect()
        self._manager = None
        self._seat = None
        reg = self.display.get_registry()
        reg.dispatcher["global"] = self._on_global
        self.display.roundtrip()
        if self._manager is None:
            self.display.disconnect()
            raise RuntimeError(
                "compositor does not expose zwlr_virtual_pointer_manager_v1 "
                "(is this Hyprland / a wlroots-style compositor?)"
            )
        self.pointer = self._manager.create_virtual_pointer(self._seat)
        self.display.roundtrip()

    def _on_global(self, registry, name, interface, version):
        if interface == "zwlr_virtual_pointer_manager_v1":
            self._manager = registry.bind(name, ZwlrVirtualPointerManagerV1, min(version, 2))
        elif interface == "wl_seat" and self._seat is None:
            self._seat = registry.bind(name, WlSeat, min(version, 7))

    # -- primitives --------------------------------------------------------
    def _flush(self):
        self.display.roundtrip()

    def press(self, button: str = "left"):
        self.pointer.button(_now_ms(), BUTTONS[button], PRESSED)
        self.pointer.frame()
        self._flush()

    def release(self, button: str = "left"):
        self.pointer.button(_now_ms(), BUTTONS[button], RELEASED)
        self.pointer.frame()
        self._flush()

    def click(self, button: str = "left", count: int = 1, interval: float = 0.08):
        for i in range(count):
            self.press(button)
            time.sleep(0.03)
            self.release(button)
            if i + 1 < count:
                time.sleep(interval)

    def move_relative(self, dx: float, dy: float):
        self.pointer.motion(_now_ms(), dx, dy)
        self.pointer.frame()
        self._flush()

    def scroll(self, dx: float = 0, dy: float = 0, steps: int = 1):
        """dy > 0 scrolls down (content moves up), like a mouse wheel.
        One `step` is one wheel notch (15 units + discrete 1)."""
        for _ in range(max(1, steps)):
            t = _now_ms()
            self.pointer.axis_source(0)  # wheel
            if dy:
                v = 15.0 if dy > 0 else -15.0
                self.pointer.axis_discrete(t, AXIS_V, v, 1 if dy > 0 else -1)
            if dx:
                v = 15.0 if dx > 0 else -15.0
                self.pointer.axis_discrete(t, AXIS_H, v, 1 if dx > 0 else -1)
            self.pointer.frame()
            self._flush()
            time.sleep(0.02)

    def close(self):
        try:
            self.pointer.destroy()
            self.display.roundtrip()
        finally:
            self.display.disconnect()
