# Daily Screenshot

Takes a daily screenshot of the [Canadian weather page](https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702) and uploads it to a shared Google Drive folder.

## How it works

1. Render cron job triggers daily at 6am
2. [thum.io](https://thum.io) captures a full-page screenshot
3. Screenshot is uploaded to Google Drive via a service account

## Setup

### Environment variables (set on Render)

- `THUM_AUTH` — thum.io auth key
- `GOOGLE_DRIVE_FOLDER_ID` — target Google Drive folder ID
- `GOOGLE_SERVICE_ACCOUNT_JSON` — raw JSON of the Google service account key

### Google Drive

The service account must be shared as an Editor/Content Manager on the target Shared Drive folder.

## Deployment

Deployed as a [Render cron job](https://render.com). Pushes to `main` trigger automatic redeployment.
