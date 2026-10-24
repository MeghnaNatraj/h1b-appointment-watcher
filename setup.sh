#!/bin/bash
# One-time setup after downloading this repo.
# Copies the private files (.env, the Telegram login, the server address) in from the secrets
# folder, builds the Python environment and runs the tests.
# Secrets folder: ~/.config/h1b-watcher (override with H1B_SECRETS=/some/path).
set -euo pipefail

SECRETS=${H1B_SECRETS:-$HOME/.config/h1b-watcher}
cd "$(dirname "$0")/telegram-watcher"

for f in .env session.session; do
  if [ ! -f "$f" ] && [ -f "$SECRETS/$f" ]; then
    cp "$SECRETS/$f" "$f"
    chmod 600 "$f"
    echo "Copied $f from $SECRETS"
  fi
done

if [ ! -f cloud/server_ip.txt ] && [ -f "$SECRETS/server_ip.txt" ]; then
  cp "$SECRETS/server_ip.txt" cloud/server_ip.txt
  echo "Copied server_ip.txt from $SECRETS"
fi

if [ ! -f .env ]; then
  echo "No .env found. Put it in $SECRETS, or copy .env.example to .env and fill it in." >&2
  exit 1
fi
[ -f session.session ] || echo "Note: no session.session. The first run will ask for a Telegram login code."

python3 -m venv h1b_watcher_venv
h1b_watcher_venv/bin/python -m pip install -q -r requirements.txt
h1b_watcher_venv/bin/python -m unittest -q

echo
echo "Ready. To update the server:  telegram-watcher/cloud/deploy.sh \$(cat telegram-watcher/cloud/server_ip.txt)"
