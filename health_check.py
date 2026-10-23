#!/usr/bin/env python3
"""
Compare the last N days of captures on the raspi4 backup with the Drive
uploads, per location, and report the gaps.

For every day in the window it reports:
- missing on both: no capture anywhere (unrecoverable; EC only shows today)
- missing on Drive only: Render missed it, but the Pi copy may fill the hole
- missing on Pi only: the backup missed it
- empty (0-byte) files
- several files for one day in the same folder
- repeats: byte-identical to the previous day's capture (a thum.io cache hit,
  so effectively a missing day)

Drive dates come from filenames, which works for the restored and backfilled
files whose createdTime was set by hand. Duncan merges the old `weather_scans`
archive (GOOGLE_DRIVE_FOLDER_ID) with its `Weather Scans/Duncan` folder; the
Oct 1-21 2026 copies in both are the same bytes and count once.

Exits 1 if anything was found, 0 if every day is present and unique.
"""

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from check_cache_coherence import parse_capture_date, parse_capture_location
from locations import LOCATIONS
from verify_latest_drive import ENV_FILE, SCOPES, load_dotenv, resolve_key_file


DEFAULT_HOST = "raspi4"
DEFAULT_REMOTE_DIR = "~/workspace/daily_screenshot/screenshots"

# First day each location was captured; earlier days aren't gaps.
SERIES_START = {
    "lake_cowichan": date(2026, 10, 21),
}

# Duncan's uploads before 2026-10-21 went to the old archive folder.
EXTRA_DRIVE_FOLDERS = {
    "duncan": ["GOOGLE_DRIVE_FOLDER_ID"],
}


@dataclass
class Capture:
    name: str
    size: int
    md5: str | None
    folder: str


# Files whose names don't parse, kept under this key so they're reported
# rather than silently looking like gaps.
UNPARSED = "unparsed"

# {location slug: {date: [Capture, ...]}}
Series = dict[str, dict[date, list[Capture]]]


def add(series: Series, name: str, size: int, md5: str | None, folder: str) -> None:
    d = parse_capture_date(name)
    slug = parse_capture_location(name)
    if d is None or slug is None:
        series.setdefault(UNPARSED, {}).setdefault(None, []).append(Capture(name, size, md5, folder))
        return
    series.setdefault(slug, {}).setdefault(d, []).append(Capture(name, size, md5, folder))


def list_pi(host: str, remote_dir: str) -> Series:
    # One line per file: "<size>\t<md5>  <name>". Names can contain spaces.
    script = (
        f"cd {remote_dir} && for f in *.png *.jpg *.jpeg; do "
        '[ -e "$f" ] || continue; '
        'printf "%s\\t%s\\n" "$(stat -c %s "$f")" "$(md5sum "$f")"; done'
    )
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=15", host, script],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh {host} failed: {result.stderr.strip()}")

    series: Series = {}
    for line in result.stdout.splitlines():
        size_s, _, rest = line.partition("\t")
        md5, _, name = rest.partition("  ")
        add(series, name, int(size_s), md5, "pi")
    return series


def list_drive(drive) -> Series:
    series: Series = {}
    seen: set[tuple[str, date | None, str]] = set()
    for location in LOCATIONS:
        for env in [location.folder_env, *EXTRA_DRIVE_FOLDERS.get(location.slug, [])]:
            folder_id = os.environ.get(env)
            if not folder_id:
                raise RuntimeError(f"{env} not set. Put it in {ENV_FILE} or export it.")
            page_token = None
            while True:
                resp = drive.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="nextPageToken, files(name, size, md5Checksum)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                for f in resp.get("files", []):
                    if parse_capture_location(f["name"]) not in (location.slug, None):
                        continue
                    # The same capture copied into two folders counts once.
                    key = (location.slug, parse_capture_date(f["name"]),
                           f.get("md5Checksum") or f["name"])
                    if key in seen:
                        continue
                    seen.add(key)
                    add(series, f["name"], int(f.get("size", 0)), f.get("md5Checksum"), env)
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
    return series


def ranges(days: list[date]) -> str:
    """Collapse sorted dates into 'Oct 3–Oct 17 2026 (15), Oct 20 2026'."""
    if not days:
        return ""
    out = []
    start = prev = days[0]
    for d in days[1:] + [None]:
        if d is not None and d - prev == timedelta(days=1):
            prev = d
            continue
        n = (prev - start).days + 1
        if n == 1:
            out.append(start.strftime("%b %-d %Y"))
        else:
            out.append(f"{start.strftime('%b %-d')}–{prev.strftime('%b %-d %Y')} ({n})")
        if d is not None:
            start = prev = d
    return ", ".join(out)


def problems(by_date: dict[date, list[Capture]], window: list[date]) -> dict[str, list]:
    empty, repeats, multiple = [], [], []
    prev_md5 = None
    for d in window:
        caps = by_date.get(d, [])
        # Two folders can each hold a capture for the switchover day (Oct 21
        # 2026: Render's run went to the archive, a manual run to Duncan).
        folders = [c.folder for c in caps]
        if len(folders) != len(set(folders)):
            multiple.append(f"{d:%b %-d %Y} ({', '.join(c.name for c in caps)})")
        if any(c.size == 0 for c in caps):
            empty.append(d)
        md5s = {c.md5 for c in caps if c.size}
        if prev_md5 and prev_md5 in md5s:
            repeats.append(d)
        prev_md5 = next(iter(md5s)) if len(md5s) == 1 else None
    return {"empty": empty, "repeats": repeats, "multiple": multiple}


def main() -> int:
    load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(description="Compare Pi and Drive captures and report gaps.")
    parser.add_argument("--days", type=int, default=90, help="Days to check, ending today (default: 90)")
    parser.add_argument("--host", default=os.environ.get("RPI_SSH_HOST", DEFAULT_HOST))
    parser.add_argument("--remote-dir", default=os.environ.get("RPI_REMOTE_DIR", DEFAULT_REMOTE_DIR))
    args = parser.parse_args()

    today = date.today()
    first = today - timedelta(days=args.days - 1)

    print(f"Daily Screenshot health — {first:%b %-d %Y} to {today:%b %-d %Y} ({args.days} days)")
    print("=" * 72)

    try:
        pi = list_pi(args.host, args.remote_dir)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"⚠️  Couldn't list the Pi: {e}")
        return 2

    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(resolve_key_file()), scopes=SCOPES
        )
        drive_series = list_drive(build("drive", "v3", credentials=credentials))
    except (FileNotFoundError, RuntimeError) as e:
        print(f"⚠️  {e}")
        return 2

    found = False
    for source, series in [("Drive", drive_series), ("Pi", pi)]:
        unparsed = series.get(UNPARSED, {}).get(None, [])
        if unparsed:
            found = True
            names = ", ".join(sorted({c.name for c in unparsed})[:5])
            print(f"⚠️  {len(unparsed)} file(s) on {source} with unrecognized names, not counted: {names}")

    for location in LOCATIONS:
        start = max(first, SERIES_START.get(location.slug, first))
        window = [start + timedelta(days=i) for i in range((today - start).days + 1)]
        pi_days = pi.get(location.slug, {})
        drive_days = drive_series.get(location.slug, {})

        both = [d for d in window if d not in pi_days and d not in drive_days]
        drive_only = [d for d in window if d in pi_days and d not in drive_days]
        pi_only = [d for d in window if d not in pi_days and d in drive_days]
        pi_problems = problems(pi_days, window)
        drive_problems = problems(drive_days, window)

        print()
        print(f"{location.name} — {len(window)} day(s) from {start:%b %-d %Y}")
        print("-" * 72)
        print(f"  Drive: {sum(d in drive_days for d in window)}/{len(window)} days   "
              f"Pi: {sum(d in pi_days for d in window)}/{len(window)} days")

        rows = [
            ("❌ Missing on both (unrecoverable)", both),
            ("❌ Missing on Drive (Pi has it)", drive_only),
            ("⚠️  Missing on Pi (Drive has it)", pi_only),
            ("❌ Empty on Drive", drive_problems["empty"]),
            ("⚠️  Empty on Pi", pi_problems["empty"]),
            ("❌ Repeat of previous day on Drive", drive_problems["repeats"]),
            ("⚠️  Repeat of previous day on Pi", pi_problems["repeats"]),
        ]
        for label, days in rows:
            if days:
                found = True
                print(f"  {label}: {ranges(days)}")
        for source, probs in [("Drive", drive_problems), ("Pi", pi_problems)]:
            for entry in probs["multiple"]:
                found = True
                print(f"  ⚠️  Several files for one day on {source}: {entry}")
        if not any(days for _, days in rows) and not (
            pi_problems["multiple"] or drive_problems["multiple"]
        ):
            print("  ✅ Every day present on both, no empties or repeats")

    print()
    print("=" * 72)
    print("❌ Problems found (see above)" if found else "✅ No gaps")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
