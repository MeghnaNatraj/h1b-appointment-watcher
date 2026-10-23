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

FILES=("$HERE/h1b_slot_watcher.py" "$HERE/slot_image.py" "$HERE/requirements.txt" "$HERE/cloud/setup_server.sh")
if ! "${SSH[@]}" "sudo test -f $APP/session.session"; then
  FILES+=("$HERE/session.session")
fi

# The server's .env is the local one, plus the server address so the fix
# commands in problem reports are copy-pasteable.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
grep -v -e '^SERVER_SSH=' -e '^SERVER_IP=' "$HERE/.env" > "$TMP/.env"
echo "SERVER_IP=$IP" >> "$TMP/.env"
echo "SERVER_SSH=ssh -i ~/.ssh/oracle_h1b $USER_AT" >> "$TMP/.env"
chmod 600 "$TMP/.env"

"${SSH[@]}" "rm -rf /tmp/h1b && mkdir -m 700 /tmp/h1b"
scp -i "$KEY" "${FILES[@]}" "$TMP/.env" "$USER_AT:/tmp/h1b/"

"${SSH[@]}" "sudo mkdir -p $APP && sudo cp -a /tmp/h1b/. $APP/ && rm -rf /tmp/h1b && sudo bash $APP/setup_server.sh"
