# OA.Report Parser

This repo extracts data from OA.Report organisation pages ([`dev`](https://dev.oa.report) and [`staging`](https://staging.oa.reoprt) reflecting [`beta`](https://beta.oa.works/report/orgs) and [`api`](https://api.oa.works/report/orgs) API endpoints respectively) and pushes it to corresponding Google Sheets for QA and historical tracking purposes.

## What it does

- Scrapes Insights, Explore, and Actions metrics from OA.Report's `staging` and `dev` environments using Selenium.
- Extracts data using XPath to target specific page elements and stores it in local `.csv` files.
- Automatically uploads parsed data to four separate Google Sheets.
- All six parsers are scheduled to run daily via GitHub Actions.

---

## Repo structure

```
.
├── config/                          # Configuration files (never commit secrets; both files are in .gitignore)
│   ├── google_creds.json            # Google service account credentials
│   ├── google_creds.template.json   # Template for google_creds.json — remove .template
│   ├── settings.yaml                # List of parsed URLs, XPaths, output files, Google Sheets mapping
│   └── settings.template.yaml       # Template for settings.yaml — remove .template
├── extractors/                      # Main parser scripts
│   ├── insights.py                  # Parses Insights data
│   ├── compare_snapshots.py         # Compares two data snapshots — not in use at the moment
│   ├── explore.py                   # Parses Explore data
│   └── actions.py                   # Parses Actions data
├── export/                          # Google Sheets export handler
│   └── google_sheets.py             # Uploads data frames to Google Sheets
├── .github/
│   └── workflows/schedule.yml      # GitHub Actions runner (scheduled daily)
└── requirements.txt                # Python dependencies
```

---

## Configuration

This project requires two configuration files in the `config/` directory that need to be set up by the user:

1. `config/google_creds.json` – for Google Sheets API authentication
2. `config/settings.yaml` – for parser options, including URLs, XPath selectors, and Google Sheet names

### 1. *`google_creds.json`*

This file contains credentials for the Google service account that uploads data to Google Sheets.

#### To obtain it:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select the `OAREPORT-PARSER` project
3. Go to **APIs & Services → Credentials**
4. Click **Create Credentials → Service Account**
5. Follow the prompts (you can skip role assignment)
6. After creating the service account:
   - Go to the account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
7. Download and save it as `config/google_creds.json`
   - A template is also provided in this repo (`config/google_creds.template.json`)
   - Simply update the file name to `config/google_creds.json` and copy-paste to replace the contents of the JSON file downloaded in Google Cloud Console to this file
8. Share your target Google Sheets with the service account email (e.g. `...@...iam.gserviceaccount.com`), giving it Editor access

### 2. *`settings.yaml`*

This file contains:
- URLs to be parsed (i.e. organisational OA.Reports)
- XPath selectors (to target specific page elements)
- Output filenames (if generating CSVs on your own machine)
- Delay durations (time to wait after certain UI interactions)
- Google Sheets export details (for automated exports)

---

## GitHub Actions setup

This is already set up to automatically run daily.   

### Repository secrets

Go to GitHub → **Settings → Secrets and Variables → Actions**

Create the following secrets under **Repository secrets**:

| Name                | Value                                      |
|---------------------|--------------------------------------------|
| `GOOGLE_CREDS_JSON` | Paste the contents of `google_creds.json`  |
| `SETTINGS_YAML`     | Paste the contents of `settings.yaml`      |

### Workflow file: `.github/workflows/schedule.yml`

The current workflow will:

- Run daily at 2am UTC
- Or can be triggered manually via the GitHub UI

### Manual run 

Go to GitHub → **Actions** → **Daily OA.Report Parsing** → **Run workflow**

All four parsers will run manually. All runs, whether failed or successful, will be listed on this page as well. 

---

## Running locally

Useful for one-off exports in a single CSV file or for testing any changes done to the parsers before committing them to the repository. 

1. Set up your Python environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

1. Run any parser manually:

```bash
# For Insights
python extractors/insights.py --env staging
python extractors/insights.py --env dev

# For Explore
python extractors/explore.py --env staging
python extractors/explore.py --env dev

# For Actions
python extractors/actions.py --env staging
python extractors/actions.py --env dev
```

The data will be exported both to CSV (in your local project folder) and to the configured remote Google Sheet.
