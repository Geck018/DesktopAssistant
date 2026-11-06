#!/usr/bin/env bash
# Enable login morning brief (copies autostart into ~/.config/autostart).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$DEST_DIR"
cp "$DIR/autostart.desktop" "$DEST_DIR/morning-assistant.desktop"
echo "Autostart enabled: $DEST_DIR/morning-assistant.desktop"
echo "Next login will run: app.py --morning"
echo "Disable: rm \"$DEST_DIR/morning-assistant.desktop\""
