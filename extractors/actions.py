#!/usr/bin/env python3
# actions.py

import sys
import os
import yaml
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
import pandas as pd
import time
from datetime import datetime

# Ensure parent directory is on sys.path for local package imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from extractors.utils import make_id
from extractors.utils import write_daily_csv
from export.google_sheets import upload_df_to_daily_gsheet_named

# Map CLI env to env tag
ENV_TAG_MAP = {
    "staging": "api",
    "dev": "beta",
    "migration": "migration",
}

# Load configuration from a YAML file
def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config/settings.yaml")
    print(f"Loading config from: {config_path}")
    with open(config_path, "r") as file:
        return yaml.safe_load(file)

CONFIG = load_config()

# Initialize WebDriver
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    return driver

def safe_click(driver, el, retries=3):
    """Wait until clickable; if intercepted, brief pause + JS click fallback."""
    for _ in range(retries):
        try:
            # ensure it’s visible & enabled first
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(el))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.click()
            return
        except ElementClickInterceptedException:
            time.sleep(0.7)
            try:
                driver.execute_script("arguments[0].click();", el)
                return
            except Exception:
                time.sleep(0.3)
        except Exception:
            time.sleep(0.3)
    # last resort
    driver.execute_script("arguments[0].click();", el)

# Function to extract actions from a page
def extract_actions(driver, url, date_range, xpaths):
    actions_data = []

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpaths["actions_buttons"])))
    action_buttons = driver.find_elements(By.XPATH, xpaths["actions_buttons"])

    for button in action_buttons:
        try:
            strategy_text = button.find_element(By.XPATH, "./span[1]").text.strip()
            strategy = strategy_text + " (action)"
        except:
            strategy = "N/A"

        try:
            value_text = button.find_element(By.XPATH, "./span[2]").text.strip().replace(",", "")  # Remove thousands separator
            value = value_text if value_text.replace(",", "").isdigit() else "N/A"
        except:
            value = "N/A"

        collection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Human-readable timestamp
        page_url = driver.current_url  # Capture current page URL
        row = {
            "range": date_range,
            "figure": strategy,
            "value": value,
            "url": page_url,
            "collection_time": collection_time,
        }
        row["id"] = make_id(row["range"], row["figure"], "actions", row["url"])
        actions_data.append(row)
    return actions_data

# Main function to process all URLs
def scrape_actions(env):
    driver = get_driver()
    all_actions = []
    xpaths = CONFIG["xpaths"]
    urls = CONFIG.get("actions_urls", {}).get(env, [])

    for url in urls:
        print(f"Scraping: {url}")
        driver.get(url)
        time.sleep(CONFIG["delays"]["page_load"])

        year_buttons = driver.find_elements(By.XPATH, xpaths["year_buttons"])
        if len(year_buttons) < 2:
            print("Skipping due to missing year buttons")
            continue

        # Extract actions for each date range
        for i, button in enumerate(year_buttons[:2]):
            safe_click(driver, button)
            time.sleep(CONFIG["delays"]["data_load"])
            date_range = button.text.strip()
            all_actions.extend(extract_actions(driver, url, date_range, xpaths))

        try:
            all_time_button = driver.find_element(By.XPATH, xpaths["all_time_button"])
            safe_click(driver, all_time_button)
            time.sleep(CONFIG["delays"]["data_load"])
            date_range = all_time_button.text.strip()
            all_actions.extend(extract_actions(driver, url, date_range, xpaths))
        except:
            print("No all-time button found.")

    driver.quit()
    return all_actions

# Run the scraper and export to CSV
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev", "migration"], required=True, help="Specify environment: staging, dev, migration")
    args = parser.parse_args()

    actions_data = scrape_actions(args.env)
    df = pd.DataFrame(actions_data)
    df = df[["range", "figure", "value", "url", "collection_time", "id"]]

    # Generate one Google Sheet per day, named {envTag}_{section}_parsed_data__YYYY-MM-DD
    # Read creds + per-env Drive folder ID from config
    creds_path = CONFIG["google_sheets"]["creds_file"]
    folder_id  = CONFIG["google_sheets"]["folder_id"]

    # Map CLI env to env tag
    env_tag = ENV_TAG_MAP[args.env]
    write_daily_csv(df=df, env_tag=env_tag, section="actions", out_dir="snapshots", tz="Europe/London")

    upload_df_to_daily_gsheet_named(
        df=df,
        env_tag=env_tag,
        section="actions",
        folder_id=folder_id,
        creds_path=creds_path,
        tz="Europe/London",
    )

if __name__ == "__main__":
    main()
