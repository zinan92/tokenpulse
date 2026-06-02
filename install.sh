#!/usr/bin/env bash
# Install TokenPulse macOS launch agents:
#   - widget : always-on-top desktop coach, relaunched at login / if it crashes
#   - nudge  : Telegram push at the checkpoint times in config.json
#
# Re-run any time to pick up config/path changes. Use ./uninstall.sh to remove.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3)"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"

echo "TokenPulse dir : $DIR"
echo "python3        : $PY"

# ---- widget agent (keep-alive) --------------------------------------------
cat > "$LA/com.tokenpulse.widget.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tokenpulse.widget</string>
  <key>ProgramArguments</key>
    <array><string>$PY</string><string>$DIR/widget.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/widget.out.log</string>
  <key>StandardErrorPath</key><string>$DIR/widget.err.log</string>
</dict>
</plist>
PLIST

# ---- nudge agent (calendar schedule from config.json checkpoints) ----------
INTERVALS="$("$PY" - "$DIR/config.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
out = []
for cp in cfg.get("checkpoints", ["15:00", "20:00", "23:00"]):
    h, m = cp.split(":")
    out.append(f"    <dict><key>Hour</key><integer>{int(h)}</integer>"
               f"<key>Minute</key><integer>{int(m)}</integer></dict>")
print("\n".join(out))
PYEOF
)"

cat > "$LA/com.tokenpulse.nudge.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tokenpulse.nudge</string>
  <key>ProgramArguments</key>
    <array><string>$PY</string><string>$DIR/nudge.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><false/>
  <key>StartCalendarInterval</key>
  <array>
$INTERVALS
  </array>
  <key>StandardOutPath</key><string>$DIR/nudge.out.log</string>
  <key>StandardErrorPath</key><string>$DIR/nudge.err.log</string>
</dict>
</plist>
PLIST

UID_NUM="$(id -u)"
for label in com.tokenpulse.widget com.tokenpulse.nudge; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$LA/$label.plist"
  echo "loaded $label"
done

echo
echo "✓ Installed. Widget should appear top-right now."
echo "  Nudge checkpoints: $(${PY} -c "import json;print(', '.join(json.load(open('$DIR/config.json'))['checkpoints']))")"
echo "  Logs: $DIR/{widget,nudge}.{out,err}.log"
