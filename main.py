from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)

# Path to your WebDriver executable
webdriver_path = '/opt/homebrew/bin/chromedriver'

# Set up the WebDriver
service = Service(webdriver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
    # Open the website
    driver.get('https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702')

    # Wait for the page to load completely
    time.sleep(5)  # Adjust this as necessary

    # Use JavaScript to get the full width and height of the webpage
    width = driver.execute_script("return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth);")
    height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")

    # Set the window size to match the entire webpage
    driver.set_window_size(width, height)

    # Capture the screenshot of the entire page
    driver.save_screenshot('full_page_screenshot.png')

finally:
    # Close the browser
    driver.quit()
