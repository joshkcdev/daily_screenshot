import json
import os
import tempfile
import time
from datetime import datetime

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from locations import LOCATIONS, Location

SCOPES = ["https://www.googleapis.com/auth/drive"]

THUM_AUTH = os.environ["THUM_AUTH"]
# When set (the raspi4 backup), save screenshots to this directory and skip
# Google Drive entirely; the Drive variables are then not required.
LOCAL_SAVE_DIR = os.environ.get("LOCAL_SAVE_DIR")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

SCREENSHOT_ATTEMPTS = 3
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def take_screenshot(url: str, save_path: str):
    """Download a full-page screenshot from thum.io."""
    # thum.io keys its cache off the inner source URL, so appending a unique
    # query param to the EC URL makes each request look like a new URL and
    # forces a fresh render. The `nonce/<ts>/` segment we tried previously
    # did not bust their cache — confirmed via diagnose_cache.py.
    sep = "&" if "?" in url else "?"
    busted_url = f"{url}{sep}_={int(time.time())}"
    request_url = f"https://image.thum.io/get/auth/{THUM_AUTH}/fullpage/width/1200/{busted_url}"

    # thum.io has occasionally returned 200 with an empty body (0-byte files
    # landed in Drive on Apr 24, Apr 30 and Sep 1 2026). Retry, and never
    # hand a non-PNG to the uploader.
    for attempt in range(1, SCREENSHOT_ATTEMPTS + 1):
        response = requests.get(request_url)
        response.raise_for_status()
        if response.content.startswith(PNG_SIGNATURE):
            break
        print(
            f"Attempt {attempt}: thum.io returned {len(response.content)} bytes, "
            f"not a PNG ({response.headers.get('Content-Type')})"
        )
        if attempt < SCREENSHOT_ATTEMPTS:
            time.sleep(30 * attempt)
    else:
        raise RuntimeError(
            f"thum.io did not return a valid PNG after {SCREENSHOT_ATTEMPTS} attempts"
        )

    with open(save_path, "wb") as f:
        f.write(response.content)
    print(f"Screenshot saved to {save_path} ({len(response.content)} bytes)")


def upload_to_google_drive(file_path: str, filename: str, folder_id: str):
    """Upload a file to a Google Drive folder using a service account."""
    creds_json = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        creds_json, scopes=SCOPES
    )
    drive_service = build("drive", "v3", credentials=credentials)

    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="image/png")
    file = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    print(f"Uploaded to Google Drive with file ID: {file.get('id')}")


def capture(location: Location, current_date: str):
    filename = f"weather_{location.slug}_{current_date}.png"

    if LOCAL_SAVE_DIR:
        take_screenshot(location.url, os.path.join(LOCAL_SAVE_DIR, filename))
        return

    folder_id = os.environ[location.folder_env]
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, filename)
        take_screenshot(location.url, save_path)
        upload_to_google_drive(save_path, filename, folder_id)


def main():
    current_date = datetime.now().strftime("%Y-%m-%d")

    if LOCAL_SAVE_DIR:
        os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)
    else:
        missing = [l.folder_env for l in LOCATIONS if not os.environ.get(l.folder_env)]
        if not GOOGLE_SERVICE_ACCOUNT_JSON:
            missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
        if missing:
            raise RuntimeError(f"Set {', '.join(missing)}, or LOCAL_SAVE_DIR")

    # Capture every location even if one fails, then fail the run so Render
    # still sends its failure email.
    failed = []
    for location in LOCATIONS:
        print(f"--- {location.name}")
        try:
            capture(location, current_date)
        except Exception as e:
            print(f"{location.name} failed: {e}")
            failed.append(location.name)

    if failed:
        raise RuntimeError(f"Capture failed for: {', '.join(failed)}")
    print("Done.")


if __name__ == "__main__":
    main()
