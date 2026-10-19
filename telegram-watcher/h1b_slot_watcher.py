"""Watch a Telegram group for H1B/H4 visa slot alerts and forward real ones.

Secrets and settings live in .env next to this file (see .env.example).
"""
import asyncio
import io
import logging
import os
import re
import smtplib
import sys
import time
import traceback
from email.mime.text import MIMEText
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


def send_email(subject, body, recipients=None):
    sender = os.environ["GMAIL_ADDRESS"]
    if recipients is None:
        recipients = [r.strip() for r in os.environ["EMAIL_RECIPIENTS"].split(",") if r.strip()]
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    # Gmail sometimes drops the connection ("Connection unexpectedly closed"),
    # so retry a couple of times before giving up.
    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
                s.login(sender, os.environ["GMAIL_APP_PASSWORD"])
                s.send_message(msg, to_addrs=recipients)
            return
        except (smtplib.SMTPServerDisconnected, OSError):
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


PROBLEM_REPEAT_HOURS = 6
WATCHER_DIR = "h1b-appointment-watcher/telegram-watcher"
REPO = "MeghnaNatraj/h1b-appointment-watcher"


def _server_commands():
    ssh = os.environ.get("SERVER_SSH", "ssh -i ~/.ssh/oracle_h1b opc@<server-ip>")
    ip = os.environ.get("SERVER_IP", "<server-ip>")
    return ssh, ip


def report_problem(key, what, fix, details=""):
    """Email the user what broke and how to fix it, at most once per 6 hours per `key`.

    If Gmail itself is the problem, fall back to signalling a failure to the
    healthchecks.io check, which emails from its own servers with this text.
    """
    marker = HERE / f".problem-{key}"
    if marker.exists() and time.time() - marker.stat().st_mtime < PROBLEM_REPEAT_HOURS * 3600:
        return
    body = f"What stopped: {what}\n\nFix:\n{fix}\n"
    if details:
        body += f"\nError: {details}\n"
    subject = f"H1B watcher stopped: {what.split(' (')[0]}"
    try:
        send_email(subject, body, [os.environ["GMAIL_ADDRESS"]])
    except Exception as e:
        log.error("Could not email problem report %s: %s", key, e)
        url = os.environ.get("HEALTHCHECK_URL")
        if url:
            try:
                requests.post(url + "/fail", data=(subject + "\n\n" + body).encode(), timeout=10)
            except Exception as e2:
                log.error("Could not signal healthcheck failure: %s", e2)
    marker.touch()
    log.warning("Problem reported (%s): %s", key, what)


def send_whatsapp(text):
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
    ssh, ip = _server_commands()
    report_problem(
        "whatsapp",
        "WhatsApp alerts (email still works).",
        "- Error 190 (token): Meta Business settings > System users > H1B Watcher Bot > Generate token, "
        "put it in .env as WA_ACCESS_TOKEN, run cloud/deploy.sh " + ip + "\n"
        "- Error 132001 (template): check WhatsApp Manager > Message templates",
        f"{resp.status_code} {resp.text[:300]}",
    )


def send_telegram_bot(text, image_bytes):
    """Send the alert from a Telegram bot to the user's chat with it.

    Copies sent from the user's own account never notify them, but a bot's
    messages do, and that chat can get its own loud sound in Telegram.
    """
    base = f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}"
    chat = os.environ["TG_BOT_CHAT_ID"]
    if image_bytes is not None:
        # Captions stop at 1024 characters, so a longer message follows the
        # photo as its own message instead of being cut.
        long_text = len(text) > 1024
        resp = requests.post(f"{base}/sendPhoto", timeout=30,
                             data={"chat_id": chat, "caption": "" if long_text else text},
                             files={"photo": ("alert.jpg", image_bytes)})
        if resp.ok and long_text:
            resp = requests.post(f"{base}/sendMessage", timeout=15, data={"chat_id": chat, "text": text})
    else:
        resp = requests.post(f"{base}/sendMessage", timeout=15, data={"chat_id": chat, "text": text})
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")


def send_ntfy(text, title="VISA SLOT", priority="urgent"):
    """Push the alert to the ntfy topic the phone app and laptop alarm listen on."""
    resp = requests.post(f"https://ntfy.sh/{os.environ['NTFY_TOPIC']}", data=text.encode("utf-8"), timeout=15,
                         headers={"Title": title, "Priority": priority, "Tags": "rotating_light"})
    resp.raise_for_status()


async def _send_copy(client, target, text, image_bytes):
    """Send a copy (not a forward) of the alert to one Telegram chat.

    The source group has forwarding protection, so neither forward_messages nor
    re-sending the original photo object works. Uploading the downloaded bytes
    as a new file does.
    """
    if image_bytes is not None:
        f = io.BytesIO(image_bytes)
        f.name = "alert.jpg"
        await client.send_file(target, f, caption=text or None)
    else:
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

        # Ring the phone app and laptop alarm first: they are the loud ones.
        # Reading the screenshot can take seconds, so it never delays this.
        if os.environ.get("NTFY_TOPIC"):
            try:
                await asyncio.to_thread(send_ntfy, text or "New slot photo posted")
            except Exception as e:
                log.error("ntfy push failed: %s", e)

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
                # If the image download failed, fall back to the alert text so
                # an uncaptioned image still produces a message.
                await _send_copy(client, target, caption if image_bytes is not None else alert, image_bytes)
            except Exception as e:
                log.error("Could not send to %s: %s", label, e)

        if os.environ.get("TG_BOT_TOKEN") and os.environ.get("TG_BOT_CHAT_ID"):
            try:
                await asyncio.to_thread(send_telegram_bot, caption if image_bytes is not None else alert, image_bytes)
            except Exception as e:
                log.error("Telegram bot send failed: %s", e)

        if _env_bool("EMAIL_ENABLED", True):
            try:
                subject = f"H1B slot alert: {summary}" if summary else "H1B slot alert"
                await asyncio.to_thread(send_email, subject, alert)
            except Exception as e:
                log.error("Email send failed: %s", e)
                ssh, ip = _server_commands()
                await asyncio.to_thread(
                    report_problem, "email",
                    "Email alerts (Gmail refused to send).",
                    "New app password at myaccount.google.com/apppasswords, put it in .env as "
                    "GMAIL_APP_PASSWORD, run cloud/deploy.sh " + ip,
                    f"Gmail error: {e}",
                )

        if _env_bool("WA_ENABLED"):
            try:
                await asyncio.to_thread(send_whatsapp, alert)
            except Exception as e:
                log.error("WhatsApp send failed: %s", e)

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
            elif _env_bool("EMAIL_ENABLED", True):
                await asyncio.to_thread(send_email, "H1B watcher still running", note,
                                        [os.environ["GMAIL_ADDRESS"]])
            log.info("Heartbeat sent")
        except Exception as e:
            log.error("Heartbeat failed: %s", e)
        await asyncio.sleep(days * 86400)


async def announce_template_approval(waba_id, minutes=15):
    """Send one WhatsApp + email once the preferred WhatsApp template is approved.

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
                note = "Meta approved the WhatsApp template. H1B slot alerts will now arrive on WhatsApp and email."
                await asyncio.to_thread(send_whatsapp, note)
                if _env_bool("EMAIL_ENABLED", True):
                    await asyncio.to_thread(send_email, "H1B watcher: WhatsApp alerts are live", note,
                                            [os.environ["GMAIL_ADDRESS"]])
                marker.touch()
                log.info("Template %s approved, user notified", name)
                return
            if status == "REJECTED":
                note = f"Meta rejected the WhatsApp template {name}. Alerts still go by email."
                if _env_bool("EMAIL_ENABLED", True):
                    await asyncio.to_thread(send_email, "H1B watcher: WhatsApp template rejected", note,
                                            [os.environ["GMAIL_ADDRESS"]])
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


def main():
    load_env(HERE / ".env")
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
                "Paste this email into Claude Code. Logs: "
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
