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
