#!/usr/bin/env python3
"""Read clipboard text through XWayland and write one JSON object per line.

GNOME on Wayland hides clipboard contents from background Wayland clients.
The X11 bridge still exposes them, so this process stays on GDK_BACKEND=x11.
"""

from __future__ import annotations

import json
import os
import sys

os.environ["GDK_BACKEND"] = "x11"

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

MAX_CHARS = 200_000


def main() -> int:
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    pending = {"id": 0}

    def emit(text: str | None) -> bool:
        pending["id"] = 0
        if not text or not str(text).strip():
            return False
        text = str(text).replace("\x00", "")
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
        sys.stdout.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return False

    def schedule(*_args) -> None:
        if pending["id"]:
            GLib.source_remove(pending["id"])
        pending["id"] = GLib.timeout_add(80, lambda: emit(cb.wait_for_text()))

    cb.connect("owner-change", schedule)
    GLib.idle_add(lambda: emit(cb.wait_for_text()))
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
