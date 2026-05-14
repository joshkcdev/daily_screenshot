#!/usr/bin/env python3
"""
Check the last N screenshots in raspi_screenshots/ and drive_screenshots/ for
thum.io cache incoherence: extract the "Last updated …" date and the leftmost
column of the forecast calendar via OCR, then flag any image where the two
disagree.

The two regions of interest live in the rendered Environment Canada weather
page (1200px wide). Both should report the same date when the cache is fresh.
"""

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytesseract
from PIL import Image


MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

WEEKDAYS = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

# "Last updated … Wed 1 Oct 2025" or "… Wednesday 1 October 2025"
RE_UPDATED_AT = re.compile(
    rf"Last\s+updated.*?\b({WEEKDAYS})[a-z]*\s+(\d{{1,2}})\s+({MONTHS})[a-z]*\s+(\d{{4}})",
    re.IGNORECASE | re.DOTALL,
)

# Calendar header column: "Wed\n1 Oct" or "Wed 1 Oct"
RE_CAL_COLUMN = re.compile(
    rf"\b({WEEKDAYS})[a-z]*[\s,]*\n?[\s,]*(\d{{1,2}})\s+({MONTHS})",
    re.IGNORECASE,
)


@dataclass
class Row:
    filename: str
    filename_date: date | None
    updated_at: date | None
    calendar_left: date | None
    status: str  # "OK" | "STALE" | "MISMATCH" | "OCR_FAILED"


def parse_capture_date(name: str) -> date | None:
    # ISO with optional time: weather_daily_2026-05-14_... or weather_daily_2026_05_14_...
    m = re.search(r"weather_daily_(\d{4})[-_](\d{2})[-_](\d{2})", name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # Human-readable: weather_daily_May 14 2026.jpg / May_14_2026 / May 14, 2026 / may_14_2026
    m = re.search(
        r"weather_daily_([A-Za-z]+)[_ ](\d{1,2}),?[_ ](\d{4})",
        name,
    )
    if m:
        month_name = m.group(1).lower()
        month = MONTH_NAMES.get(month_name) or MONTH_NAMES.get(month_name[:3])
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None

    return None


def ocr_text(img: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(img)
    except Exception as e:
        print(f"  ⚠️  OCR error: {e}")
        return ""


def extract_updated_at(text: str) -> date | None:
    m = RE_UPDATED_AT.search(text)
    if not m:
        return None
    weekday, day_s, month_s, year_s = m.groups()
    month = MONTH_NAMES.get(month_s.lower()[:3])
    if not month:
        return None
    try:
        return date(int(year_s), month, int(day_s))
    except ValueError:
        return None


def extract_calendar_left(text: str, filename_date: date | None) -> date | None:
    """Earliest weekday/day/month triple after 'Forecast' — the calendar goes
    forward in time, so the leftmost column is the chronologically smallest.

    Picking by chronology (rather than position in OCR text) is robust to
    Tesseract reading columns out of order, which happens with this layout.
    """
    # Match "Forecast" as a whole word — the breadcrumb "Local forecasts >"
    # appears earlier in the page and would otherwise be picked up first,
    # which pulls in the Current Conditions "Monday 11 May 2026" line.
    forecast_match = re.search(r"\bforecast\b", text, re.IGNORECASE)
    search_region = text[forecast_match.start():] if forecast_match else text

    base_year = filename_date.year if filename_date else date.today().year
    candidates: list[date] = []
    for m in RE_CAL_COLUMN.finditer(search_region):
        _, day_s, month_s = m.groups()
        month = MONTH_NAMES.get(month_s.lower()[:3])
        if not month:
            continue
        day = int(day_s)
        year = base_year
        # Year wraparound: filename Jan + calendar Dec → previous year; vice versa.
        if filename_date and filename_date.month == 1 and month == 12:
            year -= 1
        elif filename_date and filename_date.month == 12 and month == 1:
            year += 1
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue

    if not candidates:
        return None
    return min(candidates)


def classify(row_filename_date, updated_at, calendar_left) -> str:
    if updated_at is None or calendar_left is None:
        return "OCR_FAILED"
    # The calendar's first column is either updated-at or updated-at + 1 day,
    # depending on time of day / forecast issue. Larger gaps mean the page is
    # internally inconsistent (the bug we're hunting).
    delta = abs((calendar_left - updated_at).days)
    if delta > 1:
        return "MISMATCH"
    if row_filename_date and updated_at != row_filename_date:
        return "STALE"
    return "OK"


def process_image(path: Path) -> Row:
    filename_date = parse_capture_date(path.name)

    try:
        img = Image.open(path)
    except Exception as e:
        print(f"  ⚠️  Cannot open {path.name}: {e}")
        return Row(path.name, filename_date, None, None, "OCR_FAILED")

    # Single crop covering the Gov't of Canada banner, "Last updated" stamp,
    # and the forecast calendar row. The actual page height is ~3000px; the
    # first ~1000px is enough for both regions on every layout we've seen.
    region = img.crop((0, 0, img.width, min(1000, img.height)))
    text = ocr_text(region)
    updated_at = extract_updated_at(text)
    cal_left = extract_calendar_left(text, filename_date)

    status = classify(filename_date, updated_at, cal_left)
    return Row(path.name, filename_date, updated_at, cal_left, status)


def collect_recent(dir_path: Path, count: int) -> list[Path]:
    if not dir_path.exists():
        print(f"⚠️  Directory not found: {dir_path}")
        return []

    pairs: list[tuple[date, Path]] = []
    unparseable = 0
    for p in dir_path.iterdir():
        if p.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        d = parse_capture_date(p.name)
        if d is None:
            unparseable += 1
            continue
        pairs.append((d, p))

    if unparseable:
        print(f"  (skipped {unparseable} file(s) with unparseable names in {dir_path.name})")

    pairs.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in pairs[:count]]


def fmt_date(d: date | None) -> str:
    return d.strftime("%b %-d %Y") if d else "—"


STATUS_ICONS = {
    "OK": "✅",
    "STALE": "⚠️ ",
    "MISMATCH": "❌",
    "OCR_FAILED": "❓",
}

STATUS_LABELS = {
    "OK": "OK",
    "STALE": "stale-but-coherent",
    "MISMATCH": "MISMATCH",
    "OCR_FAILED": "OCR_FAILED",
}


def print_table(label: str, rows: list[Row]) -> dict[str, int]:
    print()
    print(f"{label} — {len(rows)} file(s)")
    print("═" * 110)
    header = f"{'file':<46} {'filename':<14} {'updated-at':<14} {'cal-left':<14} status"
    print(header)
    print("─" * 110)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
        icon = STATUS_ICONS[r.status]
        label_s = STATUS_LABELS[r.status]
        print(
            f"{r.filename[:45]:<46} "
            f"{fmt_date(r.filename_date):<14} "
            f"{fmt_date(r.updated_at):<14} "
            f"{fmt_date(r.calendar_left):<14} "
            f"{icon} {label_s}"
        )

    summary = "  ".join(f"{STATUS_ICONS[s]} {STATUS_LABELS[s]}: {n}" for s, n in counts.items())
    print("─" * 110)
    print(f"Summary: {summary}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare 'Last updated' vs first calendar column in recent screenshots."
    )
    parser.add_argument("--count", type=int, default=30, help="Files per directory (default: 30)")
    parser.add_argument("--raspi-dir", default="raspi_screenshots")
    parser.add_argument("--drive-dir", default="drive_screenshots")
    args = parser.parse_args()

    print("Cache Coherence Check")
    print("=" * 110)

    if shutil.which("tesseract") is None:
        print("⚠️  tesseract not found. Install with: brew install tesseract")
        return 2

    for label, dir_arg in [("raspi_screenshots/", args.raspi_dir), ("drive_screenshots/", args.drive_dir)]:
        dir_path = Path(dir_arg)
        files = collect_recent(dir_path, args.count)
        if not files:
            print(f"\n{label} — no files")
            continue
        rows = [process_image(f) for f in files]
        print_table(label, rows)

    return 0


if __name__ == "__main__":
    sys.exit(main())
