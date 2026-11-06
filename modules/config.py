#!/usr/bin/env python3
"""Load assistant config (schedule, etc.)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULT = {
    "schedule": [
        {"time": "09:00", "action": "both"},
        {"time": "13:00", "action": "notify"},
        {"time": "17:00", "action": "both"},
    ],
    "notify_if_empty": False,
    "theme": "sakura",
}


@dataclass
class Slot:
    time: str  # HH:MM
    action: str  # notify | open | both

    @property
    def hour_minute(self) -> tuple[int, int]:
        h, m = self.time.split(":")
        return int(h), int(m)


def load() -> dict:
    if not CONFIG_PATH.exists():
        save(DEFAULT)
        return deepcopy(DEFAULT)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    merged = deepcopy(DEFAULT)
    merged.update({k: v for k, v in data.items() if k != "comment"})
    if "schedule" in data:
        merged["schedule"] = data["schedule"]
    return merged


def save(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def theme_name(cfg: dict | None = None) -> str:
    name = str((cfg or load()).get("theme", "sakura"))
    return name if name in ("sakura", "phyrexia", "emperors") else "sakura"


def set_theme(name: str) -> None:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        data = deepcopy(DEFAULT)
    data["theme"] = name if name in ("sakura", "phyrexia", "emperors") else "sakura"
    save(data)


def slots(cfg: dict | None = None) -> list[Slot]:
    cfg = cfg or load()
    out: list[Slot] = []
    for row in cfg.get("schedule", []):
        t = str(row.get("time", "")).strip()
        a = str(row.get("action", "both")).strip().lower()
        if not t or a not in ("notify", "open", "both"):
            continue
        try:
            Slot(time=t, action=a).hour_minute
        except Exception:
            continue
        out.append(Slot(time=t, action=a))
    return out
