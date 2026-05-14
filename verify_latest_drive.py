#!/usr/bin/env python3
"""
Verify the latest screenshots in the Render-uploaded Drive folder aren't
stale-cached. Run this tomorrow / the day after to confirm the inner-URL
cache-bust in thum.py held up in production.

For each of the most recent uploads it pulls the file in memory, OCRs the
top region, and compares the page's "Last updated" date with the upload
date. A delta of 0-1 day is fine (EC's last forecast issuance can be the
prior evening); anything bigger means thum.io is caching again.
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
from PIL import Image


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
KEY_GLOB = "daily-screenshot-443720-*.json"

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


def resolve_key_file(repo_root: Path) -> Path:
    matches = sorted(repo_root.glob(KEY_GLOB))
    if not matches:
        raise FileNotFoundError(f"No service-account key matching {KEY_GLOB}")
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
    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1, help="Files to check (default: 1)")
    args = parser.parse_args()

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        print("⚠️  GOOGLE_DRIVE_FOLDER_ID not set. Put it in .env or export it.")
        return 2

    try:
        key_file = resolve_key_file(repo_root)
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return 2

    print("Verify latest Drive uploads — not stale-cached?")
    print("=" * 64)

    credentials = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=credentials)

    resp = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, size, createdTime)",
        orderBy="createdTime desc",
        pageSize=args.count,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = resp.get("files", [])
    if not files:
        print("⚠️  No files found in Drive folder.")
        return 1

    all_fresh = True
    for i, f in enumerate(files, 1):
        print()
        print(f"{i}. {f['name']}")

        created_dt = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00"))
        created_date_utc = created_dt.astimezone(timezone.utc).date()
        print(f"   Uploaded:    {created_dt.astimezone().strftime('%a %d %b %Y %H:%M %Z')}")

        buf = io.BytesIO()
        request = drive.files().get_media(fileId=f["id"], supportsAllDrives=True)
        downloader = MediaIoBaseDownload(buf, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)

        img = Image.open(buf)
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
        print("❌ At least one upload is stale. Cache-bust may be regressing —")
        print("   run `poetry run python diagnose_cache.py` to investigate.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
