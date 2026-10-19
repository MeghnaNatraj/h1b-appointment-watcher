# H1B Appointment Watcher

Watches a Telegram group where people report open US visa (H1B/H4) interview slots, and tells you the moment a real slot is posted.

## Features

- Watches the group 24 hours a day on a free cloud server, so your laptop can be off
- Ignores noise: the group's repeating notice and "NA" (no slots) messages
- Rings a full-screen alarm on your Android phone, even on silent or vibrate
- Sounds a loud alarm with a pop-up on your Mac
- Sends each real alert from a Telegram bot (just the message), by WhatsApp and by email
- Catches up on messages it missed after a restart, so alerts arrive late rather than never
- Emails you if something breaks, with the steps to fix it
- A separate free service emails you if the watcher stops completely
- Passwords and the Telegram login are never stored in this repo

## How it works

The public Telegram group **Regular_H1B_H4_VisaSlotsChecking** is where people post screenshots when they see open slots. The watcher is logged in to Telegram as you and reads the group. It only reads; it never posts there.

For every new message it:

1. **Skips** the group's repeating "H1 H4 inperson slots availa..." notice.
2. **Skips** text that says "NA" or "N/A" as a word, meaning no slots. City names that contain those letters, like CHENNAI, are not skipped.
3. **Treats as an alert** any photo or screenshot, and any other text.
4. **Sends** the alert on every channel that is turned on. Each channel is tried separately, so one failing does not stop the others.

## What you get

| Channel | What you get |
|---|---|
| **Android phone app** (Visa Alarm) | Full-screen red alarm at alarm volume, rings even on silent or vibrate, until you tap Dismiss or Open Telegram |
| **Mac alarm** | Volume to max, alarm sound and a spoken "Visa slot available", plus a pop-up, until you click it |
| **Telegram bot** | Just the group's message (photo with caption, or text). Set a loud sound for the bot's chat on your phone |
| **WhatsApp** | The message inside an approved template: "Your appointment alert has an update: ... Open Telegram to book." |
| **Email** to every address in `EMAIL_RECIPIENTS` | The message |
| **Telegram** copy to Saved Messages and a DM from your own account | Off by default: Telegram never notifies you about your own messages, so the bot replaced this |

The phone app and the Mac alarm both listen to a private channel on [ntfy.sh](https://ntfy.sh), a free push service. The watcher posts each alert to that channel (`NTFY_TOPIC`), and every device listening to it goes off at once. The channel name is long and random, so it works as a password; keep it private.

Besides alerts, you may get two other kinds of email:

- **"H1B watcher stopped: ..."** from the watcher itself, when something breaks (Telegram login expired, a crash). It says what happened and how to fix it, at most once every 6 hours per problem.
- **A "down" email from healthchecks.io**, when the watcher stops sending its "still alive" signal (every 5 minutes). No email from them means it is working.

## Where it runs

On a **free Oracle Cloud server** (Always Free plan, San Jose region). The account was never upgraded, so it cannot be charged. The server address is in `telegram-watcher/cloud/server_ip.txt`, and the watcher runs there as a service called `h1b-watcher` that restarts by itself if it crashes.

Oracle sometimes stops free servers it thinks are idle. If healthchecks.io emails you that it is down, log in to the Oracle Cloud console and start the instance again.

## What you need

- **The private files** in `~/.config/h1b-watcher/` on your Mac: `.env` (settings and passwords) and `session.session` (the saved Telegram login). Treat `session.session` like a password: anyone holding it can use your Telegram.
- **`~/.ssh/oracle_h1b`**, the key that lets you log in to the server.
- **`~/.oci/`**, the Oracle account key, only needed to create a new server.
- Python 3 on your Mac, and the GitHub app `gh` to download the repo.

The private files also live on the server in `/opt/h1b-watcher/`. If every copy is ever lost: get a new API ID and hash at my.telegram.org, create a new Google app password, and log in to Telegram again (it sends a code on first run).

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

## Settings

All settings live in `.env` (template: `telegram-watcher/.env.example`).

| Setting | What it is | Where to find it |
|---|---|---|
| `API_ID`, `API_HASH` | Lets the watcher log in to Telegram | my.telegram.org, then "API development tools" |
| `SOURCE_GROUP` | The group to watch | Already set to `Regular_H1B_H4_VisaSlotsChecking` |
| `EMAIL_ENABLED` | Email alerts on or off | `true` or `false` |
| `GMAIL_ADDRESS` | Gmail account that sends the alerts | Your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-letter password just for this app, not your real one | Google Account, Security, App passwords |
| `EMAIL_RECIPIENTS` | Who gets alert emails | Addresses separated by commas |
| `TELEGRAM_COPIES_ENABLED`, `TELEGRAM_RECIPIENT` | Telegram copies on or off, and the username (no @) that gets a DM | Your Telegram username |
| `WA_ENABLED` and the other `WA_` settings | WhatsApp alerts via Meta's WhatsApp Cloud API | Meta for Developers, your WhatsApp app; templates in WhatsApp Manager |
| `TG_BOT_TOKEN`, `TG_BOT_CHAT_ID` | The Telegram bot that sends you each alert | See "Telegram bot" below |
| `NTFY_TOPIC` | Private channel for the phone app and Mac alarm | Make one up: `echo visa-alert-$(openssl rand -hex 8)` |
| `HEALTHCHECK_URL` | The "still alive" link | healthchecks.io, your check's ping URL |
| `HEARTBEAT_DAYS` | Optional "still running" note every N days | `0` turns it off (healthchecks.io does this job instead) |

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

## Mac alarm

```
laptop-alarm/install.sh <your NTFY_TOPIC>
```

Installs a background job that starts at login. When an alert arrives it turns the volume to max, loops an alarm sound and a spoken warning, and shows a pop-up until you click Dismiss or Open Telegram, then puts the volume back. Remove it with `laptop-alarm/install.sh --uninstall`.

## Telegram bot

Messages the watcher sends from your own account never notify you, so alerts come from a bot instead.

1. In Telegram, message **@BotFather**, send `/newbot` and pick any name. It replies with a token: put it in `TG_BOT_TOKEN`.
2. Open your new bot's chat and tap **Start** (a bot cannot message you until you do).
3. Find your chat id: open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id` into `TG_BOT_CHAT_ID`.
4. Deploy. On your phone, open the bot's chat, tap its name, Notifications, Customize, and pick a loud sound. Telegram does not sound for a chat that is open on screen, and stays quiet when the phone is on vibrate; the Android app covers those cases.

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

## What the log looks like

```
2026-10-08 22:28:21,007 INFO Watching group, Telegram notifications stay as normal...
2026-10-08 07:28:16,221 INFO Alert sent: [image, no caption]
2026-10-08 20:35:50,502 WARNING WhatsApp send with template h1b_slot_update failed: 404 ...
```

"Watching group" means it connected. "Alert sent" means a slot alert went out. The WhatsApp warning is expected until Meta approves the template.

## Safety

- **Read-only in the group.** It never posts, reacts or messages anyone in the group.
- **No secrets in the repo.** `.env` and `session.session` are excluded by `.gitignore`.
- **One copy at a time.** Two copies using the same Telegram login can get the login cancelled. Do not run the watcher on your Mac while the server copy is running.
- **Cannot cost money.** The Oracle account is on the free plan and was never upgraded.

## Known issues

- **WhatsApp wording**: a business number can only start a chat with wording Meta approved in advance, and Meta does not allow the message alone: the variable cannot be at the start or end, there must be enough fixed text around it, and for US numbers the category must be Utility (Meta does not deliver Marketing messages to +1 numbers). `h1b_slot_short` is the shortest wording that passes. A template still in review is skipped and the next one in `WA_TEMPLATE` is used; the watcher emails and WhatsApps you once the first one is approved.
- **Email**: if the Gmail app password is revoked, email alerts fail (error "535" in the log). Create a new app password, update `GMAIL_APP_PASSWORD` in `~/.config/h1b-watcher/.env`, copy that file to `telegram-watcher/.env`, and run the deploy command.

## Moving to a new server

If Oracle deletes the server, `telegram-watcher/cloud/auto_setup.sh` requests a new free one, retrying every 3 minutes because free servers are often "out of capacity". It then installs everything and saves the new address in `cloud/server_ip.txt`. It uses the `h1b` profile in `~/.oci/config`.

## What is in the folders

```
h1b-appointment-watcher/
  README.md               this file
  setup.sh                one-time setup after downloading
  telegram-watcher/       the watcher (Python)
    h1b_slot_watcher.py   the program
    test_filter.py        tests for the alert rules
    requirements.txt      Python packages it needs
    .env.example          blank template of the settings file
    cloud/                scripts that create the Oracle server and copy the watcher to it
  android-app/            Visa Alarm, the one-button Android alarm app (Java)
  laptop-alarm/           Mac alarm: listener.sh and install.sh
```

## Disclaimer

For personal use. The watcher only reads a public group, but it uses your Telegram account to do so; use it within Telegram's terms.

## Related

[us-visa-bot](https://github.com/jeangnc/us-visa-bot) (ais-bot) is a different approach: it logs in to your own account on ais.usvisa-info.com and can rebook an earlier date automatically. It was considered and not used here, because frequent checks can lock your visa account and auto-rebooking cancels your current appointment.
