#!/usr/bin/env python3
# insights.py

import sys
import os
import yaml
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from datetime import datetime

# Ensure parent directory is on sys.path for local package imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from extractors.utils import make_id
from export.google_sheets import upload_df_to_daily_gsheet_named

# Map CLI env to env tag
ENV_TAG_MAP = {
    "staging": "api",
    "dev": "beta",
    "migration": "migration"
}

# Load configuration from a YAML file
def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config/settings.yaml")
    print(f"Loading config from: {config_path}")
    with open(config_path, "r") as file:
        return yaml.safe_load(file)

CONFIG = load_config()

# Initialise WebDriver
def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    return driver

# Function to extract insights from a page
def extract_insights(driver, url, date_range, xpaths):
    insights_data = []
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpaths["insights_cards"])))
    articles = driver.find_elements(By.XPATH, xpaths["insights_cards"])

    for article in articles:
        try:
            insight_name = article.find_element(By.XPATH, xpaths["insight_name"]).text.strip() + " (insight)"
        except:
            insight_name = "N/A"

        try:
            value_element = article.find_element(
                By.XPATH,
                ".//span[contains(@id, 'percent_') or contains(@id, 'articles_')] | " + xpaths["value"],
            )
            value = value_element.text.strip() if value_element.text.strip() else "N/A"
        except:
            value = "N/A"

        collection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Human-readable timestamp
        page_url = driver.current_url  # Capture current page URL

        row = {
            "range": date_range,
            "figure": insight_name,
            "value": value,
            "url": page_url,
            "collection_time": collection_time,
        }
        row["id"] = make_id(row["range"], row["figure"], "insights", row["url"])
        insights_data.append(row)

    return insights_data

# Main function to process all URLs
def scrape_insights(env):
    driver = get_driver()
    all_insights = []
    xpaths = CONFIG["xpaths"]
    urls = CONFIG.get("insights_urls", {}).get(env, [])

    for url in urls:
        print(f"Scraping: {url}")
        driver.get(url)
        time.sleep(CONFIG["delays"]["page_load"])

        year_buttons = driver.find_elements(By.XPATH, xpaths["year_buttons"])

        if len(year_buttons) >= 2:
            # Extract insights for each date range
            for i, button in enumerate(year_buttons[:2]):
                button.click()
                time.sleep(CONFIG["delays"]["data_load"])
                date_range = button.text.strip()
                all_insights.extend(extract_insights(driver, url, date_range, xpaths))

            try:
                all_time_button = driver.find_element(By.XPATH, xpaths["all_time_button"])
                all_time_button.click()
                time.sleep(CONFIG["delays"]["data_load"])
                date_range = all_time_button.text.strip()
                all_insights.extend(extract_insights(driver, url, date_range, xpaths))
            except:
                print("No all-time button found.")
        else:
            print("No year buttons found, extracting without date_range")
            all_insights.extend(extract_insights(driver, url, "", xpaths))

    driver.quit()
    return all_insights

# Run the scraper and export
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev"], required=True, help="Specify environment: staging or dev")
    args = parser.parse_args()

    insights_data = scrape_insights(args.env)
    df = pd.DataFrame(insights_data)
    df = df[["range", "figure", "value", "url", "collection_time", "id"]]

    print(f"Scraped {len(insights_data)} rows total.")

    # Write a local CSV
    output_file = f"insights_{args.env}_data.csv"
    df.to_csv(output_file, index=False)
    print(f"Data saved to {output_file}")

    # Generate one Google Sheet per day, named {envTag}_{section}_parsed_data__YYYY-MM-DD
    # Read creds + per-env Drive folder ID from config
    creds_file = CONFIG["google_sheets"]["creds_file"]
    folder_id = CONFIG["google_sheets"]["folder_id"]

    # Map CLI env to env tag
    env_tag = ENV_TAG_MAP[args.env]

    # Create/overwrite the daily sheet inside the folder (Europe/London day)
    upload_df_to_daily_gsheet_named(
        df=df,
        env_tag=env_tag,
        section="insights",
        folder_id=folder_id,
        creds_path=creds_file,
        tz="Europe/London",
    )

if __name__ == "__main__":
    main()