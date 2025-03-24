import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError

def upload_df_to_gsheet(df, spreadsheet_name, creds_path, retries=3, delay=10):
    # Define Google Sheets API scope
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Authorize client with service account credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet and get the first worksheet
    spreadsheet = client.open(spreadsheet_name)
    worksheet = spreadsheet.get_worksheet(0)

    # Get all existing rows (check if header exists)
    existing_values = worksheet.get_all_values()
    if not existing_values:
        worksheet.append_row(df.columns.tolist())

    # Convert data frame to list of rows
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