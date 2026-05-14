# Daily Weather Screenshot — How It Works

A daily screenshot of the [Canadian weather page](https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702) is automatically captured and uploaded to the `weather_scans` folder on the Island Irrigation shared Google Drive.

**Schedule:** Every day at midnight (12:00am PDT / 7:00 UTC)

## How it works

1. A Render cron job runs a Python script daily
2. The script uses [thum.io](https://thum.io) to capture a full-page screenshot of the weather page
3. The screenshot is uploaded to Google Drive using a Google service account

## If something breaks

- Check the cron job logs on Render: https://dashboard.render.com/cron/crn-d6u6sqea2pns73979n0g/settings
- If the Google key needs rotating, manage it here: https://console.cloud.google.com/iam-admin/serviceaccounts/details/112414728771443448088/keys?project=daily-screenshot-443720
- Source code: https://github.com/joshkcdev/daily_screenshot

## Environment variables (set on Render)

- `THUM_AUTH` — thum.io auth key
- `GOOGLE_DRIVE_FOLDER_ID` — target Google Drive folder ID
- `GOOGLE_SERVICE_ACCOUNT_JSON` — raw JSON of the Google service account key

## Google Drive

The service account must be shared as an Editor/Content Manager on the target Shared Drive folder.

## Deployment

Deployed as a [Render cron job](https://render.com). Pushes to `main` trigger automatic redeployment.

## Backup: raspi4

A parallel instance runs on a Raspberry Pi 4 and saves PNGs to `~/workspace/daily_screenshot/screenshots` on the Pi. To pull those screenshots down for local comparison:

```bash
python sync_raspi_screenshots.py            # rsync over SSH into ./raspi_screenshots/
python sync_raspi_screenshots.py --dry-run  # preview without copying
```

Prerequisite: a `~/.ssh/config` alias for the Pi (default: `raspi4`). Override with `--host`/`--remote-dir` flags or `RPI_SSH_HOST`/`RPI_REMOTE_DIR` env vars. The sync is incremental and never deletes local files.

## Drive download (for comparison)

To pull every screenshot the Render app has uploaded to Google Drive into `./drive_screenshots/`:

```bash
python download_drive_screenshots.py             # download everything (skips files already local)
python download_drive_screenshots.py --dry-run   # list what would be downloaded
```

Prerequisites:

- `GOOGLE_DRIVE_FOLDER_ID` set, either via your shell or via a `.env` file in the repo root (copy `.env.example` to `.env` and fill it in — `.env` is gitignored).
- The service-account JSON sitting in the repo root (filename matches `daily-screenshot-443720-*.json`). Both are gitignored.

Use this alongside `sync_raspi_screenshots.py` to compare the Render uploads against the raspi4's local backups.

## Cache-coherence check

thum.io occasionally serves a stale cached snapshot where the "Last updated" timestamp in the top-right of the page disagrees with the first column of the forecast calendar. To scan the most recent screenshots in both directories for this:

```bash
poetry run python check_cache_coherence.py            # last 30 in each dir
poetry run python check_cache_coherence.py --count 5  # quick spot-check
```

Prerequisite: `brew install tesseract` (the script uses local Tesseract OCR).

Per row the script emits the filename's date, the "Last updated" date extracted from the image, the leftmost calendar-column date, and a status:

- ✅ — all dates agree (page was fresh)
- ⚠️ stale-but-coherent — image is internally consistent but its date predates the filename's capture date (thum served a fully-cached old page)
- ❌ MISMATCH — "Last updated" disagrees with the calendar header (partial cache, the bug being hunted)
- ❓ OCR_FAILED — at least one region couldn't be parsed

## Diagnosing the cache

To find out whether stale captures are caused by thum.io's cache or by Environment Canada's upstream cache, run:

```bash
poetry run python diagnose_cache.py
```

The script fetches the EC weather page's raw HTML and a fresh thum.io capture at the same moment, extracts "Last updated" from each, and tells you which side is stale. Requires `THUM_AUTH` in `.env` or the shell.
