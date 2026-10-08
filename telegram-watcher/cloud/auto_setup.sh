#!/bin/bash
# One-shot launchd job: wait for Oracle capacity, deploy the watcher to the new
# VM, then unload itself. Safe to restart at any point (launch_retry.sh reuses
# an existing h1b-watcher instance and deploy.sh is idempotent).
set -uo pipefail
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
D=$(cd "$(dirname "$0")" && pwd)
LABEL=com.meghna.h1b-oracle-setup

IP=$("$D/launch_retry.sh" | tail -1)
echo "$(date '+%F %T') public IP: $IP"
case "$IP" in ''|null) echo "no public IP, will retry on next run"; exit 1;; esac

until ssh -i "$HOME/.ssh/oracle_h1b" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "opc@$IP" true 2>/dev/null; do
  sleep 15
done

if "$D/deploy.sh" "$IP"; then
  echo "$IP" > "$D/server_ip.txt"
  echo "$(date '+%F %T') deployed to $IP"
  osascript -e "display notification \"H1B watcher now runs on Oracle ($IP)\" with title \"H1B watcher moved to cloud\"" || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
  launchctl bootout "gui/$(id -u)/$LABEL"
else
  echo "$(date '+%F %T') deploy failed, re-enabling the Mac watcher"
  launchctl enable "gui/$(id -u)/com.meghna.h1bslotwatcher"
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.meghna.h1bslotwatcher.plist" 2>/dev/null || true
  exit 1
fi
