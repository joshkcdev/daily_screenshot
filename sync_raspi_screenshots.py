#!/usr/bin/env python3
"""
Pull screenshots from the raspi4 backup instance to a local directory via rsync.

The raspi4 runs a parallel copy of daily_screenshot and saves PNGs to
~/workspace/daily_screenshot/screenshots. This utility mirrors that directory
into ./screenshots/ on the local machine for side-by-side comparison with the
Render instance's Google Drive output.

Incremental: only new/changed files transfer. Never deletes local files.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_HOST = "raspi4"
DEFAULT_REMOTE_DIR = "~/workspace/daily_screenshot/screenshots"
DEFAULT_DEST = "raspi_screenshots"


def sync(host: str, remote_dir: str, dest: Path, dry_run: bool) -> int:
    if shutil.which("rsync") is None:
        print("⚠️  rsync not found on PATH. Install it (e.g. `brew install rsync`).")
        return 127

    dest.mkdir(parents=True, exist_ok=True)

    remote = f"{host}:{remote_dir.rstrip('/')}/"
    local = f"{dest}/"

    cmd = [
        "rsync",
        "-avzh",
        "--partial",
        "--progress",
        "--stats",
        "-e", "ssh",
    ]
    if dry_run:
        cmd.append("-n")
    cmd.extend([remote, local])

    print(f"🔍 {'Dry run: ' if dry_run else ''}syncing {remote} → {local}")
    print(f"   Command: {' '.join(cmd)}")
    print("=" * 50)

    result = subprocess.run(cmd, check=False)

    print("=" * 50)
    if result.returncode == 0:
        print(f"✅ {'Dry run complete' if dry_run else 'Sync complete'}.")
    else:
        print(f"⚠️  rsync exited with code {result.returncode}.")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror raspi4 screenshots to a local directory via rsync over SSH."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("RPI_SSH_HOST", DEFAULT_HOST),
        help=f"SSH host or ~/.ssh/config alias (default: {DEFAULT_HOST}, env: RPI_SSH_HOST)",
    )
    parser.add_argument(
        "--remote-dir",
        default=os.environ.get("RPI_REMOTE_DIR", DEFAULT_REMOTE_DIR),
        help=f"Remote screenshots directory (default: {DEFAULT_REMOTE_DIR}, env: RPI_REMOTE_DIR)",
    )
    parser.add_argument(
        "--dest",
        default=DEFAULT_DEST,
        help=f"Local destination directory (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would transfer without copying anything",
    )

    args = parser.parse_args()

    print("Raspi4 Screenshot Sync")
    print("=" * 50)

    return sync(
        host=args.host,
        remote_dir=args.remote_dir,
        dest=Path(args.dest),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
