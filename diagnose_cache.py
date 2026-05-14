#!/usr/bin/env python3
"""
Diagnose where the stale-cache problem lives: at thum.io or upstream at
Environment Canada.

Fetches the EC weather page's raw HTML and a fresh thum.io capture at the
same moment, extracts the "Last updated …" date from each, and compares.

- If raw HTML is fresh but thum.io shows an older date → thum.io is caching.
- If both show the same older date → upstream (EC / their CDN) is stale, and
  no thum.io trick will help.
"""

import os
import re
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import pytesseract
import requests
from PIL import Image


SCREENSHOT_URL = "https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702"

WEEKDAYS = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

RE_UPDATED_AT = re.compile(
    rf"Last\s+updated.*?\b({WEEKDAYS})[a-z]*\s+(\d{{1,2}})\s+({MONTHS})[a-z]*\s+(\d{{4}})",
    re.IGNORECASE | re.DOTALL,
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


def extract_updated_at(text: str) -> tuple[date, str] | None:
    m = RE_UPDATED_AT.search(text)
    if not m:
        return None
    weekday, day_s, month_s, year_s = m.groups()
    month = MONTH_NUMS.get(month_s.lower()[:3])
    if not month:
        return None
    try:
        d = date(int(year_s), month, int(day_s))
    except ValueError:
        return None
    return d, m.group(0).strip()


def fetch_ec_html() -> str:
    r = requests.get(SCREENSHOT_URL, timeout=30, headers={
        "User-Agent": "diagnose_cache.py (daily_screenshot project)",
        "Cache-Control": "no-cache",
    })
    r.raise_for_status()
    return r.text


def fetch_thumio(thum_auth: str) -> Path:
    # Cache-bust at the inner URL level (thum.io keys its cache off the source URL).
    ts = int(time.time())
    sep = "&" if "?" in SCREENSHOT_URL else "?"
    busted = f"{SCREENSHOT_URL}{sep}_={ts}"
    url = f"https://image.thum.io/get/auth/{thum_auth}/fullpage/width/1200/{busted}"
    print(f"   GET {url[:120]}...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    tmp = Path(tempfile.gettempdir()) / f"diagnose_thumio_{ts}.png"
    tmp.write_bytes(r.content)
    return tmp


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env")

    thum_auth = os.environ.get("THUM_AUTH")
    if not thum_auth:
        print("⚠️  THUM_AUTH not set. Add it to .env or export it.")
        return 2

    now = datetime.now()
    print("Cache diagnosis — where does the staleness live?")
    print("=" * 70)
    print(f"Local time: {now.strftime('%a %d %b %Y %H:%M:%S')}")
    print(f"Today:      {now.date().strftime('%a %d %b %Y')}")
    print()

    print("1. Raw HTML from weather.gc.ca")
    print("-" * 70)
    try:
        html = fetch_ec_html()
    except Exception as e:
        print(f"   ⚠️  Fetch failed: {e}")
        return 1
    html_info = extract_updated_at(html)
    if html_info:
        d_html, raw_html = html_info
        print(f"   Last updated: {d_html.strftime('%a %d %b %Y')}")
        print(f"   Matched:      {raw_html!r}")
    else:
        d_html = None
        print("   ⚠️  Could not find 'Last updated' in HTML")

    print()
    print("2. Fresh thum.io capture (unique nonce)")
    print("-" * 70)
    try:
        img_path = fetch_thumio(thum_auth)
    except Exception as e:
        print(f"   ⚠️  Capture failed: {e}")
        return 1
    img = Image.open(img_path)
    region = img.crop((0, 0, img.width, min(1000, img.height)))
    ocr_text = pytesseract.image_to_string(region)
    thum_info = extract_updated_at(ocr_text)
    if thum_info:
        d_thum, raw_thum = thum_info
        print(f"   Last updated: {d_thum.strftime('%a %d %b %Y')}")
        print(f"   Matched:      {raw_thum!r}")
    else:
        d_thum = None
        print("   ⚠️  Could not extract 'Last updated' from screenshot")
    print(f"   Saved to:     {img_path}")

    print()
    print("=" * 70)
    print("Diagnosis")
    print("-" * 70)

    today = now.date()
    if d_html and d_thum:
        html_lag = (today - d_html).days
        thum_lag = (today - d_thum).days
        print(f"   HTML lag:    {html_lag} day(s) behind today")
        print(f"   thum.io lag: {thum_lag} day(s) behind today")
        print()
        if d_html == d_thum:
            if html_lag == 0:
                print("   ✅ Both fresh. No cache problem right now.")
            else:
                print("   ⬆️  Both show the SAME stale date. Cache is UPSTREAM (Environment Canada / their CDN).")
                print("       thum.io tricks (noCache, maxAge, cache-bust nonce) will NOT help.")
                print("       Options: self-hosted Chromium, switch source, or accept the lag.")
        elif d_thum < d_html:
            print("   ❌ thum.io is older than the live HTML. Cache is at THUM.IO.")
            print("       Options: try `noCache` / `refreshCache` directives, or a higher `maxAge`.")
            print("       Also try cache-busting the inner URL (append `?_=<ts>` to the EC URL).")
        else:
            print("   🤔 thum.io is NEWER than the live HTML — unexpected. Re-run in a few minutes.")
    elif d_html and not d_thum:
        print("   ⚠️  Couldn't read thum.io image. Inspect manually:", img_path)
    elif d_thum and not d_html:
        print("   ⚠️  Couldn't find 'Last updated' in raw HTML. The page structure may have changed.")
    else:
        print("   ⚠️  Could not extract a date from either source.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
