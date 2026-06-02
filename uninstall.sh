#!/usr/bin/env bash
# Remove TokenPulse launch agents and stop the widget.
set -euo pipefail
LA="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
for label in com.tokenpulse.widget com.tokenpulse.nudge; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$LA/$label.plist"
  echo "removed $label"
done
pkill -f "widget.py" 2>/dev/null || true
echo "✓ Uninstalled."
