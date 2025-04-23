import os
import sys
import yaml
import argparse
import pandas as pd
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException   # ← added

# Allow import from parent directory for Google Sheets export
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from export.google_sheets import upload_df_to_gsheet

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config/settings.yaml")
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

def extract_table_data(driver):
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "explore_table"))
    )

    # Get headers
    header_row = driver.find_element(By.XPATH, "//table[@id='explore_table']//thead/tr")
    headers = [th.text.strip() for th in header_row.find_elements(By.TAG_NAME, "th")]

    # Get body rows
    body_rows = driver.find_elements(By.XPATH, "//table[@id='explore_table']//tbody/tr")
    data = []
    for row in body_rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        values = [cell.text.strip() for cell in cells]
        if len(values) != len(headers):
            print(f"Skipping row: {values} (expected {len(headers)} columns)")
            continue
        data.append(dict(zip(headers, values)))

    return data

def scrape_explore(env):
    urls = CONFIG.get("explore_urls", {}).get(env, [])
    xpaths = CONFIG["xpaths"]
    delay = CONFIG["delays"]
    driver = get_driver()
    all_data = []

    for url in urls:
        print(f"Scraping Explore from: {url}")
        driver.get(url)
        time.sleep(CONFIG["delays"]["page_load"]) # Wait for page to load
        
        # Click All-time button
        explore_all_time_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpaths["all_time_button"]))
        )
        driver.execute_script("arguments[0].click();", explore_all_time_button)
        WebDriverWait(driver, delay["data_load"])
        time.sleep(10)

        # Click Explore > Years button
        explore_year_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "explore_year_button"))
        )
        driver.execute_script("arguments[0].click();", explore_year_button)
        WebDriverWait(driver, delay["data_load"])
        time.sleep(5)

        # Toggle to raw numbers (if currently showing %)
        try:
            # element might be present but not yet interactable – wait for presence first
            toggle = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "toggle-data-view"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", toggle)

            # click only when it is really in % mode
            if toggle.get_attribute("aria-checked") == "true":
                driver.execute_script("arguments[0].click();", toggle)

                # wait until aria‑checked flips to "false"
                WebDriverWait(driver, 10).until(
                    lambda d: d.find_element(By.ID, "toggle-data-view")
                              .get_attribute("aria-checked") == "false"
                )
                # give the table time to re‑render
                WebDriverWait(driver, delay["data_load"])
        except Exception as e:
            print(f"[warn] could not toggle raw/percent switch on {url}: {e}")
        
        # Extract table
        try:
            table_data = extract_table_data(driver)
        except StaleElementReferenceException:
            # rare second refresh – retry once
            table_data = extract_table_data(driver)
        except Exception as e:
            print(f"Failed to extract table from {url}: {e}")
            continue

        # Pick only the last N (= years_to_keep) years
        key_col = list(table_data[0].keys())[0] if table_data else "KEY" # Grab header name of first col; default to "KEY"
        yrs_to_keep = CONFIG["explore"]["years_to_keep"]

        numeric_years = sorted(
            {int(r.get(key_col, "")) for r in table_data if r.get(key_col, "").isdigit()}
        )
        recent_years = set(numeric_years[-yrs_to_keep:]) # e.g. {2025, 2024}

        # Pivot: one metric per row
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for row in table_data:
            yr = row.get(key_col, "")
            if yr.isdigit() and int(yr) not in recent_years:
                continue    # Skip old years not in last N years

            for metric, val in row.items():
                if metric == key_col:
                    continue    # don’t treat the year column as a metric

                all_data.append({
                    "date_range"     : yr,
                    "figure"         : f"{metric} (Explore)",
                    "value"          : val,
                    "Page_URL"       : url,
                    "collection_time": ts
                })

    driver.quit()
    return pd.DataFrame(all_data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev"], required=True)
    args = parser.parse_args()

    df = scrape_explore(args.env)
    output_file = f"explore_{args.env}_data.csv"
    df.to_csv(output_file, index=False)
    print(f"Data saved to {output_file}")

    # Upload to Google Sheets
    spreadsheet_name = CONFIG["google_sheets"]["sheets"]["explore"][args.env]
    creds_file = CONFIG["google_sheets"]["creds_file"]

    upload_df_to_gsheet(df, spreadsheet_name, creds_file)

if __name__ == "__main__":
    main()