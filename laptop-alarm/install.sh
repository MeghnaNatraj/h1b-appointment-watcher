#!/bin/bash
# Install the Mac alarm: a background job that starts at login, listens on the
# ntfy topic and sounds a loud alarm for every slot alert.
# Usage: laptop-alarm/install.sh <ntfy-topic>     (the same NTFY_TOPIC as the watcher's .env)
#        laptop-alarm/install.sh --uninstall
set -euo pipefail

LABEL=com.h1bwatcher.visa-alert
APP="$HOME/Library/Application Support/visa-alert"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HERE=$(cd "$(dirname "$0")" && pwd)

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$APP" "$PLIST"
  echo "Removed."
  exit 0
fi

TOPIC=${1:?usage: install.sh <ntfy-topic>}
# Background jobs cannot read the Desktop or Documents folders, so run from Library.
mkdir -p "$APP"
cp "$HERE/listener.sh" "$APP/listener.sh"
chmod +x "$APP/listener.sh"
echo "$TOPIC" > "$APP/topic.txt"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$APP/listener.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>$APP/listener.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Test it with: curl -d 'Test slot alert' https://ntfy.sh/$TOPIC"
