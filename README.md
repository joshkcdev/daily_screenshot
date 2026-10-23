# Daily Weather Screenshot — How It Works

A daily screenshot of the Environment Canada weather page for each location in `locations.py` is automatically captured and uploaded to that location's folder under `Snow Removal/2026-27/Weather Scans` on the IILH shared Google Drive:

| Location | Page | Drive folder | Filename |
|---|---|---|---|
| Duncan | [coords=48.779,-123.702](https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702) | `Weather Scans/Duncan` | `weather_duncan_YYYY-MM-DD.png` |
| Lake Cowichan | [coords=48.825,-124.054](https://weather.gc.ca/en/location/index.html?coords=48.825,-124.054) | `Weather Scans/Lake Cowichan` | `weather_lake_cowichan_YYYY-MM-DD.png` |

Before 2026-10-22, only Duncan was captured, uploaded to the `weather_scans` folder as `weather_daily_Mon_D_YYYY.png`. That folder is kept as the archive.

**Schedule:** Every day at midnight (12:00am PDT / 7:00 UTC)

## How it works

1. A Render cron job runs `thum.py` daily.
2. The script uses [thum.io](https://thum.io) to capture a full-page screenshot of each location's weather page.
3. Each screenshot is uploaded to its location's Google Drive folder using a Google service account. If one location fails, the others still run, and the job then exits non-zero.

### Cache-busting

thum.io keys its render cache off the *source* URL we pass it, not the full thum.io request URL. To force a fresh render every run, `thum.py` appends a unique `?_=<unix_ts>` query param to the inner Environment Canada URL. Earlier `nonce/<ts>/` path segments were ignored by thum.io's cache layer (verified with `diagnose_cache.py`). Don't remove the inner-URL cache-bust — it's the thing that actually works.

## If something breaks

- Check the cron job logs on Render: https://dashboard.render.com/cron/crn-d6u6sqea2pns73979n0g/settings
- If the Google key needs rotating, manage it here: https://console.cloud.google.com/iam-admin/serviceaccounts/details/112414728771443448088/keys?project=daily-screenshot-443720
- Source code: https://github.com/joshkcdev/daily_screenshot

## Environment variables (set on Render)

- `THUM_AUTH` — thum.io auth key
- `GOOGLE_DRIVE_FOLDER_ID_DUNCAN` — Drive folder ID for `Weather Scans/Duncan`
- `GOOGLE_DRIVE_FOLDER_ID_LAKE_COWICHAN` — Drive folder ID for `Weather Scans/Lake Cowichan`
- `GOOGLE_SERVICE_ACCOUNT_JSON` — raw JSON of the Google service account key

## Google Drive

The service account must be shared as an Editor/Content Manager on the target Shared Drive folder. It is shared as Content manager on `Weather Scans`, so it can write to both location subfolders.

To add a location, add an entry to `locations.py`, create its subfolder under `Weather Scans`, and set its folder ID variable on Render and the Pi.

## Deployment

Deployed as a [Render cron job](https://render.com). Pushes to `main` trigger automatic redeployment.

## Backup: raspi4

A parallel instance runs on a Raspberry Pi 4 and saves PNGs to `~/workspace/daily_screenshot/screenshots` on the Pi. It runs this same `thum.py` with `LOCAL_SAVE_DIR` set, which saves each location's screenshot there and skips Google Drive (the Drive variables aren't needed). The Pi's cron job (00:00 Pacific) loads `THUM_AUTH` and `LOCAL_SAVE_DIR` from `~/.secret/island-utility/daily-screenshot.env`.

To pull those screenshots down for local comparison:

```bash
python sync_raspi_screenshots.py            # rsync over SSH into ./raspi_screenshots/
python sync_raspi_screenshots.py --dry-run  # preview without copying
```

Prerequisite: a `~/.ssh/config` alias for the Pi (default: `raspi4`). Override with `--host`/`--remote-dir` flags or `RPI_SSH_HOST`/`RPI_REMOTE_DIR` env vars. The sync is incremental and never deletes local files.

### Nightly check and alert

The Pi also runs `alert_on_failure.py` at 02:00 Pacific. It runs `verify_latest_drive.py --location <slug> --max-age-hours 12` for each location and, if any fail, sends one email with all the output via Resend. Because it runs off Render, it also catches a Render run that never happened. On top of the variables above, it needs each location's `GOOGLE_DRIVE_FOLDER_ID_*`, `RESEND_API_KEY`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO` in the same env file, plus the service-account key JSON in `~/.secret/island-utility/`, and `tesseract-ocr` from apt.

### Health check: Pi vs Drive

```bash
poetry run python health_check.py             # last 90 days
poetry run python health_check.py --days 365
```

Run from the Mac. For each location it lists the Pi's captures over SSH and the Drive folders with the service account (Duncan also includes the old `weather_scans` archive). It then reports days missing on both, on Drive only (the Pi copy might fill the gap) or on the Pi only, plus empty files and byte-identical repeats of the previous day. Exits 1 if anything is found. In Claude Code, the `/screenshot-health` skill runs it, checks the Pi's cron and verify logs, and separates new problems from the gaps already recorded in the vault.

## Drive download (for comparison)

To pull every screenshot the Render app has uploaded to Google Drive into `./drive_screenshots/`:

```bash
python download_drive_screenshots.py             # download everything (skips files already local)
python download_drive_screenshots.py --dry-run   # list what would be downloaded
```

Prerequisites:

- `GOOGLE_DRIVE_FOLDER_ID` set, either via your shell or in `~/.secret/island-utility/daily-screenshot.env` (loaded automatically; see `.env.example` for the expected keys).
- The service-account JSON in `~/.secret/island-utility/` (filename matches `daily-screenshot-443720-*.json`).

Use this alongside `sync_raspi_screenshots.py` to compare the Render uploads against the raspi4's local backups.

## If the cache problem comes back

Historically, thum.io served snapshots that lagged the live page by days to weeks. The cache-busting in `thum.py` (see above) fixes this — three tools are here for ongoing verification and investigation.

### `verify_latest_drive.py` — daily spot-check

```bash
poetry run python verify_latest_drive.py            # check the latest upload
poetry run python verify_latest_drive.py --count 3  # check the latest 3
poetry run python verify_latest_drive.py --location lake_cowichan  # check one location's folder
```

Without `--location` it checks `GOOGLE_DRIVE_FOLDER_ID` (the old `weather_scans` archive).

Pulls the newest Drive upload(s) in memory, OCRs the "Last updated" date, and compares it to the upload date. ✅ if within 1 day (normal — EC's last forecast issuance can be the prior evening), ❌ if more (the cache bug is back). It also flags ❌ DUPLICATE when a file's Drive md5 matches the upload before it — a byte-identical copy is a cache hit even if the lag looks fine. `--max-age-hours N` also fails when the newest upload is more than N hours old (a run that never happened). Exits non-zero on any of these so it can be wired into notifications.

### `diagnose_cache.py` — is it thum.io or upstream?

```bash
poetry run python diagnose_cache.py
```

Fetches the EC weather page's raw HTML and a fresh thum.io capture at the same instant, then compares "Last updated" from each. Tells you whether the staleness lives at thum.io or at Environment Canada — a different fix path for each. Requires `THUM_AUTH` in `~/.secret/island-utility/daily-screenshot.env`.

### `check_cache_coherence.py` — scan historical captures

```bash
poetry run python check_cache_coherence.py            # last 30 in each dir
poetry run python check_cache_coherence.py --count 5  # quick spot-check
poetry run python check_cache_coherence.py --location lake_cowichan  # one location only
```

Reads both the per-location names (`weather_<location>_YYYY-MM-DD.png`) and the older `weather_daily_*` names, which count as `duncan`. Without `--location`, the newest files from every location are mixed in one table.

Uses local Tesseract OCR (`brew install tesseract`) to extract the "Last updated" date and the leftmost forecast-calendar date from each image in `./raspi_screenshots/` and `./drive_screenshots/`. Status per row:

- ✅ — all dates agree
- ⚠️ stale-but-coherent — image is internally consistent but its date predates the filename
- ❌ MISMATCH — "Last updated" disagrees with the calendar header (partial cache)
- ❓ OCR_FAILED — region couldn't be parsed
