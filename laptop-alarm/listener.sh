#!/bin/bash
# Listens on a private ntfy topic and alerts this Mac once per slot: the volume
# goes up, it says "Visa slot available" one time and shows a pop-up. Messages
# in the next 5 minutes (such as the "Slot details" follow-up) stay silent.

DIR="$(cd "$(dirname "$0")" && pwd)"
TOPIC="$(cat "$DIR/topic.txt")"
QUIET_SECONDS=300
STAMP="$DIR/.last-alert"

alert() {
  local msg="$1"
  [ -z "$msg" ] && msg="Visa slot available"

  local old_vol
  old_vol="$(osascript -e 'output volume of (get volume settings)')"
  osascript -e 'set volume output volume 100 without output muted'
  afplay /System/Library/Sounds/Sosumi.aiff
  say "Visa slot available"
  osascript -e "set volume output volume $old_vol"

  # The pop-up stays until dismissed but does not hold up the listener.
  osascript -e "display dialog \"$(printf '%s' "$msg" | tr -d '\"\\' | cut -c1-500)\" with title \"VISA SLOT ALERT\" buttons {\"Open Telegram\", \"Dismiss\"} default button \"Open Telegram\" with icon caution" \
    -e 'if button returned of result is "Open Telegram" then tell application "Telegram" to activate' >/dev/null 2>&1 &
}

# /raw streams one line per message (blank lines are keepalives).
# Reconnects automatically if the connection drops.
while true; do
  curl -sN --max-time 0 "https://ntfy.sh/$TOPIC/raw" | while IFS= read -r line; do
    [ -z "$line" ] && continue
    now=$(date +%s)
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    if (( now - last >= QUIET_SECONDS )); then
      echo "$now" > "$STAMP"
      alert "$line"
    fi
  done
  sleep 5
done
