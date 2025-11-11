#!/usr/bin/env python3
# explore.py

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
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException

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
    "dev": "beta"
}

# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config/settings.yaml")
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

# --------------------------------------------------------------------------- #
#  Selenium helpers
# --------------------------------------------------------------------------- #
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

    # Wait until either the table header or a "No results found" message appears.
    try:
        WebDriverWait(driver, 10).until(
            lambda d: (
                d.find_elements(By.XPATH, "//table[@id='explore_table']//thead/tr")
                or d.find_elements(By.XPATH, "//table[@id='explore_table']//tbody//td[contains(., 'No results found')]")
                or d.find_elements(By.XPATH, "//table[@id='explore_table']//tbody/tr/td")
            )
        )
    except TimeoutException:
        return []

    # If the table explicitly reports no results, bail out early.
    no_results = driver.find_elements(
        By.XPATH, "//table[@id='explore_table']//tbody//td[contains(., 'No results found')]"
    )
    if no_results:
        return []

    # Get headers
    header_rows = driver.find_elements(By.XPATH, "//table[@id='explore_table']//thead/tr")
    if not header_rows:
        # Header row may be missing when the table is empty.
        return []
    header_row = header_rows[0]
    headers = [th.text.strip() for th in header_row.find_elements(By.TAG_NAME, "th")]

    # Get body rows; if none, this will just return []
    data = []
    for row in driver.find_elements(By.XPATH, "//table[@id='explore_table']//tbody/tr"):
        cells = row.find_elements(By.TAG_NAME, "td")
        values = [cell.text.strip() for cell in cells]
        if len(values) != len(headers):
            # skip "No results found" row or malformed rows
            continue
        data.append(dict(zip(headers, values)))

    return data

# --------------------------------------------------------------------------- #
#  Core scraping routine
# --------------------------------------------------------------------------- #
def scrape_explore(env):
    """
    For every URL in settings.yaml → explore_urls[env]:
        • load page
        • switch to: All-time / yearly view / raw numbers
        • extract table (“All articles”)
        • if the “Preprints” radio is present, click it, re-extract table
    Returns a flattened DataFrame with one metric per row.
    """
    urls          = CONFIG.get("explore_urls", {}).get(env, [])
    xpaths        = CONFIG["xpaths"]
    delay_cfg     = CONFIG["delays"]
    years_to_keep = CONFIG["explore"]["years_to_keep"]

    driver   = get_driver()
    out_rows = []

    for url in urls:
        print(f"→ {url}")
        driver.get(url)
        time.sleep(delay_cfg["page_load"])

        # --- 1. Click all-time ---------------------------------------------------------- #
        btn_all_time = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpaths["all_time_button"]))
        )
        driver.execute_script("arguments[0].click();", btn_all_time)
        time.sleep(delay_cfg["data_load"])

        # --- 2. Click year-by-year breakdown -------------------------------------------- #
        btn_year = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "explore_year_button"))
        )
        driver.execute_script("arguments[0].click();", btn_year)
        time.sleep(delay_cfg["data_load"])

        # --- 3. Toggle to raw number mode ----------------------------------------------- #
        try:
            toggle = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "toggle-data-view"))
            )
            if toggle.get_attribute("aria-checked") == "true":   # “%” mode
                driver.execute_script("arguments[0].click();", toggle)
                WebDriverWait(driver, 10).until(
                    lambda d: d.find_element(By.ID, "toggle-data-view")
                              .get_attribute("aria-checked") == "false"
                )
                time.sleep(delay_cfg["data_load"])
        except Exception as e:
            print(f"[warn] raw-number toggle unavailable: {e}")

        # --- Helper to flatten a table into out_rows ------------------------------------ #
        def _flush_table(table: list[dict], label_suffix: str):
            if not table:
                return
            year_col  = next(iter(table[0]))            # first column is Year/KEY
            recent    = sorted(
                {int(r[year_col]) for r in table if r[year_col].isdigit()}
            )[-years_to_keep:]

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for r in table:
                yr = r[year_col]
                if yr.isdigit() and int(yr) not in recent:
                    continue
                for metric, val in r.items():
                    if metric == year_col:
                        continue
                    figure = f"{metric} {label_suffix}"
                    row = {
                        "range": yr,
                        "figure": figure,
                        "value": val,
                        "url": url,
                        "collection_time": ts,
                    }
                    row["id"] = make_id(row["range"], row["figure"], "explore", row["url"])
                    out_rows.append(row)

        # --- 4. Normal publications view ------------------------------------------------ #
        try:
            tbl = extract_table_data(driver)
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException):
            print("[info] explore table missing/empty; skipping this URL")
            tbl = []
        _flush_table(tbl, "(Explore)")

        # --- 5. Optional: Preprints view ------------------------------------------------ #
        try:
            radio_pp = driver.find_element(By.ID, "filter_is_preprint")
            driver.execute_script("arguments[0].click();", radio_pp)
            time.sleep(delay_cfg["data_load"])
            tbl_pp = extract_table_data(driver)
            _flush_table(tbl_pp, "(Explore – Preprints)")
        except Exception:
            # radio absent → silently ignore
            pass

    driver.quit()
    return pd.DataFrame(
        out_rows,
        columns=["range", "figure", "value", "url", "collection_time", "id"]
    )

# --------------------------------------------------------------------------- #
#  CLI entry point
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev"], required=True,
                        help="Specify environment: staging, dev")
    args = parser.parse_args()

    df = scrape_explore(args.env)
    # Keep only the expected columns and handle empty safely
    if df.empty:
        print(f"[info] Explore: no rows for env={args.env}. Skipping CSV and Google Sheets upload.")
        return

    df = df[["range", "figure", "value", "url", "collection_time", "id"]]

    creds_file = CONFIG["google_sheets"]["creds_file"]
    folder_id = CONFIG["google_sheets"]["folder_id"]

    ENV_TAG_MAP = {"staging": "api", "dev": "beta"}
    env_tag = ENV_TAG_MAP[args.env]

    from extractors.utils import write_daily_csv
    from export.google_sheets import upload_df_to_daily_gsheet_named

    write_daily_csv(df=df, env_tag=env_tag, section="explore",
                    out_dir="snapshots", tz="Europe/London")

    upload_df_to_daily_gsheet_named(
        df=df,
        env_tag=env_tag,
        section="explore",
        folder_id=folder_id,
        creds_path=creds_file,
        tz="Europe/London",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "dev"], required=True, help="Specify environment: staging, dev")
    args = parser.parse_args()

    df = scrape_explore(args.env)
    df = df[["range", "figure", "value", "url", "collection_time", "id"]]
    if df.empty:
        print(f"[info] Explore: no rows for env={args.env}. Skipping CSV and Google Sheets upload.")
        return

    # Generate one Google Sheet per day, named {envTag}_{section}_parsed_data__YYYY-MM-DD
    # Read creds + per-env Drive folder ID from config
    creds_file = CONFIG["google_sheets"]["creds_file"]
    folder_id = CONFIG["google_sheets"]["folder_id"]

    # Map CLI env to env tag
    env_tag = ENV_TAG_MAP[args.env]
    write_daily_csv(df=df, env_tag=env_tag, section="explore", out_dir="snapshots", tz="Europe/London")

    upload_df_to_daily_gsheet_named(
        df=df,
        env_tag=env_tag,
        section="explore",
        folder_id=folder_id,
        creds_path=creds_file,
        tz="Europe/London",
    )

if __name__ == "__main__":
    main()