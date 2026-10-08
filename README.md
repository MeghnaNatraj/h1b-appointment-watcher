# H1B Appointment Watcher

Finds earlier US visa (H1B/H4) interview slots and tells you right away.

## What it does, in plain words

There is a public Telegram group, **Regular_H1B_H4_VisaSlotsChecking**, where people post when they see open visa interview slots. Watching it by hand is tiring, so this tool watches it for you, 24 hours a day.

Every time someone posts in the group, the watcher decides whether it is a real slot alert:

| Message in the group | What the watcher does |
|---|---|
| The group's repeating "H1 H4 inperson slots availa..." notice | Ignores it |
| A screenshot or photo | Treats it as an alert |
| Text saying "NA" or "N/A" (no slots) | Ignores it |
| Any other text | Treats it as an alert |

When it finds an alert, it sends it to you:

| Channel | Status |
|---|---|
| **Email** (to every address in the settings) | On |
| **WhatsApp** | On, but not delivering yet: Meta has not approved the message template, so sends fail |
| **Telegram** (a copy to your Saved Messages and a DM) | Off |

## Where it runs

It runs on a **free Oracle Cloud server** (Always Free plan, San Jose region, IP in `telegram-watcher/cloud/server_ip.txt`). The account was never upgraded, so it cannot be charged. Your laptop does not need to be on.

A free monitoring service (**healthchecks.io**) gets a "still alive" signal from the watcher every 5 minutes. **If those signals stop, healthchecks.io emails you.** No email from them means it is working.

Oracle sometimes stops free servers it thinks are idle. If you get the "it stopped" email, log in to the Oracle Cloud console and start the instance again.

## What is NOT in this repo (on purpose)

Two private files never go to GitHub:

- **`.env`**: the settings and passwords (Telegram API keys, Gmail app password, WhatsApp token, email list, monitoring link).
- **`session.session`**: the saved login to your Telegram account. Anyone holding it can use your Telegram, so treat it like a password.

They are kept in two places: on the server (`/opt/h1b-watcher/`) and on your Mac in **`~/.config/h1b-watcher/`**. To reach the server you also need **`~/.ssh/oracle_h1b`** (server key) and **`~/.oci/`** (Oracle account key). Keep all of these.

If they are ever all lost: get a new API ID and hash at my.telegram.org, a new Google app password, and log in to Telegram again (it texts a code on first run).

## Get it working again on a computer

1. Download the repo: `gh repo clone MeghnaNatraj/h1b-appointment-watcher`
2. Make sure `~/.config/h1b-watcher/` has `.env` and `session.session`.
3. Run `./setup.sh` inside the folder. It copies the private files in, installs what it needs and runs the tests.

To push a change to the server (edited script or settings): `telegram-watcher/cloud/deploy.sh $(cat telegram-watcher/cloud/server_ip.txt)`

## Everyday commands

Run these from the repo folder. `IP` is the server address.

```
IP=$(cat telegram-watcher/cloud/server_ip.txt)
```

| I want to... | Command |
|---|---|
| See if it is running | `ssh -i ~/.ssh/oracle_h1b opc@$IP systemctl is-active h1b-watcher` |
| See the last messages it logged | `ssh -i ~/.ssh/oracle_h1b opc@$IP sudo journalctl -u h1b-watcher -n 50` |
| Restart it | `ssh -i ~/.ssh/oracle_h1b opc@$IP sudo systemctl restart h1b-watcher` |

Only one copy may use the Telegram login at a time. Do not run the watcher on your Mac while the server copy is running.

## Known issues

- **WhatsApp**: alerts fail with "Template ... does not exist" until the `h1b_slot_update` template is Active in WhatsApp Manager. Nothing to change in the code; once Meta approves it, alerts start arriving.
- **Email**: if the Gmail app password is revoked or expires, email alerts fail (error "535" in the log). Create a new app password, put it in `GMAIL_APP_PASSWORD` in `~/.config/h1b-watcher/.env`, copy that file to `telegram-watcher/.env` and run the deploy command.

## Moving to a new server

If Oracle deletes the server, `telegram-watcher/cloud/auto_setup.sh` requests a new free one (it retries every 3 minutes, because free servers are often "out of capacity"), installs everything and saves the new IP in `cloud/server_ip.txt`. It uses the `h1b` profile in `~/.oci/config`.

## What is in the folders

```
h1b-appointment-watcher/
  README.md               this file
  setup.sh                one-time setup after downloading
  telegram-watcher/       the watcher (Python)
    h1b_slot_watcher.py   the program
    test_filter.py        tests for the alert rules
    requirements.txt      Python packages it needs
    .env.example          blank template of the private settings file
    cloud/                scripts that create the Oracle server and copy the watcher to it
  ais-bot/                second, optional tool (never set up, see below)
```

## The second tool: ais-bot (optional, not set up)

`ais-bot/` is a copy of github.com/jeangnc/us-visa-bot with one change: a Mac notification when it finds an earlier date. Instead of watching other people's reports, it logs in to **your own** account on ais.usvisa-info.com and checks for dates earlier than your booking.

Two warnings before ever using it:

- Without `--dry-run` it **books the earlier slot automatically**, which cancels your current appointment. Always use `--dry-run`.
- Checking too often can **lock your visa account**. Use a delay of minutes, not seconds.

Setup and options are in `ais-bot/README.md`.
