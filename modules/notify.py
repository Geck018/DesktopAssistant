#!/usr/bin/env python3
"""Desktop notifications + ping summaries."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from modules import config as cfg_mod
from modules import todos as todo_mod
from modules import updates as upd_mod

APP_DIR = Path(__file__).resolve().parent.parent
TODO_PATH = APP_DIR / "todo.md"
ICON_PATH = APP_DIR / "icon.png"


def send(title: str, body: str, urgency: str = "normal") -> None:
    if not shutil.which("notify-send"):
        return
    cmd = [
        "notify-send",
        "--app-name=Assistant",
        f"--urgency={urgency}",
        "--expire-time=12000",
    ]
    if ICON_PATH.exists():
        cmd.append(f"--icon={ICON_PATH}")
    else:
        cmd.append("--icon=checkbox-checked-symbolic")
    # Click hint — GNOME may ignore; still useful elsewhere
    cmd.extend(["--action=default=Open", title, body])
    subprocess.run(cmd, check=False, capture_output=True)


def build_summary() -> tuple[str, str, int, int, bool]:
    """Returns title, body, open_todos, updates, is_empty."""
    items = todo_mod.load_items(TODO_PATH)
    open_items = todo_mod.open_items(items)
    report = upd_mod.gather(refresh=False)
    open_n = len(open_items)
    upd_n = report.total

    title = "Assistant check-in"
    lines: list[str] = []
    if open_n:
        lines.append(f"{open_n} open todo(s):")
        for it in open_items[:5]:
            lines.append(f"• {it.text}")
        if open_n > 5:
            lines.append(f"…and {open_n - 5} more")
    else:
        lines.append("No open todos.")

    if upd_n:
        lines.append(f"\n{upd_n} system update(s) available.")
    else:
        lines.append("\nSystem packages look current.")

    if report.reboot_required:
        lines.append("Reboot pending when you’re ready.")

    empty = open_n == 0 and upd_n == 0
    return title, "\n".join(lines), open_n, upd_n, empty


def maybe_notify(force: bool = False) -> bool:
    """Send notification unless empty and notify_if_empty is false. Returns whether sent."""
    cfg = cfg_mod.load()
    title, body, _o, _u, empty = build_summary()
    if empty and not cfg.get("notify_if_empty", False) and not force:
        return False
    send(title, body, urgency="normal" if empty else "normal")
    return True
