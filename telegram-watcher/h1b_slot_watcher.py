"""Watch a Telegram group for H1B/H4 visa slot alerts and ring the Visa Alarm app.

Secrets and settings live in .env next to this file (see .env.example).
"""
import argparse
import asyncio
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path

import requests

import slot_image

HERE = Path(__file__).resolve().parent
log = logging.getLogger("h1b_watcher")

JUNK_MARKER = "THIS IS H1 H4 INPERSON SLOTS AVAILA"
# "NA", "N A", "N/A", "N.A." or "N - A", in any case, means "no slots". The
# group also writes "NA1", "Na2 all" (NA for slot type 1, 2, ...), so a digit
# may follow. A plain substring check would also match CHENNAI, AHMEDABAD, etc.,
# so no letter may sit on either side.
NA_PATTERN = re.compile(r"(?<![A-Za-z])N[ /.\-]*A(?![A-Za-z])", re.IGNORECASE)
# "Ghost" posts (a booking that vanished, or "ghosted") are not real slots.
GHOST_PATTERN = re.compile(r"ghost", re.IGNORECASE)
PROBLEM_REPEAT_HOURS = 6
WATCHER_DIR = "h1b-appointment-watcher/telegram-watcher"
REPO = "MeghnaNatraj/h1b-appointment-watcher"


def load_env(path):
    """Tiny stdlib .env parser: KEY=VALUE lines, # comments, optional quotes.

    Values already set in the real environment win over the file.
    """
    path = Path(path)
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def should_alert(text, has_image):
    """Return True if a group message looks like a real slot alert.

    Any NA wins, even on a photo. A photo with no NA always alerts.
    """
    text = (text or "").strip()
    if JUNK_MARKER in text.upper():
        return False
    if NA_PATTERN.search(text) or GHOST_PATTERN.search(text):
        return False
    return has_image or bool(text)


def send_ntfy(text, title="VISA SLOT", priority="urgent"):
    """Push a message to the ntfy topic the Visa Alarm app listens on."""
    resp = requests.post(f"https://ntfy.sh/{os.environ['NTFY_TOPIC']}", data=text.encode("utf-8"), timeout=15,
                         headers={"Title": title, "Priority": priority, "Tags": "rotating_light"})
    resp.raise_for_status()


def _server_commands():
    ssh = os.environ.get("SERVER_SSH", "ssh -i ~/.ssh/oracle_h1b opc@<server-ip>")
    ip = os.environ.get("SERVER_IP", "<server-ip>")
    return ssh, ip


def report_problem(key, what, fix, details=""):
    """Tell the user what broke and how to fix it, at most once per 6 hours per `key`.

    If ntfy cannot be reached, signal a failure to the healthchecks.io check,
    which raises its own down alert.
    """
    marker = HERE / f".problem-{key}"
    if marker.exists() and time.time() - marker.stat().st_mtime < PROBLEM_REPEAT_HOURS * 3600:
        return
    body = f"What stopped: {what}\n\nFix:\n{fix}\n"
    if details:
        body += f"\nError: {details}\n"
    subject = f"H1B watcher stopped: {what.split(' (')[0]}"
    try:
        send_ntfy(body, subject, "high")
    except Exception as e:
        log.error("Could not send problem report %s: %s", key, e)
        url = os.environ.get("HEALTHCHECK_URL")
        if url:
            try:
                requests.post(url + "/fail", data=(subject + "\n\n" + body).encode(), timeout=10)
            except Exception as e2:
                log.error("Could not signal healthcheck failure: %s", e2)
    marker.touch()
    log.warning("Problem reported (%s): %s", key, what)


def is_admin_post(event):
    """Anonymous admins and channel posts carry the chat itself as the sender.

    Looking up a named sender's admin rights needs admin rights of our own in
    this group, so it always failed and only delayed the alarm.
    """
    return bool(event.message.post) or event.sender_id is None or event.sender_id == event.chat_id


async def _push(text, title="VISA SLOT", priority="urgent"):
    try:
        await asyncio.to_thread(send_ntfy, text, title, priority)
    except Exception as e:
        log.error("ntfy push failed: %s", e)


def make_handler(client):
    async def handler(event):
        has_image = event.message.photo is not None
        text = (event.message.raw_text or "").strip()
        if not should_alert(text, has_image):
            return
        if is_admin_post(event):
            log.info("Skipped admin message: %s", text[:80])
            return

        # Ring the phone first. Reading the screenshot can take seconds, so it
        # follows as a second "Slot details" message.
        alert = text or "New slot photo posted"
        await _push(alert)
        if has_image:
            try:
                image_bytes = await event.message.download_media(file=bytes)
            except Exception:
                log.exception("Could not download alert image")
                image_bytes = None
            # Location and dates read from the screenshot, or None.
            summary = await asyncio.to_thread(slot_image.read_slot_image, image_bytes) if image_bytes else None
            if summary:
                await _push(summary, "Slot details", "high")
        log.info("Alert sent: %s", alert[:80])

    return handler


async def healthcheck_pinger(client, url, minutes=5):
    """Ping a dead-man's-switch URL (e.g. healthchecks.io) while connected.

    The monitoring service alerts when pings stop, which covers the cases the
    watcher cannot report itself: crashes, a lost Telegram connection, or the
    VM being stopped.
    """
    while True:
        if client.is_connected():
            try:
                await asyncio.to_thread(requests.get, url, timeout=10)
            except Exception as e:
                log.warning("Healthcheck ping failed: %s", e)
        await asyncio.sleep(minutes * 60)


def _report_login_needed(details):
    ssh, ip = _server_commands()
    report_problem(
        "telegram-login",
        "Telegram login (logged out).",
        f"In Terminal, if the repo is not on this computer: gh repo clone {REPO} && {REPO.split('/')[1]}/setup.sh\n"
        f"Then cd {WATCHER_DIR} and:\n"
        "1. h1b_watcher_venv/bin/python h1b_slot_watcher.py  (enter the Telegram code, Ctrl+C at 'Watching group')\n"
        f"2. {ssh} sudo rm /opt/h1b-watcher/session.session\n"
        f"3. cloud/deploy.sh {ip}\n"
        "4. cp session.session ~/.config/h1b-watcher/  (keeps the backup copy current)",
        details,
    )


def run_test_alert(message):
    """Send a TEST message to the phone app; return the exit code. Never touches the Telegram login."""
    try:
        send_ntfy("TEST: " + (message or "H1B watcher alert test, please ignore"))
    except Exception as e:
        print(f"ntfy: FAILED ({e})")
        return 1
    print("ntfy: sent")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-alert", nargs="?", const="", metavar="MESSAGE",
                        help="send a TEST message to the phone app and exit (no Telegram login)")
    args = parser.parse_args()
    load_env(HERE / ".env")
    if args.test_alert is not None:
        sys.exit(run_test_alert(args.test_alert))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    try:
        _run()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        log.exception("Watcher crashed")
        name = type(e).__name__
        if name in ("AuthKeyUnregisteredError", "SessionRevokedError", "AuthKeyDuplicatedError",
                    "UserDeactivatedError", "SessionExpiredError"):
            _report_login_needed(f"{name}: {e}")
        else:
            ssh, ip = _server_commands()
            report_problem(
                "crash",
                f"The watcher (crashed with {name}; it auto-restarts).",
                "See the logs: "
                f"{ssh} sudo journalctl -u h1b-watcher -n 100",
                traceback.format_exc()[-1500:],
            )
        raise


def _run():
    from telethon import TelegramClient, events

    client = TelegramClient(str(HERE / "session"), int(os.environ["API_ID"]), os.environ["API_HASH"], catch_up=True)
    client.add_event_handler(make_handler(client), events.NewMessage(chats=os.environ["SOURCE_GROUP"]))
    if not sys.stdin.isatty():
        # On the server nobody can type a login code, so report instead of hanging.
        client.loop.run_until_complete(client.connect())
        if not client.loop.run_until_complete(client.is_user_authorized()):
            _report_login_needed("The saved Telegram session is not logged in.")
            sys.exit(1)
    client.start()
    if os.environ.get("HEALTHCHECK_URL"):
        client.loop.create_task(healthcheck_pinger(client, os.environ["HEALTHCHECK_URL"]))
    log.info("Watching group, Telegram notifications stay as normal...")
    client.run_until_disconnected()
    # Telethon gave up reconnecting. systemd restarts the service.
    log.error("Disconnected from Telegram, exiting so systemd restarts the watcher")


if __name__ == "__main__":
    main()
