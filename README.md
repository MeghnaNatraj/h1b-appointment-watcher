# H1B Appointment Watcher

Watches a Telegram group where people report open US visa (H1B/H4) interview slots, and tells you the moment a real slot is posted.

## Features

- Watches the group 24 hours a day on a free cloud server, so your laptop can be off
- Ignores noise: the group's repeating notice and "NA" (no slots) messages
- Sends each real alert by email, and by WhatsApp once Meta approves the template
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

| Channel | Status today |
|---|---|
| **Email** to every address in `EMAIL_RECIPIENTS` | On |
| **WhatsApp** | On, but not delivering: Meta has not approved the `h1b_slot_update` template. You get an email the moment it is approved. |
| **Telegram** copy to Saved Messages and a DM | Off |

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
| `HEALTHCHECK_URL` | The "still alive" link | healthchecks.io, your check's ping URL |
| `HEARTBEAT_DAYS` | Optional "still running" note every N days | `0` turns it off (healthchecks.io does this job instead) |

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

- **WhatsApp**: fails with error 404 until the `h1b_slot_update` template is Active in WhatsApp Manager. No code change needed.
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
```

## Disclaimer

For personal use. The watcher only reads a public group, but it uses your Telegram account to do so; use it within Telegram's terms.

## Related

[us-visa-bot](https://github.com/jeangnc/us-visa-bot) (ais-bot) is a different approach: it logs in to your own account on ais.usvisa-info.com and can rebook an earlier date automatically. It was considered and not used here, because frequent checks can lock your visa account and auto-rebooking cancels your current appointment.
