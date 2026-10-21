#!/usr/bin/env python3
"""
Verify the latest screenshots in the Render-uploaded Drive folder aren't
stale-cached. Run this tomorrow / the day after to confirm the inner-URL
cache-bust in thum.py held up in production.

For each of the most recent uploads it pulls the file in memory, OCRs the
top region, and compares the page's "Last updated" date with the upload
date. A delta of 0-1 day is fine (EC's last forecast issuance can be the
prior evening); anything bigger means thum.io is caching again.

It also compares each file's Drive md5 with the upload before it. A
byte-identical copy of the previous day is a thum.io cache hit, even when
the lag looks fine.
"""

import argparse
import io
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytesseract
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image, UnidentifiedImageError

from locations import LOCATIONS, get_location


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SECRETS_DIR = Path.home() / ".secret" / "island-utility"
KEY_GLOB = "daily-screenshot-443720-*.json"
ENV_FILE = SECRETS_DIR / "daily-screenshot.env"

WEEKDAYS = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

RE_UPDATED_AT = re.compile(
    rf"Last\s+updated.*?\b({WEEKDAYS})[a-z]*\s+(\d{{1,2}})\s+({MONTHS})[a-z]*\s+(\d{{4}})",
    re.IGNORECASE | re.DOTALL,
)
RE_CAL_COLUMN = re.compile(
    rf"\b({WEEKDAYS})[a-z]*[\s,]*\n?[\s,]*(\d{{1,2}})\s+({MONTHS})",
    re.IGNORECASE,
)

MONTH_NUMS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_key_file() -> Path:
    matches = sorted(SECRETS_DIR.glob(KEY_GLOB))
    if not matches:
        raise FileNotFoundError(f"No service-account key matching {SECRETS_DIR / KEY_GLOB}")
    return matches[-1]


def extract_updated_at(text: str) -> date | None:
    m = RE_UPDATED_AT.search(text)
    if not m:
        return None
    _, day_s, month_s, year_s = m.groups()
    month = MONTH_NUMS.get(month_s.lower()[:3])
    if not month:
        return None
    try:
        return date(int(year_s), month, int(day_s))
    except ValueError:
        return None


def extract_calendar_left(text: str, base_year: int) -> date | None:
    forecast = re.search(r"\bforecast\b", text, re.IGNORECASE)
    region = text[forecast.start():] if forecast else text
    candidates: list[date] = []
    for m in RE_CAL_COLUMN.finditer(region):
        _, day_s, month_s = m.groups()
        month = MONTH_NUMS.get(month_s.lower()[:3])
        if not month:
            continue
        try:
            candidates.append(date(base_year, month, int(day_s)))
        except ValueError:
            continue
    return min(candidates) if candidates else None


def fmt_date(d: date | None) -> str:
    return d.strftime("%a %d %b %Y") if d else "—"


def main() -> int:
    load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1, help="Files to check (default: 1)")
    parser.add_argument("--links", action="store_true", help="Print the Drive web link for each file")
    parser.add_argument(
        "--max-age-hours", type=float,
        help="Fail if the newest upload is older than this (catches a run that never happened)",
    )
    parser.add_argument(
        "--location", choices=[l.slug for l in LOCATIONS],
        help="Check this location's folder instead of GOOGLE_DRIVE_FOLDER_ID",
    )
    args = parser.parse_args()

    folder_env = get_location(args.location).folder_env if args.location else "GOOGLE_DRIVE_FOLDER_ID"
    folder_id = os.environ.get(folder_env)
    if not folder_id:
        print(f"⚠️  {folder_env} not set. Put it in {ENV_FILE} or export it.")
        return 2

    try:
        key_file = resolve_key_file()
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return 2

    title = f" — {get_location(args.location).name}" if args.location else ""
    print(f"Verify latest Drive uploads{title} — not stale-cached?")
    print("=" * 64)

    credentials = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=credentials)

    # Fetch one extra file so the oldest checked upload has a predecessor
    # for the md5 comparison.
    resp = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, size, md5Checksum, createdTime, webViewLink)",
        orderBy="createdTime desc",
        pageSize=args.count + 1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    listed = resp.get("files", [])
    files = listed[:args.count]
    if not files:
        print("⚠️  No files found in Drive folder.")
        return 1

    all_fresh = True
    if args.max_age_hours is not None:
        newest = datetime.fromisoformat(files[0]["createdTime"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
        if age_hours > args.max_age_hours:
            print(f"❌ MISSING — newest upload is {age_hours:.1f}h old (limit {args.max_age_hours:g}h)")
            all_fresh = False

    for i, f in enumerate(files, 1):
        print()
        print(f"{i}. {f['name']}")

        created_dt = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00"))
        created_date_utc = created_dt.astimezone(timezone.utc).date()
        print(f"   Uploaded:    {created_dt.astimezone().strftime('%a %d %b %Y %H:%M %Z')}")
        if args.links:
            print(f"   Link:        {f.get('webViewLink', '—')}")

        if int(f.get("size", 0)) == 0:
            print("   Verdict:     ❌ EMPTY — 0-byte file, upload failed")
            all_fresh = False
            continue

        prev = listed[i] if i < len(listed) else None
        if prev and f.get("md5Checksum") and f.get("md5Checksum") == prev.get("md5Checksum"):
            print(f"   Verdict:     ❌ DUPLICATE — byte-identical to {prev['name']} (cache hit)")
            all_fresh = False
            continue

        buf = io.BytesIO()
        request = drive.files().get_media(fileId=f["id"], supportsAllDrives=True)
        downloader = MediaIoBaseDownload(buf, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)

        try:
            img = Image.open(buf)
        except UnidentifiedImageError:
            print(f"   Verdict:     ❌ NOT_AN_IMAGE — {f.get('size')} bytes, unreadable")
            all_fresh = False
            continue
        region = img.crop((0, 0, img.width, min(1000, img.height)))
        text = pytesseract.image_to_string(region)

        updated_at = extract_updated_at(text)
        cal_left = extract_calendar_left(text, created_date_utc.year)
        print(f"   Updated-at:  {fmt_date(updated_at)}")
        print(f"   Cal-left:    {fmt_date(cal_left)}")

        if updated_at is None:
            print("   Verdict:     ❓ OCR_FAILED — couldn't read 'Last updated' from image")
            all_fresh = False
            continue

        # EC's last forecast issuance is often the previous evening, so a
        # 0- or 1-day lag from upload date is normal. Anything bigger is
        # the stale-cache bug.
        lag = (created_date_utc - updated_at).days
        if lag <= 1:
            print(f"   Verdict:     ✅ Fresh (lag {lag} day{'s' if lag != 1 else ''})")
        else:
            print(f"   Verdict:     ❌ STALE — {lag} days behind upload date")
            all_fresh = False

    print()
    print("=" * 64)
    if all_fresh:
        print("✅ All checked uploads are fresh. Cache-bust is holding.")
        return 0
    else:
        print("❌ At least one upload is missing, stale, duplicate, empty or unreadable. If STALE or")
        print("   DUPLICATE, the cache-bust may be regressing — run `poetry run python diagnose_cache.py`.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
