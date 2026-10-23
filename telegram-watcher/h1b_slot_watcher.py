"""Watch a Telegram group for H1B/H4 visa slot alerts and forward real ones.

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
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

import slot_image

HERE = Path(__file__).resolve().parent
log = logging.getLogger("h1b_watcher")

JUNK_MARKER = "THIS IS H1 H4 INPERSON SLOTS AVAILA"
# "NA", "N/A" or "N.A.", in any case, means "no slots". The group also writes
# "NA1", "Na2 all" (NA for slot type 1, 2, ...), so a digit may follow. A plain
# substring check would also match CHENNAI, AHMEDABAD, etc., so no letter may
# sit on either side.
NA_PATTERN = re.compile(r"(?<![A-Za-z])N[/.]?A(?![A-Za-z])", re.IGNORECASE)
ADMIN_CACHE_SECONDS = 24 * 3600


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
    if NA_PATTERN.search(text):
        return False
    return has_image or bool(text)


def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(fmt)
    log.addHandler(stdout)
    log_dir = HERE / "logs"
    log_dir.mkdir(exist_ok=True)
    rotating = RotatingFileHandler(log_dir / "watcher.log", maxBytes=1_000_000, backupCount=3)
    rotating.setFormatter(fmt)
    log.addHandler(rotating)


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


PROBLEM_REPEAT_HOURS = 6
WATCHER_DIR = "h1b-appointment-watcher/telegram-watcher"
REPO = "MeghnaNatraj/h1b-appointment-watcher"


def _server_commands():
    ssh = os.environ.get("SERVER_SSH", "ssh -i ~/.ssh/oracle_h1b opc@<server-ip>")
    ip = os.environ.get("SERVER_IP", "<server-ip>")
    return ssh, ip


def notify_owner(title, body):
    """Tell the user something that is not a slot alert, by Telegram bot and the alarm channel.

    Raises if neither channel could be reached.
    """
    sent = False
    if _bot_enabled():
        try:
            send_telegram_bot(f"{title}\n\n{body}")
            sent = True
        except Exception as e:
            log.error("Bot notice failed: %s", e)
    if os.environ.get("NTFY_TOPIC"):
        try:
            send_ntfy(body, title, "high")
            sent = True
        except Exception as e:
            log.error("ntfy notice failed: %s", e)
    if not sent:
        raise RuntimeError("no Telegram bot or ntfy channel reachable")


def report_problem(key, what, fix, details=""):
    """Tell the user what broke and how to fix it, at most once per 6 hours per `key`.

    If neither the Telegram bot nor ntfy can be reached, fall back to signalling
    a failure to the healthchecks.io check, which raises its own down alert.
    """
    marker = HERE / f".problem-{key}"
    if marker.exists() and time.time() - marker.stat().st_mtime < PROBLEM_REPEAT_HOURS * 3600:
        return
    body = f"What stopped: {what}\n\nFix:\n{fix}\n"
    if details:
        body += f"\nError: {details}\n"
    subject = f"H1B watcher stopped: {what.split(' (')[0]}"
    try:
        notify_owner(subject, body)
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


def send_whatsapp(text, report=True):
    """Send `text` as a WhatsApp template message.

    WA_TEMPLATE may list several templates, comma-separated, in order of
    preference. A template that is still in Meta review (or missing) is
    rejected, so the next one is tried. This lets a new template take over
    on its own the moment Meta approves it.
    """
    url = f"https://graph.facebook.com/v21.0/{os.environ['WA_PHONE_NUMBER_ID']}/messages"
    headers = {"Authorization": f"Bearer {os.environ['WA_ACCESS_TOKEN']}"}
    names = [n.strip() for n in os.environ.get("WA_TEMPLATE", "h1b_slot_alert").split(",") if n.strip()]
    # Template parameters may not contain newlines, tabs or runs of spaces,
    # so flatten the alert to one line.
    param = " ".join(text.split())[:1000]
    for name in names:
        payload = {
            "messaging_product": "whatsapp",
            "to": os.environ["WA_RECIPIENT"],
            # Template send: works anytime, no 24h window needed, but requires
            # the template to be approved in WhatsApp Manager first.
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": os.environ.get("WA_LANGUAGE", "en")},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": param}]}],
            },
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.ok:
            return
        log.warning("WhatsApp send with template %s failed: %s %s", name, resp.status_code, resp.text)
    if not report:
        # Test mode: surface the failure instead of sending a problem report.
        raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")
    ssh, ip = _server_commands()
    report_problem(
        "whatsapp",
        "WhatsApp alerts (the alarm and Telegram bot still work).",
        "- Error 190 (token): Meta Business settings > System users > H1B Watcher Bot > Generate token, "
        "put it in .env as WA_ACCESS_TOKEN, run cloud/deploy.sh " + ip + "\n"
        "- Error 132001 (template): check WhatsApp Manager > Message templates",
        f"{resp.status_code} {resp.text[:300]}",
    )


def send_telegram_bot(text):
    """Send the alert text (never the screenshot) from a Telegram bot to the user's chat with it.

    Copies sent from the user's own account never notify them, but a bot's
    messages do, and that chat can get its own loud sound in Telegram.
    """
    base = f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}"
    resp = requests.post(f"{base}/sendMessage", timeout=15,
                         data={"chat_id": os.environ["TG_BOT_CHAT_ID"], "text": text})
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")


def send_ntfy(text, title="VISA SLOT", priority="urgent"):
    """Push the alert to the ntfy topic the phone app listens on."""
    resp = requests.post(f"https://ntfy.sh/{os.environ['NTFY_TOPIC']}", data=text.encode("utf-8"), timeout=15,
                         headers={"Title": title, "Priority": priority, "Tags": "rotating_light"})
    resp.raise_for_status()


# Settings each channel needs, and the on/off flag for the ones that have one.
CHANNEL_SETTINGS = {
    "ntfy": ["NTFY_TOPIC"],
    "bot": ["TG_BOT_TOKEN", "TG_BOT_CHAT_ID"],
    "whatsapp": ["WA_PHONE_NUMBER_ID", "WA_ACCESS_TOKEN", "WA_RECIPIENT"],
}
CHANNEL_FLAGS = {"bot": ("BOT_ENABLED", True), "whatsapp": ("WA_ENABLED", False)}


def _bot_enabled():
    return _env_bool("BOT_ENABLED", True) and all(os.environ.get(k) for k in CHANNEL_SETTINGS["bot"])


def _missing_settings(name):
    return [k for k in CHANNEL_SETTINGS[name] if not os.environ.get(k)]


def channel_skip_reason(name):
    """Why a channel will not send ("disabled ..." or "missing ..."), or None if it will."""
    if name in CHANNEL_FLAGS:
        flag, default = CHANNEL_FLAGS[name]
        if not _env_bool(flag, default):
            return f"disabled ({flag} is off)"
    missing = _missing_settings(name)
    if missing:
        return "missing " + ", ".join(missing)
    return None


def build_channels(test=False):
    """List the non-Telethon alert channels as [(name, enabled, send)], ntfy first.

    send(alert, caption, image_bytes, summary) is blocking; `caption` is the text
    that goes with an image and `summary` the details read from it, or None.
    Shared by the live handler and --test-alert.
    """
    return [
        ("ntfy", bool(os.environ.get("NTFY_TOPIC")), lambda alert, caption, img, summary=None: send_ntfy(alert)),
        ("bot", _bot_enabled(),
         lambda alert, caption, img, summary=None: send_telegram_bot(caption)),
        ("whatsapp", _env_bool("WA_ENABLED"),
         lambda alert, caption, img, summary=None: send_whatsapp(alert, report=not test)),
    ]


async def _send_copy(client, target, text):
    """Send a text copy of the alert (never the screenshot) to one Telegram chat."""
    await client.send_message(target, text)


def make_admin_check(client):
    """Return an async check for "this message was posted by a group admin"."""
    cache = {}  # sender_id -> (is_admin, checked_at)

    async def is_admin_post(event):
        # Anonymous admins and channel posts carry the chat itself as sender.
        if event.message.post or event.sender_id is None or event.sender_id == event.chat_id:
            return True
        hit = cache.get(event.sender_id)
        if hit and time.time() - hit[1] < ADMIN_CACHE_SECONDS:
            return hit[0]
        try:
            perms = await client.get_permissions(event.chat_id, event.sender_id)
            is_admin = bool(perms.is_admin or perms.is_creator)
        except Exception as e:
            log.warning("Could not check admin status of %s: %s", event.sender_id, e)
            return False
        cache[event.sender_id] = (is_admin, time.time())
        return is_admin

    return is_admin_post


def make_handler(client):
    recipient = os.environ["TELEGRAM_RECIPIENT"]
    is_admin_post = make_admin_check(client)

    async def handler(event):
        has_image = event.message.photo is not None
        text = (event.message.raw_text or "").strip()
        if not should_alert(text, has_image):
            return
        if await is_admin_post(event):
            log.info("Skipped admin message: %s", text[:80])
            return

        channels = build_channels()

        async def run_channel(name, enabled, send, alert, caption, image_bytes, summary=None):
            if not enabled:
                return
            try:
                await asyncio.to_thread(send, alert, caption, image_bytes, summary)
            except Exception as e:
                log.error("%s send failed: %s", name, e)

        # Ring the phone app first: it is the loud one.
        # Reading the screenshot can take seconds, so it never delays this.
        first = text or "New slot photo posted"
        await run_channel(*channels[0], first, first, None)

        image_bytes = None
        if has_image:
            try:
                image_bytes = await event.message.download_media(file=bytes)
            except Exception:
                log.exception("Could not download alert image")

        # Location, visa type and dates read from the screenshot, or None.
        summary = None
        if image_bytes is not None:
            summary = await asyncio.to_thread(slot_image.read_slot_image, image_bytes)
            if summary and os.environ.get("NTFY_TOPIC"):
                try:
                    await asyncio.to_thread(send_ntfy, summary, "Slot details", "high")
                except Exception as e:
                    log.error("ntfy details push failed: %s", e)
        # The full original message, never shortened, with the summary on top.
        caption = slot_image.compose_alert(text, summary)
        alert = caption or "New slot photo posted"

        targets = (("me", "Saved Messages"), (recipient, f"DM {recipient}"))
        if not _env_bool("TELEGRAM_COPIES_ENABLED", True):
            targets = ()
        for target, label in targets:
            try:
                await _send_copy(client, target, alert)
            except Exception as e:
                log.error("Could not send to %s: %s", label, e)

        for channel in channels[1:]:
            await run_channel(*channel, alert, alert, image_bytes, summary)

        log.info("Alert sent: %s", alert[:80])

    return handler


async def heartbeat(days):
    """Send a "still running" note every `days` days, by WhatsApp when enabled.

    On the Oracle VM this is the only sign it is alive: if Oracle stops the
    instance as idle, these notes stop arriving.
    """
    note = f"Not a slot alert: the H1B watcher is still running on {os.uname().nodename}."
    while True:
        try:
            if _env_bool("WA_ENABLED"):
                await asyncio.to_thread(send_whatsapp, note)
            else:
                await asyncio.to_thread(notify_owner, "H1B watcher still running", note)
            log.info("Heartbeat sent")
        except Exception as e:
            log.error("Heartbeat failed: %s", e)
        await asyncio.sleep(days * 86400)


async def announce_template_approval(waba_id, minutes=15):
    """Tell the user once the preferred WhatsApp template is approved (or rejected).

    The first name in WA_TEMPLATE may still be in Meta review when deployed.
    This polls its status and, the first time it is APPROVED, tells the user
    WhatsApp alerts are live. A marker file stops it from repeating.
    """
    name = os.environ.get("WA_TEMPLATE", "").split(",")[0].strip()
    marker = HERE / f".approved-{name}"
    if not name or marker.exists():
        return
    url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates"
    while True:
        try:
            resp = await asyncio.to_thread(
                requests.get, url, timeout=15,
                params={"name": name, "fields": "name,status",
                        "access_token": os.environ["WA_ACCESS_TOKEN"]},
            )
            status = next((t["status"] for t in resp.json().get("data", []) if t["name"] == name), None)
            if status == "APPROVED":
                note = f"Meta approved the WhatsApp template {name}. WhatsApp alerts now use it."
                await asyncio.to_thread(send_whatsapp, note)
                await asyncio.to_thread(notify_owner, "WhatsApp template approved", note)
                marker.touch()
                log.info("Template %s approved, user notified", name)
                return
            if status == "REJECTED":
                note = f"Meta rejected the WhatsApp template {name}. WhatsApp keeps using the next one in WA_TEMPLATE."
                await asyncio.to_thread(notify_owner, "WhatsApp template rejected", note)
                marker.touch()
                log.warning("Template %s rejected", name)
                return
        except Exception as e:
            log.warning("Template status check failed: %s", e)
        await asyncio.sleep(minutes * 60)


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


async def connection_watchdog(client, limit_minutes=10):
    """Report when Telegram has been disconnected for more than `limit_minutes`."""
    down_since = None
    while True:
        if client.is_connected():
            down_since = None
        else:
            down_since = down_since or time.time()
            if time.time() - down_since > limit_minutes * 60:
                ssh, ip = _server_commands()
                await asyncio.to_thread(
                    report_problem, "telegram-disconnected",
                    f"Telegram connection, down {limit_minutes}+ minutes (it keeps retrying).",
                    f"If this repeats, restart: {ssh} sudo systemctl restart h1b-watcher",
                )
        await asyncio.sleep(60)


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


def run_test_alert(message, only=None):
    """Send a TEST message through every enabled non-Telethon channel; return the exit code.

    Never touches the Telegram user-account session (a second login can log it out).
    """
    alert = "TEST: " + (message or "H1B watcher alert channel test, please ignore")
    failed = False
    for name, enabled, send in build_channels(test=True):
        if only and name not in only:
            continue
        reason = channel_skip_reason(name)
        if reason or not enabled:
            print(f"{name}: skipped ({reason or 'not enabled'})")
            continue
        try:
            send(alert, alert, None)
        except Exception as e:
            failed = True
            print(f"{name}: FAILED ({e})")
            continue
        print(f"{name}: sent")
    print("telegram user-account copies: not tested (the Telethon session is never used here)")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-alert", nargs="?", const="", metavar="MESSAGE",
                        help="send a TEST message through every enabled channel and exit (no Telegram login)")
    parser.add_argument("--channels", help="with --test-alert, only these (comma-separated: ntfy,bot,whatsapp)")
    args = parser.parse_args()
    load_env(HERE / ".env")
    if args.test_alert is not None:
        only = {c.strip() for c in args.channels.split(",") if c.strip()} if args.channels else None
        unknown = (only or set()) - set(CHANNEL_SETTINGS)
        if unknown:
            parser.error("unknown channel(s): " + ", ".join(sorted(unknown)))
        sys.exit(run_test_alert(args.test_alert, only))
    setup_logging()
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
                "Paste this message into Claude Code. Logs: "
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
    heartbeat_days = float(os.environ.get("HEARTBEAT_DAYS", "0"))
    if heartbeat_days > 0:
        client.loop.create_task(heartbeat(heartbeat_days))
    if _env_bool("WA_ENABLED") and os.environ.get("WA_BUSINESS_ACCOUNT_ID"):
        client.loop.create_task(announce_template_approval(os.environ["WA_BUSINESS_ACCOUNT_ID"]))
    if os.environ.get("HEALTHCHECK_URL"):
        client.loop.create_task(healthcheck_pinger(client, os.environ["HEALTHCHECK_URL"]))
    client.loop.create_task(connection_watchdog(client))
    log.info("Watching group, Telegram notifications stay as normal...")
    client.run_until_disconnected()
    # Telethon gave up reconnecting. systemd restarts the service.
    log.error("Disconnected from Telegram, exiting so systemd restarts the watcher")


if __name__ == "__main__":
    main()
