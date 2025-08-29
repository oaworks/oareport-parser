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
from extractors.utils import make_id

# Allow import from parent directory for Google Sheets export
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from export.google_sheets import upload_df_to_gsheet

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
            value_text = button.find_element(By.XPATH, "./span[2]").text.strip().replace(",", "") # Remove thousands separator
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
            button.click()
            time.sleep(CONFIG["delays"]["data_load"])
            date_range = button.text.strip()
            all_actions.extend(extract_actions(driver, url, date_range, xpaths))
        
        try:
            all_time_button = driver.find_element(By.XPATH, xpaths["all_time_button"])
            all_time_button.click()
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
    parser.add_argument("--env", choices=["staging", "dev"], required=True, help="Specify environment: staging or dev")
    args = parser.parse_args()

    actions_data = scrape_actions(args.env)
    output_file = f"actions_{args.env}_data.csv"
    df = pd.DataFrame(actions_data)
    df = df[["range", "figure", "value", "url", "collection_time", "id"]]
    df.to_csv(output_file, index=False)
    print(f"Data saved to {output_file}")

    # Upload to Google Sheets
    spreadsheet_name = CONFIG["google_sheets"]["sheets"]["actions"][args.env]
    creds_path = CONFIG["google_sheets"]["creds_file"]

    upload_df_to_gsheet(
        df=df,
        spreadsheet_name=spreadsheet_name,
        creds_path=creds_path
    )

if __name__ == "__main__":
    main()
