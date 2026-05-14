# Daily Weather Screenshot — How It Works

A daily screenshot of the [Canadian weather page](https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702) is automatically captured and uploaded to the `weather_scans` folder on the Island Irrigation shared Google Drive.

**Schedule:** Every day at midnight (12:00am PDT / 7:00 UTC)

## How it works

1. A Render cron job runs `thum.py` daily.
2. The script uses [thum.io](https://thum.io) to capture a full-page screenshot of the weather page.
3. The screenshot is uploaded to Google Drive using a Google service account.

### Cache-busting

thum.io keys its render cache off the *source* URL we pass it, not the full thum.io request URL. To force a fresh render every run, `thum.py` appends a unique `?_=<unix_ts>` query param to the inner Environment Canada URL. Earlier `nonce/<ts>/` path segments were ignored by thum.io's cache layer (verified with `diagnose_cache.py`). Don't remove the inner-URL cache-bust — it's the thing that actually works.

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

## If the cache problem comes back

Historically, thum.io served snapshots that lagged the live page by days to weeks. The cache-busting in `thum.py` (see above) fixes this — but if you ever notice old screenshots appearing again, two tools are here to investigate.

### `diagnose_cache.py` — is it thum.io or upstream?

```bash
poetry run python diagnose_cache.py
```

Fetches the EC weather page's raw HTML and a fresh thum.io capture at the same instant, then compares "Last updated" from each. Tells you whether the staleness lives at thum.io or at Environment Canada — a different fix path for each. Requires `THUM_AUTH` in `.env`.

### `check_cache_coherence.py` — scan historical captures

```bash
poetry run python check_cache_coherence.py            # last 30 in each dir
poetry run python check_cache_coherence.py --count 5  # quick spot-check
```

Uses local Tesseract OCR (`brew install tesseract`) to extract the "Last updated" date and the leftmost forecast-calendar date from each image in `./raspi_screenshots/` and `./drive_screenshots/`. Status per row:

- ✅ — all dates agree
- ⚠️ stale-but-coherent — image is internally consistent but its date predates the filename
- ❌ MISMATCH — "Last updated" disagrees with the calendar header (partial cache)
- ❓ OCR_FAILED — region couldn't be parsed
