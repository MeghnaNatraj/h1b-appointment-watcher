# Agent instructions

How to run, change and fix this project. Written for Claude or any coding agent working on Meghna's Mac. The README is the short human overview.

## Hard rules

- **Never commit secrets.** These stay in `~/.config/h1b-watcher/` and are gitignored: `.env`, `session.session`, `server_ip.txt`, `VisaAlarm.apk`, and the personal clips `vastuguna.m4a` and `pinkblush.m4a`. Before any push, check `git status` shows none of them. The repo is public.
- **Never run the watcher on the Mac** except briefly to log in to Telegram (see "Telegram logged out"). Two copies on one Telegram login can get the login cancelled. Only the server runs it.
- **Read only in Telegram.** The watcher must never post, react or message anyone.
- **Change settings on the Mac, not the server.** Deploy copies the Mac's `.env` over the server's.
- **Ask Meghna before** force pushing, rewriting git history, deleting the server, or changing the ntfy channel (changing it means rebuilding and reinstalling the phone app).

## Layout

| Path | What it is |
|---|---|
| `telegram-watcher/h1b_slot_watcher.py` | The watcher: Telegram client, filter, alerts, healthcheck pings |
| `telegram-watcher/slot_image.py` | Reads screenshots with tesseract and writes the "slot details" line |
| `telegram-watcher/test_*.py` | Unit tests, run by `setup.sh` |
| `telegram-watcher/cloud/` | `auto_setup.sh` (create an Oracle server), `deploy.sh` (push code and settings), `setup_server.sh` (runs on the server) |
| `android-app/` | Visa Alarm, the Android app (Java, no dependencies) |
| `docs/system-design.html` | Full design document |
| `setup.sh` | Copies private files in from `~/.config/h1b-watcher/`, builds the Python venv, runs tests |

## Private files

All in `~/.config/h1b-watcher/` on the Mac. `setup.sh` copies them into the repo folder.

- `.env`: settings. Template: `telegram-watcher/.env.example`. Keys: `API_ID`, `API_HASH`, `SOURCE_GROUP`, `NTFY_TOPIC`, `HEALTHCHECK_URL`, `OCR_ENABLED`.
- `session.session`: the Telegram login. Treat it like a password.
- `server_ip.txt`: the Oracle server address. `setup.sh` copies it to `telegram-watcher/cloud/server_ip.txt`.
- `VisaAlarm.apk`: the latest built phone app.

Other keys: `~/.ssh/oracle_h1b` (SSH to the server), `~/.oci/` with profile `h1b` (Oracle account, only for creating a server).

Read secrets into shell variables; never print them.

## Server commands

Run from the repo root after `./setup.sh`.

```bash
IP=$(cat telegram-watcher/cloud/server_ip.txt)
ssh -i ~/.ssh/oracle_h1b opc@$IP systemctl is-active h1b-watcher            # is it running
ssh -i ~/.ssh/oracle_h1b opc@$IP sudo journalctl -u h1b-watcher -n 50       # logs
ssh -i ~/.ssh/oracle_h1b opc@$IP sudo systemctl restart h1b-watcher         # restart
ssh -i ~/.ssh/oracle_h1b opc@$IP 'sudo -u watcher /opt/h1b-watcher/venv/bin/python /opt/h1b-watcher/h1b_slot_watcher.py --test-alert'   # ring the phone
```

In the log, "Watching group" means connected and "Alert sent" means an alert went out. The service is `h1b-watcher`, installed in `/opt/h1b-watcher`, running as user `watcher`.

## Changing the watcher

1. Edit code in `telegram-watcher/`, or settings in `~/.config/h1b-watcher/.env`.
2. `./setup.sh` (copies settings in and runs the tests; stop if tests fail).
3. `telegram-watcher/cloud/deploy.sh $(cat telegram-watcher/cloud/server_ip.txt)`
4. Send a test alert and check the log.

## Phone app

**Build.** Tools: Java 17 and the Android SDK at Homebrew paths. Install them if missing (about 2 GB; accepting the SDK licenses needs Meghna's OK the first time on a new Mac):

```bash
brew install openjdk@17
brew install --cask android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@17 ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
yes | sdkmanager --licenses
sdkmanager "platforms;android-34" "build-tools;34.0.0" "platform-tools"
```

Then build with the channel name from `.env`, without echoing it:

```bash
cd android-app
export JAVA_HOME=/opt/homebrew/opt/openjdk@17 ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
T=$(grep -E '^NTFY_TOPIC=' ../telegram-watcher/.env | cut -d= -f2- | tr -d '"'"'"' \r')
./gradlew -q assembleRelease -PntfyTopic="$T"
```

Output: `android-app/app/build/outputs/apk/release/app-release.apk`. Bump `versionCode` and `versionName` in `android-app/app/build.gradle` for each release. Copy the APK to `~/.config/h1b-watcher/VisaAlarm.apk` and `~/Downloads/VisaAlarm-<version>.apk`.

**Install over USB.** `$ANDROID_HOME/platform-tools/adb devices` must list the phone as `device`. If it is missing, Meghna needs to turn on USB debugging (Settings, About phone, Software information, tap Build number 7 times; then Developer options, USB debugging), turn off Samsung Auto Blocker, and tap Allow on the phone. Then:

```bash
$ANDROID_HOME/platform-tools/adb install -r ~/.config/h1b-watcher/VisaAlarm.apk
$ANDROID_HOME/platform-tools/adb shell dumpsys package com.meghna.visaalarm | grep -m1 versionName
```

**Alarm sounds.** Built in: phone alarm (`alarm`) and `scream` (`res/raw/scream.mp3`, CC0). Personal clips are optional and gitignored: `vastuguna` and `pinkblush` in `res/raw/`. Each is looked up by name with `Alarm.personalClip()` and hidden from the dropdown when absent.

To add a personal clip:
1. Cut it with ffmpeg to AAC: `ffmpeg -ss <start> -to <end> -i <source> -vn -c:a aac -b:a 128k -ar 44100 android-app/app/src/main/res/raw/<name>.m4a`
2. Add `<name>` to `SOUND_KEYS` and a label to `SOUND_LABELS` in `MainActivity.java`, and a `case "<name>":` beside `vastuguna` in `Alarm.soundUri()`.
3. Add `android-app/app/src/main/res/raw/<name>.*` to `.gitignore`.
4. Build, install, and ask Meghna to tap Test alarm.

## When something breaks

| Symptom | Fix |
|---|---|
| Alarm says "Telegram login" | Telegram logged out. On the Mac: `cd telegram-watcher && h1b_watcher_venv/bin/python h1b_slot_watcher.py`; Meghna types the code Telegram sends; wait for "Watching group"; Ctrl+C. Then `cp session.session ~/.config/h1b-watcher/`, `ssh -i ~/.ssh/oracle_h1b opc@$IP sudo rm /opt/h1b-watcher/session.session`, and deploy. |
| "Watcher stopped" from healthchecks.io | Check the service and logs. If SSH fails, Oracle may have stopped the server: Meghna starts it in the Oracle console. If it was deleted, run `telegram-watcher/cloud/auto_setup.sh` (it retries until Oracle has capacity, deploys, and saves the new address to both `server_ip.txt` files). |
| Watcher crashes | systemd restarts it after 30 seconds and it catches up on missed messages. Check logs for the cause. |
| Phone doesn't ring on a test alert | Check the app's box is green (ON) and that the APK was built with the current `NTFY_TOPIC`. |

The watcher sends the same problem alert at most once every 6 hours.

## Fresh setup on a new Mac

1. `gh repo clone MeghnaNatraj/h1b-appointment-watcher && cd h1b-appointment-watcher`
2. Make sure `~/.config/h1b-watcher/` has the private files (Meghna restores them from her backup). With no `.env`, copy `telegram-watcher/.env.example` there and have Meghna fill it in.
3. `./setup.sh`
4. If there is no working server, `telegram-watcher/cloud/auto_setup.sh`.
5. healthchecks.io (only if the check is new): 5 minute period, ping URL in `HEALTHCHECK_URL`, and a webhook that POSTs to `https://ntfy.sh/<NTFY_TOPIC>` with headers `Title: Watcher stopped`, `Priority: urgent` when down, and `Title: Watcher back`, `Priority: low` when up.
6. Build and install the phone app, then send a test alert.
