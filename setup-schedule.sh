#!/usr/bin/env bash
# Install systemd --user timers from config.json so pings fire even if the app isn't open.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
STATE_DIR="$DIR/state"
mkdir -p "$STATE_DIR" "$UNIT_DIR"

remove_all() {
  systemctl --user daemon-reload 2>/dev/null || true
  for u in $(systemctl --user list-unit-files 'assistant-ping-*.timer' --no-legend 2>/dev/null | awk '{print $1}'); do
    systemctl --user disable --now "$u" 2>/dev/null || true
  done
  rm -f "$UNIT_DIR"/assistant-ping-*.timer "$UNIT_DIR"/assistant-ping-*.service
  rm -f "$STATE_DIR/schedule-units.txt"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "Removed all assistant-ping timers."
}

if [[ "${1:-}" == "--remove" ]]; then
  remove_all
  exit 0
fi

python3 - "$DIR" "$UNIT_DIR" "$STATE_DIR" <<'PY'
import json, re, sys
from pathlib import Path

app_dir, unit_dir, state_dir = map(Path, sys.argv[1:4])
unit_dir.mkdir(parents=True, exist_ok=True)
state_dir.mkdir(parents=True, exist_ok=True)

cfg = json.loads((app_dir / "config.json").read_text())
slots = cfg.get("schedule", [])
if not slots:
    print("No schedule entries in config.json", file=sys.stderr)
    sys.exit(1)

for p in unit_dir.glob("assistant-ping-*.timer"):
    p.unlink(missing_ok=True)
for p in unit_dir.glob("assistant-ping-*.service"):
    p.unlink(missing_ok=True)

enabled = []
for row in slots:
    t = str(row.get("time", "")).strip()
    action = str(row.get("action", "both")).strip().lower()
    if not re.fullmatch(r"\d{1,2}:\d{2}", t) or action not in ("notify", "open", "both"):
        print(f"Skipping invalid slot: {row}")
        continue
    hh, mm = [int(x) for x in t.split(":")]
    stamp = f"{hh:02d}{mm:02d}"
    name = f"assistant-ping-{stamp}"
    (unit_dir / f"{name}.service").write_text(
        f"""[Unit]
Description=Assistant scheduled ping at {hh:02d}:{mm:02d} ({action})

[Service]
Type=oneshot
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
WorkingDirectory={app_dir}
StandardOutput=append:{app_dir}/state/assistant.log
StandardError=append:{app_dir}/state/assistant.log
ExecStart=/usr/bin/env python3 {app_dir}/app.py --ping --action={action} --slot={hh:02d}:{mm:02d}
"""
    )
    (unit_dir / f"{name}.timer").write_text(
        f"""[Unit]
Description=Assistant schedule {hh:02d}:{mm:02d} ({action})

[Timer]
OnCalendar=*-*-* {hh:02d}:{mm:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    )
    enabled.append(name)
    print(f"Wrote {name}.timer ({hh:02d}:{mm:02d} → {action})")

if not enabled:
    sys.exit(1)

(state_dir / "schedule-units.txt").write_text("\n".join(enabled) + "\n")
PY

systemctl --user daemon-reload

# Disable any leftover assistant-ping timers first
mapfile -t OLD < <(systemctl --user list-unit-files 'assistant-ping-*.timer' --no-legend 2>/dev/null | awk '{print $1}' || true)
for u in "${OLD[@]:-}"; do
  [[ -z "${u:-}" ]] && continue
  systemctl --user disable --now "$u" 2>/dev/null || true
done

while read -r name; do
  [[ -z "$name" ]] && continue
  systemctl --user enable --now "${name}.timer"
  echo "Enabled ${name}.timer"
done < "$STATE_DIR/schedule-units.txt"

echo
echo "Schedule installed from config.json"
systemctl --user list-timers 'assistant-ping-*' --no-pager 2>/dev/null || true
echo
echo "Edit times in: $DIR/config.json"
echo "Then re-run:     $DIR/setup-schedule.sh"
echo "Test notify:     $DIR/quick-todo --ping --action=notify"
echo "Test open:       $DIR/quick-todo --ping --action=open"
echo "Remove timers:   $DIR/setup-schedule.sh --remove"
