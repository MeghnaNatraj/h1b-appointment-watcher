#!/bin/bash
# Listens on a private ntfy topic and sounds a loud alarm on this Mac
# for every message, until the pop-up is dismissed.

DIR="$(cd "$(dirname "$0")" && pwd)"
TOPIC="$(cat "$DIR/topic.txt")"
SOUND="/System/Library/Sounds/Sosumi.aiff"

alarm() {
  local msg="$1"
  [ -z "$msg" ] && msg="Visa slot available"

  local old_vol
  old_vol="$(osascript -e 'output volume of (get volume settings)')"
  osascript -e 'set volume output volume 100 without output muted'

  # Loop sound and voice in the background until the dialog is closed
  (
    while true; do
      afplay "$SOUND"; afplay "$SOUND"
      say "Visa slot available. Check now."
    done
  ) &
  local loop_pid=$!

  osascript -e "display dialog \"$(printf '%s' "$msg" | tr -d '\"\\' | cut -c1-500)\" with title \"VISA SLOT ALERT\" buttons {\"Open Telegram\", \"Dismiss\"} default button \"Open Telegram\" with icon caution" \
    -e 'if button returned of result is "Open Telegram" then tell application "Telegram" to activate' >/dev/null 2>&1

  pkill -P "$loop_pid" 2>/dev/null
  kill "$loop_pid" 2>/dev/null
  killall afplay say 2>/dev/null
  osascript -e "set volume output volume $old_vol"
}

# /raw streams one line per message (blank lines are keepalives).
# Reconnects automatically if the connection drops.
while true; do
  curl -sN --max-time 0 "https://ntfy.sh/$TOPIC/raw" | while IFS= read -r line; do
    [ -n "$line" ] && alarm "$line"
  done
  sleep 5
done
