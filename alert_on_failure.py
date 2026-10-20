#!/usr/bin/env python3
"""
Run verify_latest_drive.py and email its output via Resend if it fails.

Runs nightly on raspi4, independent of Render, so it also catches a Render
run that never happened. Any extra arguments are passed to the verifier.

Env: RESEND_API_KEY, ALERT_EMAIL_FROM, ALERT_EMAIL_TO (plus the verifier's
GOOGLE_DRIVE_FOLDER_ID and service-account key).
"""

import html
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen


VERIFIER = Path(__file__).with_name("verify_latest_drive.py")


def send_email(subject: str, output: str) -> None:
    body = {
        "from": os.environ["ALERT_EMAIL_FROM"],
        "to": [os.environ["ALERT_EMAIL_TO"]],
        "subject": subject,
        "html": (
            "<p>The nightly Daily Screenshot check on raspi4 failed.</p>"
            f"<pre style='font-size:13px'>{html.escape(output)}</pre>"
        ),
    }
    request = Request(
        "https://api.resend.com/emails",
        method="POST",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "DailyScreenshot-RaspberryPi/1.0",
        },
    )
    with urlopen(request, timeout=60) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Resend returned HTTP {response.status}")


def main() -> int:
    result = subprocess.run(
        [sys.executable, str(VERIFIER), *sys.argv[1:]],
        capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    print(output, end="")

    if result.returncode != 0:
        send_email(f"Daily Screenshot check failed (exit {result.returncode})", output)
        print("Alert email sent.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
