import json
import os
import tempfile
from datetime import datetime

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

THUM_AUTH = os.environ["THUM_AUTH"]
GOOGLE_DRIVE_FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

SCREENSHOT_URL = "https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702"


def take_screenshot(url: str, save_path: str):
    """Download a full-page screenshot from thum.io."""
    request_url = f"https://image.thum.io/get/auth/{THUM_AUTH}/fullpage/width/1200/{url}"
    response = requests.get(request_url)
    response.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(response.content)
    print(f"Screenshot saved to {save_path}")


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


def main():
    current_date = datetime.now().strftime("%b_%-d_%Y")
    filename = f"weather_daily_{current_date}.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, filename)
        take_screenshot(SCREENSHOT_URL, save_path)
        upload_to_google_drive(save_path, filename, GOOGLE_DRIVE_FOLDER_ID)

    print("Done.")


if __name__ == "__main__":
    main()
