# H1B Appointment Watcher

Watches a Telegram group where people report open US visa (H1B/H4) interview slots, and rings the Visa Alarm app on your Android phone the moment a real slot is posted.

## Features

- Watches the group 24 hours a day on a free cloud server, so your laptop can be off
- Ignores noise: the group's repeating notice, admin posts and "NA" (no slots) messages
- Rings a full-screen alarm on your Android phone, even on silent or vibrate
- Reads the posted screenshot and sends a one-line summary, like "Hyderabad, H1B regular, 3 dates: Nov 4, 5, 12 2026"
- Catches up on messages it missed after a restart, so alerts arrive late rather than never
- Rings the alarm if something breaks, with the steps to fix it
- A separate free service rings the alarm if the watcher stops completely
- Passwords and the Telegram login are never stored in this repo

## How it works

The public Telegram group **Regular_H1B_H4_VisaSlotsChecking** is where people post screenshots when they see open slots. The watcher is logged in to Telegram as you and reads the group. It only reads; it never posts there.

For every new message it:

1. **Skips** the group's repeating "H1 H4 inperson slots availa..." notice and posts by group admins.
2. **Skips** text that says "NA" or "N/A" as a word, meaning no slots. City names that contain those letters, like CHENNAI, are not skipped.
3. **Rings the phone** for any photo or other text: the message text, or "New slot photo posted" for a bare screenshot, goes to a private channel on [ntfy.sh](https://ntfy.sh), a free push service, and the Visa Alarm app goes off at once.
4. **Reads** the screenshot, if there is one, and sends what it found as a second message titled "Slot details" (see "Reading screenshots" below).

The channel name (`NTFY_TOPIC`) is long and random, so it works as a password; keep it private.

Besides alerts, the app can show two other kinds of notice:

- **"H1B watcher stopped: ..."** from the watcher itself, when something breaks (Telegram login expired, a crash). It says what happened and how to fix it, at most once every 6 hours per problem.
- **"Watcher stopped"** from healthchecks.io, when the watcher stops sending its "still alive" signal (every 5 minutes while connected to Telegram), and a quiet "Watcher back" when it recovers. To set that up, in healthchecks.io open Integrations, add a Webhook, and assign it to your check. For "down" events use method POST, URL `https://ntfy.sh/<NTFY_TOPIC>`, body `Visa slot watcher stopped. No slot alerts until it is fixed.`, and headers `Title: Watcher stopped`, `Priority: urgent`, `Tags: warning`. For "up" events use POST, the same URL, body `Visa slot watcher is running again.`, and headers `Title: Watcher back`, `Priority: low`.

## Where it runs

On a **free Oracle Cloud server** (Always Free plan, San Jose region). The account was never upgraded, so it cannot be charged. The server address is in `telegram-watcher/cloud/server_ip.txt`, and the watcher runs there as a service called `h1b-watcher` that restarts by itself if it crashes.

Oracle sometimes stops free servers it thinks are idle. If the alarm says "Watcher stopped" and it does not come back, log in to the Oracle Cloud console and start the instance again.

## What you need

- **The private files** in `~/.config/h1b-watcher/` on your Mac: `.env` (settings and passwords) and `session.session` (the saved Telegram login). Treat `session.session` like a password: anyone holding it can use your Telegram.
- **`~/.ssh/oracle_h1b`**, the key that lets you log in to the server.
- **`~/.oci/`**, the Oracle account key, only needed to create a new server.
- Python 3 on your Mac, and the GitHub app `gh` to download the repo.

The private files also live on the server in `/opt/h1b-watcher/`. If every copy is ever lost: get a new API ID and hash at my.telegram.org, and log in to Telegram again (it sends a code on first run).

## Get it working on a computer

1. Download it:
   ```
   gh repo clone MeghnaNatraj/h1b-appointment-watcher
   cd h1b-appointment-watcher
   ```
2. Run the one-time setup. It copies the private files in from `~/.config/h1b-watcher/`, installs what it needs and runs the tests:
   ```
   ./setup.sh
   ```
3. To send a change (edited code or settings) to the server:
   ```
   telegram-watcher/cloud/deploy.sh $(cat telegram-watcher/cloud/server_ip.txt)
   ```
   This copies your local `.env` over the server's, so edit settings in `~/.config/h1b-watcher/.env` and run `./setup.sh` first.

## Settings

All settings live in `.env` (template: `telegram-watcher/.env.example`).

| Setting | What it is | Where to find it |
|---|---|---|
| `API_ID`, `API_HASH` | Lets the watcher log in to Telegram | my.telegram.org, then "API development tools" |
| `SOURCE_GROUP` | The group to watch | Already set to `Regular_H1B_H4_VisaSlotsChecking` |
| `NTFY_TOPIC` | Private channel for the phone app | Make one up: `echo visa-alert-$(openssl rand -hex 8)` |
| `HEALTHCHECK_URL` | The "still alive" link | healthchecks.io, your check's ping URL |
| `OCR_ENABLED` | Read screenshots for a "Slot details" line | `true` (default) or `false` |

## Reading screenshots

Most alerts in the group are screenshots with no caption. The watcher reads each screenshot with [tesseract](https://github.com/tesseract-ocr/tesseract), a free text-recognition program that runs on the server itself (no paid service, no account), and picks out the location (Hyderabad, Chennai, Mumbai, New Delhi, Kolkata and common US consulates abroad), the visa type (H1B or H4, regular or dropbox) and the dates. It builds one line from what it found, for example `Hyderabad, H1B regular, 3 dates: Nov 4, 5, 12 2026`. It only reports what is written in the image and never guesses a date.

The first alarm never waits for this. The "Slot details" message follows a moment later, and the app rings for it too, so you may need to dismiss twice. If tesseract is not installed, cannot read the image, takes longer than 15 seconds, or finds no location or date, only the first alarm goes out. Set `OCR_ENABLED=false` to turn it off.

Install tesseract once on each computer that runs the watcher:

- **Mac**: `brew install tesseract`
- **Oracle Linux 9 server**: `sudo dnf install -y oracle-epel-release-el9 && sudo dnf install -y tesseract tesseract-langpack-eng`. dnf needs the extra swap that `setup_server.sh` adds on the 1 GB server, so run it after the first deploy, then restart the watcher.
- **Ubuntu**: `sudo apt-get install -y tesseract-ocr`

## Android phone app (Visa Alarm)

A one-button app in `android-app/`. Tap **START** once; it asks for each permission it needs (notifications, full-screen alerts, unrestricted battery), then listens in the background and restarts by itself after a reboot. **Test alarm** shows what an alert looks like.

Build it on a Mac (free tools, about 2 GB):

```
brew install openjdk@17 gradle
brew install --cask android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@17 ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
yes | sdkmanager --licenses
sdkmanager "platforms;android-34" "build-tools;34.0.0" "platform-tools"
cd android-app
./gradlew assembleRelease -PntfyTopic=<your NTFY_TOPIC>
```

The app is `android-app/app/build/outputs/apk/release/app-release.apk`. The channel name is built into the app, so build your own copy rather than sharing one.

Install it, either way:

- **By cable:** on the phone, turn on Developer options (Settings, About phone, Software information, tap Build number 7 times), then Developer options, USB debugging. On Samsung, turn off Settings, Security and privacy, Auto Blocker first. Plug in, tap Allow on the phone, then run `$ANDROID_HOME/platform-tools/adb install -r app-release.apk`.
- **Without a cable:** email the APK to yourself, open it on the phone and allow installing from Gmail.

Then open Visa Alarm and tap **START**.

## Everyday commands

Run from the repo folder. First set the server address:

```
IP=$(cat telegram-watcher/cloud/server_ip.txt)
```

| I want to... | Command |
|---|---|
| See if it is running | `ssh -i ~/.ssh/oracle_h1b opc@$IP systemctl is-active h1b-watcher` |
| See the last 50 log lines | `ssh -i ~/.ssh/oracle_h1b opc@$IP sudo journalctl -u h1b-watcher -n 50` |
| Restart it | `ssh -i ~/.ssh/oracle_h1b opc@$IP sudo systemctl restart h1b-watcher` |
| Ring the phone with a TEST alert (the Telegram login is never used) | `ssh -i ~/.ssh/oracle_h1b opc@$IP 'sudo -u watcher /opt/h1b-watcher/venv/bin/python /opt/h1b-watcher/h1b_slot_watcher.py --test-alert'` |

The service runs as user `watcher` from /opt/h1b-watcher, with .env next to the script, so the test command must run as that user. Add a message after `--test-alert` to change the text.

"Watching group" in the log means it connected. "Alert sent" means a slot alert went out.

## Safety

- **Read-only in the group.** It never posts, reacts or messages anyone in the group.
- **No secrets in the repo.** `.env` and `session.session` are excluded by `.gitignore`.
- **One copy at a time.** Two copies using the same Telegram login can get the login cancelled. Do not run the watcher on your Mac while the server copy is running, except briefly to log in again.
- **Cannot cost money.** The Oracle account is on the free plan and was never upgraded.

## Moving to a new server

If Oracle deletes the server, `telegram-watcher/cloud/auto_setup.sh` requests a new free one, retrying every 3 minutes because free servers are often "out of capacity". It then installs everything and saves the new address in `cloud/server_ip.txt`. It uses the `h1b` profile in `~/.oci/config`.

## What is in the folders

```
h1b-appointment-watcher/
  README.md               this file
  setup.sh                one-time setup after downloading
  docs/system-design.html end-to-end design of the whole system
  telegram-watcher/       the watcher (Python)
    h1b_slot_watcher.py   the program
    slot_image.py         reads screenshots (tesseract) and builds the summary line
    test_*.py             tests for the alert rules, screenshot reading and problem reports
    requirements.txt      Python packages it needs
    .env.example          blank template of the settings file
    cloud/                scripts that create the Oracle server and copy the watcher to it
  android-app/            Visa Alarm, the one-button Android alarm app (Java)
```

## Disclaimer

For personal use. The watcher only reads a public group, but it uses your Telegram account to do so; use it within Telegram's terms.

## Related

[us-visa-bot](https://github.com/jeangnc/us-visa-bot) (ais-bot) is a different approach: it logs in to your own account on ais.usvisa-info.com and can rebook an earlier date automatically. It was considered and not used here, because frequent checks can lock your visa account and auto-rebooking cancels your current appointment.
