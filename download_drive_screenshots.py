#!/usr/bin/env python3
"""
Download every file from the Google Drive folder that the Render instance
uploads to (GOOGLE_DRIVE_FOLDER_ID) into a local directory. Used for
side-by-side comparison with the raspi4's local-only backup.

Re-runs are incremental: a file already present at dest/<name> is skipped.
"""

import argparse
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_DEST = "drive_screenshots"
KEY_GLOB = "daily-screenshot-443720-*.json"


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE per line. Existing env vars are not overwritten."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def resolve_key_file(repo_root: Path, override: str | None) -> Path:
    if override:
        path = Path(override)
        if not path.exists():
            raise FileNotFoundError(f"--key-file not found: {path}")
        return path

    matches = sorted(repo_root.glob(KEY_GLOB))
    if not matches:
        raise FileNotFoundError(
            f"No service-account key found ({KEY_GLOB}). "
            "Download a fresh key from the GCP service-accounts console — see README."
        )
    if len(matches) > 1:
        print(f"⚠️  Multiple key files found; using newest: {matches[-1].name}")
    return matches[-1]


def list_drive_files(drive, folder_id: str) -> list[dict]:
    files: list[dict] = []
    page_token: str | None = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def resolve_names(files: list[dict]) -> tuple[list[tuple[str, dict]], int]:
    """
    Drive permits duplicate names. Disambiguate by appending `_<first-6-of-id>`
    to all-but-the-first occurrence. Returns (resolved, duplicates_renamed).
    """
    seen: dict[str, int] = {}
    resolved: list[tuple[str, dict]] = []
    renamed = 0
    for f in sorted(files, key=lambda x: (x["name"], x["id"])):
        name = f["name"]
        count = seen.get(name, 0)
        if count == 0:
            resolved.append((name, f))
        else:
            stem, dot, ext = name.rpartition(".")
            suffix = f["id"][:6]
            new_name = f"{stem}_{suffix}.{ext}" if dot else f"{name}_{suffix}"
            resolved.append((new_name, f))
            renamed += 1
        seen[name] = count + 1
    return resolved, renamed


def download_file(drive, file_id: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(tmp, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    tmp.rename(dest)


def human_size(n: int | None) -> str:
    if n is None:
        return "?"
    n = int(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env")

    parser = argparse.ArgumentParser(
        description="Download all files from a Google Drive folder for local comparison."
    )
    parser.add_argument(
        "--folder-id",
        default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID"),
        help="Drive folder ID (default: env GOOGLE_DRIVE_FOLDER_ID)",
    )
    parser.add_argument(
        "--key-file",
        default=None,
        help=f"Service-account JSON path (default: auto-detect via {KEY_GLOB})",
    )
    parser.add_argument(
        "--dest",
        default=DEFAULT_DEST,
        help=f"Local destination directory (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be downloaded without writing anything",
    )

    args = parser.parse_args()

    print("Drive Screenshot Download")
    print("=" * 50)

    if not args.folder_id:
        print("⚠️  GOOGLE_DRIVE_FOLDER_ID is not set. Export it or pass --folder-id.")
        return 2

    try:
        key_file = resolve_key_file(repo_root, args.key_file)
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return 2

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Folder ID: {args.folder_id}")
    print(f"🔍 Key file:  {key_file.name}")
    print(f"🔍 Dest:      {dest}/")
    if args.dry_run:
        print("🔍 DRY RUN — no files will be written")
    print("=" * 50)

    credentials = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=credentials)

    files = list_drive_files(drive, args.folder_id)
    resolved, duplicates_renamed = resolve_names(files)

    downloaded = 0
    skipped = 0

    for name, f in resolved:
        target = dest / name
        size_str = human_size(f.get("size"))

        if target.exists():
            skipped += 1
            continue

        if args.dry_run:
            print(f"  would download: {name} ({size_str})")
            downloaded += 1
            continue

        print(f"  ↓ {name} ({size_str})")
        download_file(drive, f["id"], target)
        downloaded += 1

    print("=" * 50)
    print(f"Total in Drive folder: {len(files)}")
    print(f"  {'Would download' if args.dry_run else 'Downloaded'}: {downloaded}")
    print(f"  Skipped (already local): {skipped}")
    print(f"  Duplicate names renamed: {duplicates_renamed}")
    print("✅ Done." if not args.dry_run else "✅ Dry run complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
