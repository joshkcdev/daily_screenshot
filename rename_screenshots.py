#!/usr/bin/env python3
"""
Script to rename screenshot files to use only lowercase and underscores.
Converts: weather_daily_2024-12-11_12-00-01_AM.png
To: weather_daily_2024_december_11.png
"""

import os
import re
from pathlib import Path


def rename_screenshots(screenshots_dir: str = "screenshots", dry_run: bool = True):
    """
    Rename screenshot files to use lowercase and underscores only.
    Also replaces month numbers with month names.

    Args:
        screenshots_dir: Directory containing the screenshots
        dry_run: If True, only print what would be renamed without actually renaming
    """
    # Month number to name mapping
    MONTHS = {
        '01': 'january',
        '02': 'february',
        '03': 'march',
        '04': 'april',
        '05': 'may',
        '06': 'june',
        '07': 'july',
        '08': 'august',
        '09': 'september',
        '10': 'october',
        '11': 'november',
        '12': 'december'
    }

    screenshots_path = Path(screenshots_dir)

    if not screenshots_path.exists():
        print(f"Error: Directory '{screenshots_dir}' does not exist")
        return

    # Get all PNG files in the directory
    files = list(screenshots_path.glob("*.png"))

    if not files:
        print(f"No PNG files found in '{screenshots_dir}'")
        return

    renamed_count = 0
    skipped_count = 0

    for file_path in sorted(files):
        old_name = file_path.name

        # Convert to lowercase and replace hyphens with underscores
        new_name = old_name.lower().replace("-", "_")

        # Replace month number with month name
        # Pattern: weather_daily_YYYY_MM_DD... or weather_daily_YYYY-MM-DD...
        pattern = r'(weather_daily_\d{4}[_-])(\d{2})([_-])'
        match = re.search(pattern, new_name)

        if match:
            month_num = match.group(2)
            if month_num in MONTHS:
                month_name = MONTHS[month_num]
                new_name = re.sub(pattern, rf'\g<1>{month_name}\g<3>', new_name)

        # Remove time portion (everything after the day number until .png)
        # Pattern: weather_daily_YYYY_MONTHNAME_DD_HH_MM_SS_am/pm.png
        time_pattern = r'(weather_daily_\d{4}_[a-z]+_\d{2})(_\d{2}_\d{2}_\d{2}_[ap]m)(\.png)$'
        new_name = re.sub(time_pattern, r'\1\3', new_name)

        # Skip if the name doesn't need to change
        if old_name == new_name:
            skipped_count += 1
            continue

        new_path = file_path.parent / new_name

        # Check if target file already exists
        if new_path.exists():
            print(f"⚠️  Skipping '{old_name}': target '{new_name}' already exists")
            skipped_count += 1
            continue

        if dry_run:
            print(f"Would rename: {old_name} → {new_name}")
        else:
            file_path.rename(new_path)
            print(f"Renamed: {old_name} → {new_name}")

        renamed_count += 1

    print(f"\n{'Dry run ' if dry_run else ''}Summary:")
    print(f"  Total files: {len(files)}")
    print(f"  {'Would rename' if dry_run else 'Renamed'}: {renamed_count}")
    print(f"  Skipped: {skipped_count}")

    if dry_run and renamed_count > 0:
        print(f"\nTo actually rename the files, run with dry_run=False")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Rename screenshot files to use lowercase and underscores only"
    )
    parser.add_argument(
        "--dir",
        default="screenshots",
        help="Directory containing screenshots (default: screenshots)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files (default is dry-run mode)"
    )

    args = parser.parse_args()

    print("Screenshot Renaming Script")
    print("=" * 50)
    if not args.execute:
        print("🔍 DRY RUN MODE - No files will be renamed")
        print("   Use --execute flag to actually rename files")
        print("=" * 50)

    rename_screenshots(args.dir, dry_run=not args.execute)
