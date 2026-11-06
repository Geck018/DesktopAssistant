#!/usr/bin/env python3
"""Todo list backed by todo.md."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path

TODO_RE = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.*)$")
_UID = itertools.count(1)


@dataclass
class Item:
    text: str
    done: bool = False
    uid: int = field(default_factory=lambda: next(_UID))


def load_items(path: Path) -> list[Item]:
    if not path.exists():
        path.write_text("# Todos\n\n", encoding="utf-8")
    items: list[Item] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TODO_RE.match(line)
        if m:
            items.append(Item(text=m.group(3).rstrip(), done=m.group(2).lower() == "x"))
    return items


def save_items(path: Path, items: list[Item]) -> None:
    lines = ["# Todos", ""]
    for it in items:
        mark = "x" if it.done else " "
        lines.append(f"- [{mark}] {it.text}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def open_items(items: list[Item]) -> list[Item]:
    return [i for i in items if not i.done]
