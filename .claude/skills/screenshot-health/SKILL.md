---
name: screenshot-health
description: Check the health of the Daily Screenshot setup — compare the last 90 days of captures on the raspi4 backup with the Drive uploads, per location (Duncan, Lake Cowichan), and report gaps, empty files and stale repeats, separating new problems from known history. Use when the user asks to check the daily screenshot / weather scan health, look for gaps or missing days, or compare the Pi against Drive. Read-only.
user-invocable: true
---

# Screenshot Health

Compare what the Pi saved with what Render uploaded to Drive, day by day, and tell the user
what's missing, what's recoverable, and what's new since the last known state.

Arguments: a number of days (e.g. `30`, `365`) overrides the default 90.

## Never

- Upload, rename, replace or delete anything in Drive, or touch files on the Pi. This skill
  reports. Restoring a day is a separate task the user approves.
- Print secrets from `~/.secret/island-utility/`.

## 1. Run the comparison

From the repo root:

```bash
poetry run python health_check.py            # last 90 days
poetry run python health_check.py --days N   # if the user gave a number
```

It lists the Pi's `~/workspace/daily_screenshot/screenshots` over SSH (alias `raspi4`) and
both locations' Drive folders with the service account, and takes about 15 seconds. Exit
codes: 0 no problems, 1 problems found, 2 couldn't reach the Pi or Drive.

On exit 2, say which side failed and stop. Common causes: the Pi is off or off the network
(`ssh raspi4 true`), a missing `GOOGLE_DRIVE_FOLDER_ID*` in
`~/.secret/island-utility/daily-screenshot.env`, or a missing service-account key. If
`import` fails, run `poetry install --no-root` once and retry.

## 2. Check the nightly jobs

The comparison shows what exists, not whether the jobs are healthy now. Also run:

```bash
ssh raspi4 'cd ~/workspace/daily_screenshot && tail -15 cron.log && grep -c "❌" verify.log; grep "❌" verify.log | tail -5'
```

`cron.log` should end with `Done.` from last night's 00:00 capture. Any `❌` in `verify.log`
means the 02:00 check failed and should have emailed `josh@jkc.dev`.

## 3. Separate known history from new problems

Read `Decisions.md` in the vault project
(`Clients/Island Utility/Projects/Daily Screenshot`) — the audits there record past gaps.
Anything already recorded there is **known**; say so in one line rather than alarming the
user. As of 2026-10-23 the 90-day window holds these known items, which age out by
early 2027:

- Duncan **Sep 1 2026 empty on Drive**: a 0-byte upload from before the PNG check; the
  Pi's copy that day is a stale repeat, so it can't be restored.
- Duncan **Pi repeats up to Oct 19 2026**: the Pi ran old code without the cache-bust until
  its rebuild, so it only rendered fresh about every 16 days.
- Lake Cowichan **Oct 21 2026 missing on Pi**: the Pi pulled the two-location code after
  that night's run.

Everything else is new. How to read each row:

| Row | Meaning |
|---|---|
| ❌ Missing on both | Unrecoverable — EC only shows the current page |
| ❌ Missing on Drive (Pi has it) | Render missed it. Recoverable **only if** the Pi copy is fresh — OCR it with `check_cache_coherence.py` and check it isn't a repeat before proposing a restore |
| ⚠️ Missing on Pi | The backup missed it; Drive is fine. Check `cron.log` on the Pi |
| ❌ Empty on Drive / ⚠️ Empty on Pi | thum.io returned nothing; on Drive this is effectively a missing day |
| ❌ Repeat on Drive | Byte-identical to the day before: a thum.io cache hit, so the day is stale |
| ⚠️ Repeat on Pi | Same, for the backup |
| ⚠️ Several files for one day | Two captures of one day in the same folder; one is probably a manual run |
| ⚠️ Unrecognized names | A filename format `parse_capture_date` doesn't know. Add it in `check_cache_coherence.py` and rerun — until then those days look missing |

A problem on today's date before ~00:05 Pacific just means tonight's run hasn't happened yet.

## 4. Report

Keep it short:

- **Verdict** in one line: healthy, or what's wrong.
- **New problems**, each with the dates and what it means (recoverable or not, which side).
- **Known history**, one line listing what's already recorded.
- **Nightly jobs**: last capture time and whether the 02:00 check passed.
- **Next step** only if there's something to do, such as restoring a day from the Pi
  (after OCR confirms it's fresh) or investigating a missed run. Ask before doing it.

If you find a new problem, offer to log it in the vault `Decisions.md` (unrecoverable gaps)
or `Tasks.md` (something to fix). Don't write `SESSIONS.md`; that's `/save-game`.
