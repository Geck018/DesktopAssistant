#!/usr/bin/env bash
# One-time: install AppIndicator bindings so Quick Todo can sit in the top bar.
set -euo pipefail
pkexec apt-get install -y gir1.2-ayatanaappindicator3-0.1
echo "Done. Restart Quick Todo — you should see a checkbox icon in the top bar."
