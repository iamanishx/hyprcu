from __future__ import annotations

import argparse
import json
import os
import shutil
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hyprcu", description="Computer use for Hyprland (MCP server)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")
    sub.add_parser("doctor", help="check the environment")
    i = sub.add_parser("init", help="print / run the `claude mcp add` registration")
    i.add_argument("--run", action="store_true", help="execute the claude mcp add command")
    i.add_argument("--scope", default="user")
    s = sub.add_parser("shot", help="take a screenshot (quick manual test)")
    s.add_argument("target", nargs="?", default="screen")
    t = sub.add_parser("tree", help="dump the accessibility tree of a window")
    t.add_argument("window", nargs="?", default="active")
    a = ap.parse_args(argv)

    if a.cmd == "doctor":
        from .doctor import run, format_rows
        ok, rows = run()
        print(format_rows(rows))
        print("\nall good" if ok else "\nproblems found")
        return 0 if ok else 1
    if a.cmd == "init":
        exe = shutil.which("hyprcu") or sys.argv[0]
        cmd = ["claude", "mcp", "add", "-s", a.scope, "hyprcu", "--", os.path.abspath(exe), "serve"]
        print(" ".join(cmd))
        if a.run:
            os.execvp("claude", cmd)
        return 0
    if a.cmd == "shot":
        from . import hypr, screen
        print(json.dumps(screen.capture(hypr.Target.host(), a.target).to_dict(), indent=1))
        return 0
    if a.cmd == "tree":
        from . import hypr, a11y
        _, nodes = a11y.tree(hypr.Target.host(), a.window)
        print("\n".join(n.line() for n in nodes))
        return 0
    from .server import serve
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
