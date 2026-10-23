# Changelog

This file is the commit-traceable history of Daily Screenshot. Committed
entries are grouped by date in reverse chronological order and retain the Git
commit's short hash and summary. Work that has not yet been committed belongs
under **Unreleased**.

Documentation-only follow-up commits that maintain this file do not list
themselves.

## Unreleased

## 2026-10-23

- `8006190` — Teach check_cache_coherence.py the per-location filenames

## 2026-10-21

- `e6fea98` — Capture Duncan and Lake Cowichan into separate Weather Scans folders

## 2026-10-20

- `49c77c3` — Ignore the raspi4 screenshots and cron logs
- `293a2ba` — Add a missed-run check and a nightly failure alert for the Pi
- `896f331` — Flag byte-identical consecutive uploads in verify_latest_drive.py

## 2026-10-19

- `70790c1` — Add LOCAL_SAVE_DIR mode to thum.py for the raspi4 backup
- `5b15f05` — Reject empty thum.io responses and report bad files in verifier

## 2026-09-30

- `a5124e6` — Add vault pointer to CLAUDE.md

## 2026-08-07

- `a622b1b` — Move local secrets to ~/.secret/island-utility/
- `3c1a790` — Add --links flag to verify_latest_drive.py to print Drive web links

## 2026-05-14

- `4e7d500` — Add verify_latest_drive.py to spot-check the cache-bust in production
- `8b7b241` — Update README: document cache-bust and reframe diagnostic tools
- `d471750` — Cache-bust at the inner URL to force fresh thum.io captures
- `abb2d12` — Add diagnose_cache.py to locate the source of stale captures
- `98d7469` — Add Drive download + cache-coherence check utilities
- `58674fb` — Add sync_raspi_screenshots.py to pull Pi backups via rsync

## 2026-04-24

- `9ac8fd5` — Remove maxAge/1 from thum.io requests to fix 403 errors

## 2026-04-21

- `5aeb275` — Add rename utility script and gitignore service account keys
- `f55529f` — Add maxAge/1 to thum.io requests to force fresh screenshots

## 2026-03-25

- `88cd04e` — Add cache-busting nonce to thum.io requests to prevent stale screenshots

## 2026-03-24

- `78e946d` — Change cron schedule to 12am PDT to match Zapier/Urlbox timing

## 2026-03-23

- `1f930a0` — Update screenshot filename format to match previous naming convention
- `d7955a9` — Change cron schedule to 4pm PDT to match previous screenshot timing

## 2026-03-19

- `39c8c1b` — Update README with current setup details
- `2cbe14f` — Remove debug logging now that upload is working
- `87035ac` — Add debug logging for shared drive folder access
- `0f11717` — Support Shared Drives: use full drive scope and supportsAllDrives
- `cb1a3f3` — Read Google service account JSON directly instead of base64
- `86abf37` — Disable Poetry package mode for Render build
- `5feb7ee` — Fix README.md casing for Poetry build on Render
- `68e162f` — Add Google Drive upload and Render cron job config

## 2024-12-04

- `b2b5fa4` — filename
- `f6356ea` — paths
- `f5d35e9` — paths
- `0d2cbe2` — update paths
- `2389095` — fixing paths

## 2024-12-03

- `01594e2` — fixed missing dir
- `e997acc` — updated to thum.io for image creation

## 2024-12-02

- `4f99df4` — init
