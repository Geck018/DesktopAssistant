#!/usr/bin/env python3
"""Persistent state for the morning assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = APP_DIR / "state"
LAST_BRIEF = STATE_DIR / "last_brief_date"
FIRED_SLOTS = STATE_DIR / "fired_slots"
LOG_FILE = STATE_DIR / "assistant.log"


def ensure() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STATE_DIR.chmod(0o777)
    except Exception:
        pass
    if not LOG_FILE.exists():
        try:
            LOG_FILE.touch()
            LOG_FILE.chmod(0o666)
        except Exception:
            pass


def today_str() -> str:
    return date.today().isoformat()


def brief_already_shown_today() -> bool:
    ensure()
    if not LAST_BRIEF.exists():
        return False
    try:
        return LAST_BRIEF.read_text(encoding="utf-8").strip() == today_str()
    except OSError:
        return False


def mark_brief_shown() -> None:
    ensure()
    try:
        LAST_BRIEF.write_text(today_str() + "\n", encoding="utf-8")
        LAST_BRIEF.chmod(0o666)
    except OSError:
        pass


def slot_key(day: str, time_hhmm: str) -> str:
    return f"{day}T{time_hhmm}"


def slot_already_fired(time_hhmm: str, day: str | None = None) -> bool:
    ensure()
    day = day or today_str()
    key = slot_key(day, time_hhmm)
    if not FIRED_SLOTS.exists():
        return False
    try:
        return key in {
            line.strip()
            for line in FIRED_SLOTS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except OSError:
        return False


def mark_slot_fired(time_hhmm: str, day: str | None = None) -> None:
    ensure()
    day = day or today_str()
    key = slot_key(day, time_hhmm)
    existing: list[str] = []
    if FIRED_SLOTS.exists():
        try:
            existing = [
                line.strip()
                for line in FIRED_SLOTS.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            existing = []
    yday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    pruned = [e for e in existing if e.startswith(day) or e.startswith(yday)]
    if key not in pruned:
        pruned.append(key)
    try:
        FIRED_SLOTS.write_text("\n".join(pruned) + "\n", encoding="utf-8")
        FIRED_SLOTS.chmod(0o666)
    except OSError:
        pass


def log(msg: str) -> None:
    ensure()
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
        try:
            LOG_FILE.chmod(0o666)
        except Exception:
            pass
    except OSError:
        try:
            fallback = Path(f"/tmp/assistant-log-{today_str()}.txt")
            with fallback.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass
