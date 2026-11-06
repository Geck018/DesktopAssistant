#!/usr/bin/env bash
# Launch Assistant without keeping a terminal open.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DIR/state"
chmod u+rwX,go+rwX "$DIR/state" 2>/dev/null || true

LOG="$DIR/state/assistant.log"
# Ensure log is writable by the desktop user (agent runs can leave root-owned files)
if [[ ! -w "$LOG" ]]; then
  rm -f "$LOG" 2>/dev/null || true
  touch "$LOG" 2>/dev/null || LOG="/tmp/assistant-$USER.log"
  chmod 666 "$LOG" 2>/dev/null || true
fi
touch "$LOG" 2>/dev/null || LOG="/tmp/assistant-$USER.log"

FG=0
ARGS=()
for a in "$@"; do
  if [[ "$a" == "--fg" ]]; then
    FG=1
  else
    ARGS+=("$a")
  fi
done

export ASSISTANT_DAEMONIZED=1   # tell Python not to double-fork; we're already detaching
export ASSISTANT_LOG="$LOG"

if [[ "$FG" -eq 1 ]]; then
  exec /usr/bin/env python3 "$DIR/app.py" "${ARGS[@]}"
fi

# Detach from any terminal; failures must not prevent launch
nohup /usr/bin/env python3 "$DIR/app.py" "${ARGS[@]}" >>"$LOG" 2>&1 &
disown 2>/dev/null || true
exit 0
