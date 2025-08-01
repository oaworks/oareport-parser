#!/usr/bin/env python3
"""
Minimal gspread helpers – same API you already used, now extended to:
  • allow writing to / replacing an arbitrary worksheet
  • maintain an ‘INFO’ tab with the list of run-tabs
"""
import time, pandas as pd, gspread
from gspread.exceptions import APIError, WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

# --------------------------------------------------------------------------- #
#  Core uploader  (append OR replace)
# --------------------------------------------------------------------------- #
def upload_df_to_gsheet(df,
                        spreadsheet_name,
                        creds_path,
                        worksheet_name=None,
                        replace_sheet=False,
                        retries=3,
                        delay=10):
    """
    • worksheet_name None ⇒ first tab (legacy)
    • replace_sheet True  ⇒ clear + write header + rows
      else                ⇒ append rows
    """
    client = gspread.authorize(
        ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPE))

    ss = client.open(spreadsheet_name)
    if worksheet_name:
        try:
            ws = ss.worksheet(worksheet_name)
        except WorksheetNotFound:
            ws = ss.add_worksheet(title=worksheet_name,
                                  rows="1", cols=str(len(df.columns)))
    else:
        ws = ss.get_worksheet(0)

    # ▸ clear + header
    if replace_sheet:
        ws.clear()
        ws.append_row(df.columns.tolist())
    # ▸ header if empty
    elif not ws.get_all_values():
        ws.append_row(df.columns.tolist())

    rows = df.values.tolist()

    for n in range(retries):
        try:
            ws.append_rows(rows)
            print(f"Uploaded {len(rows)} rows → {spreadsheet_name}/{ws.title}")
            break
        except APIError as e:
            if "Quota exceeded" in str(e):
                print(f"Quota hit, retrying in {delay}s… ({n+1}/{retries})")
                time.sleep(delay)
            else:
                raise
    else:
        print("Failed after retries.")

# --------------------------------------------------------------------------- #
#  INFO-tab maintainer
# --------------------------------------------------------------------------- #
def append_run_to_info(spreadsheet_name, creds_path, tab_name):
    """Append the run-tab name to the INFO sheet (creates sheet if absent)."""
    client = gspread.authorize(
        ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPE))
    ss = client.open(spreadsheet_name)

    try:
        ws = ss.worksheet("INFO")
    except WorksheetNotFound:
        ws = ss.add_worksheet("INFO", rows="1", cols="1")

    ws.append_row([tab_name], table_range="A1")

# --------------------------------------------------------------------------- #
#  Simple reader (unchanged)
# --------------------------------------------------------------------------- #
def load_gsheet_to_df(spreadsheet_name, creds_path, worksheet_index=0):
    client = gspread.authorize(
        ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPE))
    ws = client.open(spreadsheet_name).get_worksheet(worksheet_index)
    return pd.DataFrame(ws.get_all_records())
