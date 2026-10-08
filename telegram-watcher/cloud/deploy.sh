#!/bin/bash
# Copy the watcher to the Oracle Always Free VM and (re)start it there.
# Usage: cloud/deploy.sh <server-ip> [ssh-key] [ssh-user]
# First run moves the Telegram session to the server; later runs only update
# the script, requirements and .env.
set -euo pipefail

IP=${1:?usage: deploy.sh <server-ip> [ssh-key]}
KEY=${2:-$HOME/.ssh/oracle_h1b}
USER_AT=${3:-opc}@$IP
HERE=$(cd "$(dirname "$0")/.." && pwd)
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER_AT")
APP=/opt/h1b-watcher

FILES=("$HERE/h1b_slot_watcher.py" "$HERE/requirements.txt" "$HERE/cloud/setup_server.sh")
if ! "${SSH[@]}" "sudo test -f $APP/session.session"; then
  FILES+=("$HERE/session.session")
fi

# The server's .env is the local one. "It stopped" alerts come from the
# HEALTHCHECK_URL monitor, so no periodic "still running" message is sent.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
grep -v '^HEARTBEAT_DAYS=' "$HERE/.env" > "$TMP/.env"
echo "HEARTBEAT_DAYS=0" >> "$TMP/.env"
# Used in problem-report emails so the fix commands are copy-pasteable.
grep -v -e '^SERVER_SSH=' -e '^SERVER_IP=' "$TMP/.env" > "$TMP/.env.new" && mv "$TMP/.env.new" "$TMP/.env"
echo "SERVER_IP=$IP" >> "$TMP/.env"
echo "SERVER_SSH=ssh -i ~/.ssh/oracle_h1b $USER_AT" >> "$TMP/.env"
chmod 600 "$TMP/.env"

"${SSH[@]}" "rm -rf /tmp/h1b && mkdir -m 700 /tmp/h1b"
# Only one copy may use the Telegram session at a time, so stop the Mac's job
# before copying the session file (it is written while the watcher runs).
launchctl bootout "gui/$(id -u)/com.meghna.h1bslotwatcher" 2>/dev/null || true
launchctl disable "gui/$(id -u)/com.meghna.h1bslotwatcher"
scp -i "$KEY" "${FILES[@]}" "$TMP/.env" "$USER_AT:/tmp/h1b/"

"${SSH[@]}" "sudo mkdir -p $APP && sudo cp -a /tmp/h1b/. $APP/ && rm -rf /tmp/h1b && sudo bash $APP/setup_server.sh"
