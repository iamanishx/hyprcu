from __future__ import annotations

import subprocess

from .hypr import Target


def get(target: Target) -> str:
    try:
        p = subprocess.run(["wl-paste", "-n"], capture_output=True, text=True,
                           timeout=5, env=target.env())
    except FileNotFoundError:
        raise RuntimeError("wl-paste not found: install 'wl-clipboard'")
    if p.returncode != 0:
        return ""
    return p.stdout


def set_(target: Target, text: str) -> None:
    try:
        subprocess.run(["wl-copy"], input=text, text=True, timeout=5, env=target.env(), check=True)
    except FileNotFoundError:
        raise RuntimeError("wl-copy not found: install 'wl-clipboard'")
