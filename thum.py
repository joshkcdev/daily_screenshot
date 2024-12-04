import requests
import os
from datetime import datetime

current_datetime = datetime.now().strftime('%Y-%m-%d_%I-%M-%S_%p')

def ensure_directory_exists(directory: str):
    """Creates the directory if it does not exist."""
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_image(url: str, save_path: str):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Check for HTTP errors

        with open(save_path, 'wb') as file:
            file.write(response.content)

        print(f"Image successfully downloaded and saved to {save_path}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

screenshot_dir = "~/workspace/daily_screenshot/screenshots"
ensure_directory_exists(screenshot_dir)
screenshot_url = "https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702"
request_url = f"https://image.thum.io/get/auth/72878-weather_daily/fullpage/width/1200{screenshot_url}"
filename = f"{screenshot_dir}/screenshot_{current_datetime}.png"
download_image(request_url, filename)
