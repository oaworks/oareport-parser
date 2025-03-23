import gspread
from oauth2client.service_account import ServiceAccountCredentials

def upload_df_to_gsheet(df, spreadsheet_name, creds_path):
    # Define Google Sheets API scope
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Authorize client with service account credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet and get the first worksheet
    spreadsheet = client.open(spreadsheet_name)
    worksheet = spreadsheet.get_worksheet(0)

    # Check if the first row already contains headers
    existing_values = worksheet.get_all_values()
    if not existing_values:
        # Sheet is empty — write headers
        worksheet.append_row(df.columns.values.tolist())

    # Append each row of data
    for row in df.values.tolist():
        worksheet.append_row(row)

    print(f"Appended {len(df)} rows to Google Sheets: {spreadsheet_name}")
