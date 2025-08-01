#!/usr/bin/env python3
"""
───────────────────────────────────────────────────────────────────────────────
  OA.Report – Explore scraper
───────────────────────────────────────────────────────────────────────────────
• Scrapes “Explore” for every URL in `settings.yaml → explore_urls[… ]`
• Writes **one worksheet per run** so a single tab can never exceed 10 M cells
    ─ daily mode (default) :  2025-08-01
    ─ weekly mode          :  2025-07-27__2025-08-02   (Sun-to-Sat)
• An ‘INFO’ tab tracks all run-tabs (latest appended last).  
  Down-stream QA formulas can always pick “last two runs” programmatically.
───────────────────────────────────────────────────────────────────────────────
"""

# --------------------------------------------------------------------------- #
#  Imports
# --------------------------------------------------------------------------- #
import os, sys, yaml, argparse, time
from datetime import datetime, date, timedelta
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# Allow import from parent directory for Google Sheets export helpers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from export.google_sheets import upload_df_to_gsheet, append_run_to_info  # noqa: E402

# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "../config/settings.yaml")
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
    """Return Explore table as list[dict]."""
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "explore_table"))
    )

    # ► headers
    header_row = driver.find_element(By.XPATH, "//table[@id='explore_table']//thead/tr")
    headers    = [th.text.strip() for th in header_row.find_elements(By.TAG_NAME, "th")]

    # ► body rows
    data = []
    for row in driver.find_elements(By.XPATH, "//table[@id='explore_table']//tbody/tr"):
        cells   = [td.text.strip() for td in row.find_elements(By.TAG_NAME, "td")]
        if len(cells) != len(headers):
            print("Skipping row due to col mismatch:", cells)
            continue
        data.append(dict(zip(headers, cells)))
    return data

# --------------------------------------------------------------------------- #
#  Tab-naming helpers
# --------------------------------------------------------------------------- #
def today_tab() -> str:
    return date.today().isoformat()                         # 2025-08-01

def week_tab() -> str:
    today   = date.today()
    sunday  = today - timedelta(days=(today.weekday() + 1) % 7)
    saturday = sunday + timedelta(days=6)
    return f"{sunday}__{saturday}"                          # 2025-07-27__2025-08-02

# --------------------------------------------------------------------------- #
#  Core scraping routine
# --------------------------------------------------------------------------- #
def scrape_explore(env: str) -> pd.DataFrame:
    """
    • load page  → all-time
    • switch to yearly, raw numbers
    • extract table(s)  – main view + optional “Preprints”
    • keep only the N most recent years, flatten to rows
    """
    urls       = CONFIG["explore_urls"][env]
    xpaths     = CONFIG["xpaths"]
    delay_cfg  = CONFIG["delays"]
    keep_years = CONFIG["explore"]["years_to_keep"]

    driver   = get_driver()
    out_rows = []

    for url in urls:
        print("→", url)
        driver.get(url);                     time.sleep(delay_cfg["page_load"])

        # (1) click “All-time”
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpaths["all_time_button"]))
        ).click()
        time.sleep(delay_cfg["data_load"])

        # (2) click “Years” breakdown
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "explore_year_button"))
        ).click()
        time.sleep(delay_cfg["data_load"])

        # (3) toggle raw-numbers (if currently %)
        try:
            toggle = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "toggle-data-view"))
            )
            if toggle.get_attribute("aria-checked") == "true":
                toggle.click()
                WebDriverWait(driver, 10).until(
                    lambda d: d.find_element(By.ID, "toggle-data-view")
                              .get_attribute("aria-checked") == "false")
                time.sleep(delay_cfg["data_load"])
        except Exception:
            print("[warn] raw/percent toggle missing → skip")

        # helper to flatten a table into out_rows
        def flush(tbl: list[dict], suffix: str):
            if not tbl:
                return
            key_col = next(iter(tbl[0]))                   # first column = year/“KEY”
            recent  = sorted({int(r[key_col]) for r in tbl if r[key_col].isdigit()})[-keep_years:]
            ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for r in tbl:
                yr = r[key_col]
                if yr.isdigit() and int(yr) not in recent:
                    continue
                for metric, val in r.items():
                    if metric == key_col:
                        continue
                    out_rows.append({
                        "date_range"     : yr,
                        "figure"         : f"{metric} {suffix}",
                        "value"          : val,
                        "Page_URL"       : url,
                        "collection_time": ts
                    })

        # (4) ► main view
        try:
            flush(extract_table_data(driver), "(Explore)")
        except StaleElementReferenceException:
            flush(extract_table_data(driver), "(Explore)")

        # (5) ► optional Preprints view
        try:
            driver.find_element(By.ID, "filter_is_preprint").click()
            time.sleep(delay_cfg["data_load"])
            flush(extract_table_data(driver), "(Explore – Preprints)")
        except Exception:
            pass  # radio absent – ignore

    driver.quit()
    return pd.DataFrame(out_rows)

# --------------------------------------------------------------------------- #
#  CLI entry-point
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env",    required=True, choices=["staging", "dev"])
    parser.add_argument("--period", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()

    df        = scrape_explore(args.env)
    ss_name   = CONFIG["google_sheets"]["sheets"]["explore"][args.env]
    creds     = CONFIG["google_sheets"]["creds_file"]
    tab_name  = today_tab() if args.period == "daily" else week_tab()

    # write to sheet (replace tab if already exists)
    upload_df_to_gsheet(df, ss_name, creds,
                        worksheet_name=tab_name, replace_sheet=True)
    append_run_to_info(ss_name, creds, tab_name)

    # optional CSV dump
    csv_file = f"explore_{args.env}_{tab_name}.csv"
    df.to_csv(csv_file, index=False)
    print("CSV →", csv_file)

if __name__ == "__main__":
    main()