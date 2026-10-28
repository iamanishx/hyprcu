<p align="center">
  <h1 align="center">hyprcu</h1>
  <p align="center"><b>Computer use for Hyprland.</b><br/>
  An MCP server that gives Claude Code (or any MCP client) native hands and eyes on your Wayland desktop.<br/>
  <i>No uinput. No root. No ydotool daemon. No portals. Just a well-behaved Wayland client.</i></p>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#attach-to-claude-code">Attach to Claude Code</a> ·
  <a href="#tools">Tools</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#why-not-">Why not …?</a>
</p>

---

Anthropic's official computer use does not exist on Linux. Every cross-platform
"desktop MCP" assumes X11 or macOS APIs and falls over on Wayland, where global
input injection is forbidden by design. hyprcu takes the one route that
actually works on Hyprland: speak the compositor's own protocols.

```
you:    "open calculator and work out 78*6 using the accessibility tree"
claude: launch("gnome-calculator") → find(role="button", name="7") → a11y_click("e15")
        → type("8*6") → key(["Return"]) → wait_for(text="468")   ✓ 468
```

That whole loop ran as the first end-to-end test. No screenshot was needed.

## What you get

| Need            | How hyprcu does it                                                        |
|-----------------|---------------------------------------------------------------------------|
| See             | `grim` (wlr-screencopy); every image returns geometry + scale            |
| Read UI as text | AT-SPI accessibility tree, Wayland's window-relative coords fixed via `hyprctl` |
| Click / scroll  | `zwlr_virtual_pointer_v1` over the Wayland socket (pywayland)            |
| Position cursor | `hyprctl dispatch movecursor` in global logical coords, multi-monitor safe |
| Type / keys     | `wtype` (`zwp_virtual_keyboard_v1`, real XKB keymap, Unicode OK)          |
| Wait            | `wait_for(text=…)` on the tree instead of screenshot polling             |
| Isolate         | optional nested Hyprland: the agent gets its own cursor, focus and clipboard |
| Audit           | every input action journaled to `$XDG_RUNTIME_DIR/hyprcu/journal.jsonl`  |

## Install

Ubuntu / Debian:

```bash
sudo apt install hyprland grim wtype wl-clipboard python3-gi gir1.2-atspi-2.0 at-spi2-core
git clone https://github.com/iamanishx/hyprcu && cd hyprcu
uv venv --python /usr/bin/python3 --system-site-packages   # system python has the GObject bindings
uv pip install -e .
.venv/bin/hyprcu doctor
```

Arch:

```bash
sudo pacman -S grim wtype wl-clipboard python-gobject at-spi2-core
# then the same uv steps
```

`doctor` checks the session, binaries, the virtual-pointer global, screencopy and
the AT-SPI bus, and tells you exactly what is missing.

> The venv must be able to `import gi`, hence `--system-site-packages`. Without
> it the accessibility tools switch off and everything else still works.

## Attach to Claude Code

```bash
claude mcp add -s user hyprcu -- /abs/path/to/hyprcu/.venv/bin/hyprcu serve
# or simply
.venv/bin/hyprcu init --run
```

Launch Claude Code from inside your Hyprland session so the server inherits
`WAYLAND_DISPLAY` and `HYPRLAND_INSTANCE_SIGNATURE`.

Recommended permission split: auto-allow the read-only tools, keep the input
tools behind the approval prompt. hyprcu marks them with MCP `readOnlyHint` /
`destructiveHint` annotations so clients can do this automatically.

## Tools

**Observe** (read-only)

| Tool            | What                                                                       |
|-----------------|----------------------------------------------------------------------------|
| `screenshot`    | focused monitor, a monitor by name, `active`, a window by title/class, or `region=[x,y,w,h]`; `stable=true` waits for the frame to settle |
| `zoom`          | 2x native crop around a point, for small targets                           |
| `tree`          | accessibility tree as indented text: `[ref] role 'name' = value (x,y wxh) {states}` |
| `find`          | elements by role and/or name substring                                     |
| `a11y_text`     | full text of an element                                                    |
| `windows`, `monitors`, `cursor`, `clipboard_get`, `status`                                  |
| `wait_for`      | block until text appears in a window, or a window with a title exists     |

**Act**

| Tool                       | What                                                            |
|----------------------------|-----------------------------------------------------------------|
| `click`, `move`, `drag`, `scroll` | real pointer events at global coordinates                |
| `a11y_click`               | click the center of a tree element by ref                       |
| `a11y_action`              | invoke an element's native action (works even when covered)     |
| `a11y_focus`, `a11y_set_text` | focus an element / replace an input's text with no keystrokes |
| `type`, `key`              | literal text; combos like `["ctrl+l", "Return"]`, `["super+2"]` |
| `focus_window`, `workspace`, `hypr_dispatch` | window management via hyprctl                 |
| `launch`                   | start a program on the current target desktop                   |
| `clipboard_set`            |                                                                 |

**Agent desktop** (experimental)

`desktop_start` spawns a nested Hyprland that appears as one window on your
host. The agent gets its own cursor, focus and clipboard; you keep working.
All tools target it until `desktop_stop`.

### Coordinates

Everything is in Hyprland **global logical** coordinates, the same space as
`hyprctl clients` and `cursorpos`. A screenshot reports `x, y, width, height`
and `scale` (image pixels per logical unit):

```
global_x = x + px / scale
global_y = y + py / scale
```

This is what makes fractional scaling and multi-monitor layouts work without
guesswork.

## How it works

```
 Claude Code ──stdio──▶ hyprcu (python)
                          ├─ hyprctl ─────────▶ windows, monitors, movecursor, focus
                          ├─ pywayland ───────▶ zwlr_virtual_pointer_v1   (buttons, scroll)
                          ├─ wtype ───────────▶ zwp_virtual_keyboard_v1   (text, combos)
                          ├─ grim ────────────▶ wlr-screencopy            (pixels)
                          ├─ AT-SPI (gi) ─────▶ org.a11y.Bus              (UI as text)
                          └─ Hyprland --config ▶ nested agent desktop     (isolation)
```

Why this combination and not uinput: Wayland deliberately forbids global
input injection. `ydotool` works around it with a root daemon and a fake
kernel device, which needs the `input` group, suffers pointer-acceleration
drift on long moves, and does not know where windows are. Hyprland exposes the
virtual-pointer and virtual-keyboard protocols, so a normal client can send
input *with* the compositor's blessing and still ask it where everything is.

Why the accessibility tree first: screenshots cost thousands of tokens per
step and clicks on them are guesses. The tree gives named, sized elements and
exact centers. Pixels are the fallback for apps that expose nothing.

## Safety

- `HYPRCU_READONLY=1` disables every input tool.
- `HYPRCU_ALLOW_HOST_INPUT=0` restricts input to the nested agent desktop.
- Window titles, tree text and screenshots are **untrusted input**. The server
  instructions tell the model so; the client's approval prompt is the real guard.
- The journal in `$XDG_RUNTIME_DIR/hyprcu/journal.jsonl` records every action.
- Screenshots live in `$XDG_RUNTIME_DIR/hyprcu/`, a tmpfs cleared at logout.

| Variable                  | Default | Meaning                                       |
|---------------------------|---------|-----------------------------------------------|
| `HYPRCU_READONLY`         | `0`     | `1` disables all input tools                  |
| `HYPRCU_ALLOW_HOST_INPUT` | `1`     | `0` allows input only on the agent desktop    |
| `HYPRCU_SCREENSHOT_MODE`  | `image` | `path` returns only the file path (saves tokens) |
| `HYPRCU_MAX_DIM`          | `1568`  | longest screenshot side sent to the model     |
| `HYPRCU_A11Y_TIMEOUT_MS`  | `800`   | per-call AT-SPI timeout for frozen apps       |
| `HYPRCU_NESTED_TERMINAL`  | `kitty` | Super+Return inside the agent desktop         |

## Known limits

- **Shared seat.** On the host desktop you and the agent share one cursor and
  keyboard. If you click elsewhere mid-action, keystrokes follow your focus.
  Use `desktop_start` for a separate seat.
- **Chromium / Electron** expose a tree only with `--force-renderer-accessibility`.
  Terminals, games and canvas apps expose nothing: screenshot + click.
- **Hyprland only.** Tested on 0.53. sway and niri speak the same protocols but
  the hyprctl layer is Hyprland-specific. X11 is out of scope.
- Ubuntu's `grim` has no JPEG support; hyprcu captures PNG and re-encodes.

## Why not …?

| Project               | Difference                                                                 |
|-----------------------|----------------------------------------------------------------------------|
| Anthropic computer use| macOS and Windows only                                                     |
| Cua Driver            | X11 / XWayland route; pure Wayland unsupported, Hyprland experimental      |
| computer-use-linux    | portals + uinput + ydotool; validated on GNOME, not Hyprland               |
| hypruse               | same input design, no isolated agent desktop                               |
| hypr-computer         | has the nested desktop, but host input goes through uinput                 |

hyprcu is the union: compositor-native input, tree-first observation, and an
optional isolated seat, in one small Python package.

## Development

```bash
.venv/bin/hyprcu doctor            # environment check
.venv/bin/hyprcu shot active       # quick capture
.venv/bin/hyprcu tree calculator   # dump a window's tree
```

The virtual-pointer binding in `src/hyprcu/protocols/gen/` is generated from the
vendored `wlr-virtual-pointer-unstable-v1.xml` with `python -m pywayland.scanner`.

## License

MIT
