import time
import pandas as pd
import gspread
import pytz
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError
from googleapiclient.discovery import build
from datetime import datetime

def upload_df_to_gsheet(df, spreadsheet_name, creds_path, retries=3, delay=10):
    # Define Google Sheets API scope
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Authorise client with service account credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet and get the first worksheet
    spreadsheet = client.open(spreadsheet_name)
    worksheet = spreadsheet.get_worksheet(0)

    # Get all existing rows (check if header exists)
    existing_values = worksheet.get_all_values()

    # If sheet is empty, write headers first
    if not existing_values:
        worksheet.append_row(df.columns.tolist())

    # If sheet is not empty but headers don't match, raise a warning
    elif existing_values[0] != df.columns.tolist():
        print("Column headers do not match existing sheet. No data appended.")
        print("Local DF columns:", df.columns.tolist())
        print("Remote sheet columns:", existing_values[0])
        return

    # Convert dataframe to list of lists
    data_rows = df.values.tolist()

    # Retry appending if rate limit is hit
    for attempt in range(retries):
        try:
            worksheet.append_rows(data_rows)
            print(f"Appended {len(data_rows)} rows to Google Sheet: {spreadsheet_name}")
            break  # Success, exit loop
        except APIError as e:
            if "Quota exceeded" in str(e):
                print(f"Rate limit hit, retrying in {delay} seconds… (attempt {attempt+1}/{retries})")
                time.sleep(delay)
            else:
                raise  # Raise other API errors immediately
    else:
        print("Failed to append rows after multiple attempts due to API rate limits.")

def load_gsheet_to_df(spreadsheet_name, creds_path, worksheet_index=0):
    """
    Load data from a Google Sheet into a pandas DataFrame.
    Only pulls the worksheet at the given index (default = 0).
    Assumes headers are in the first row.
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)

    spreadsheet = client.open(spreadsheet_name)
    worksheet = spreadsheet.get_worksheet(worksheet_index)

    # Get all rows as dictionaries (header taken from row 1)
    records = worksheet.get_all_records()
    return pd.DataFrame(records)

def _sa_creds(creds_path, scopes):
    return ServiceAccountCredentials.from_json_keyfile_name(creds_path, scopes)

def _drive_service(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _gspread_client(creds):
    return gspread.authorize(creds)

def upload_df_to_daily_gsheet_named(
    df: pd.DataFrame,
    env_tag: str,                 # "api" | "beta" | "migration"
    section: str,                 # "insights" | "explore" | "actions"
    folder_id: str,               # Google Drive folder ID
    creds_path: str,
    tz: str = "Europe/London",
    date_str: str | None = None,  # override date if needed
    retries: int = 3,
    delay: int = 10,
):
    """
    Create/overwrite ONE spreadsheet per day in the given Drive folder with the name:
      {env_tag}_{section}_parsed_data__YYYY-MM-DD

    If the same-day run happens again, the existing file is deleted then recreated.

    Requirements:
      - Service account has Editor access to the folder (folder_id).
      - googleapiclient is installed (pip install google-api-python-client pytz).
    """
    env_tag = env_tag.strip().lower()
    section = section.strip().lower()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _sa_creds(creds_path, scopes)
    drive = _drive_service(creds)
    gc = _gspread_client(creds)

    if date_str is None:
        now = datetime.now(pytz.timezone(tz))
        date_str = now.date().isoformat()

    title = f"{env_tag}_{section}_parsed_data__{date_str}"

    # Delete any existing same-name spreadsheet in the folder (overwrite behaviour)
    # NOTE: name matching is exact; if you use single quotes in names you'll need escaping.
    q = (
        f"name = '{title}' and "
        f"mimeType = 'application/vnd.google-apps.spreadsheet' and "
        f"'{folder_id}' in parents and trashed = false"
    )
    resp = drive.files().list(q=q, fields="files(id,name)").execute()
    for f in resp.get("files", []):
        drive.files().delete(fileId=f["id"]).execute()

    # Create new spreadsheet in the folder
    sh = gc.create(title, folder_id=folder_id)
    ws = sh.sheet1

    # Write all data in one call
    values = [df.columns.tolist()] + df.astype(str).values.tolist()
    for attempt in range(retries):
        try:
            ws.update("A1", values)
            print(f"Created daily sheet '{title}' in folder {folder_id} with {len(df)} rows.")
            break
        except APIError as e:
            if "Quota exceeded" in str(e):
                print(f"Rate limit hit, retrying in {delay}s… (attempt {attempt+1}/{retries})")
                time.sleep(delay)
            else:
                raise