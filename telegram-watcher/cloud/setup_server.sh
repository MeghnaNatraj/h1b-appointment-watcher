#!/bin/bash
# Runs as root on the Oracle VM (Oracle Linux or Ubuntu). Expects the watcher files already
# copied into /opt/h1b-watcher by deploy.sh. Safe to re-run.
set -euo pipefail

APP=/opt/h1b-watcher
UV_VERSION=0.8.0

if ! id watcher >/dev/null 2>&1; then
  useradd --system --home "$APP" --shell /usr/sbin/nologin watcher
fi

# The free AMD shape has 1 GB of RAM, and the image's ~1 GB swap file is not
# enough for dnf (it was OOM-killed installing python3.12). Add 2 GB more once.
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  [ -f /swapfile ] || { fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile; }
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap defaults 0 0' >> /etc/fstab
fi

if [ ! -x "$APP/venv/bin/python" ]; then
  # The pinned requirements need Python >= 3.10. Oracle Linux 9's python3 is
  # 3.9, and dnf runs out of memory on the 1 GB shape loading repo metadata, so
  # use uv's standalone Python 3.12 instead. Ubuntu just needs python3-venv.
  if command -v dnf >/dev/null; then
    if ! command -v /usr/local/bin/uv >/dev/null; then
      curl -fsSL "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$(uname -m)-unknown-linux-gnu.tar.gz" \
        | tar -xz -C /usr/local/bin --strip-components=1
    fi
    UV_PYTHON_INSTALL_DIR=/opt/uv-python /usr/local/bin/uv venv --python 3.12 "$APP/venv"
  else
    apt-get update && apt-get install -y python3-venv
    python3 -m venv "$APP/venv"
  fi
fi
if [ -x /usr/local/bin/uv ]; then
  /usr/local/bin/uv pip install -q --python "$APP/venv/bin/python" -r "$APP/requirements.txt"
else
  "$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"
fi

# deploy.sh stages files in /tmp and cp -a keeps their user_tmp_t SELinux
# label, which systemd refuses to exec (status=203/EXEC). Reset the labels.
if command -v restorecon >/dev/null; then
  restorecon -R "$APP"
fi
chown -R watcher:watcher "$APP"
chmod 700 "$APP"
chmod 600 "$APP/.env" "$APP/session.session"

cat > /etc/systemd/system/h1b-watcher.service <<UNIT
[Unit]
Description=H1B slot watcher
Wants=network-online.target
After=network-online.target

[Service]
User=watcher
WorkingDirectory=$APP
ExecStart=$APP/venv/bin/python -u $APP/h1b_slot_watcher.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable h1b-watcher
systemctl restart h1b-watcher
sleep 10
systemctl --no-pager status h1b-watcher | head -5
journalctl -u h1b-watcher --no-pager -n 5
