# OA.Report Parser

A small Python/Selenium project that:

1. Reads OA.Report pages as seen by users ([`dev`](https://dev.oa.report) and [`staging`](https://staging.oa.report) which reflect [`beta`](https://beta.oa.works/report/orgs) and [`api`](https://api.oa.works/report/orgs) API endpoints respectively).
2. Extracts figures from the Insights, Explore, and Actions sections.
3. Writes them into Google Sheets so that QA can compare snapshots across dates and spot any abnormal regressions or spikes quickly. It also feeds into an archive kept for historical tracking purposes.

It runs daily via [**GitHub Actions** workflow](https://github.com/oaworks/oareport-parser/actions).

## What it runs

For each task run done via GitHub Actions, we target the **website** (_not the API_ directly) on two environments:

- **Staging website** → `https://staging.oa.report/<org-slug>?orgkey=...`  
- **Dev website** → `https://dev.oa.report/<org-slug>?orgkey=...`

And for **each** environment we scrape **three sections** of a page:

- **Insights** – `extractors/insights.py`  
- **Explore** – `extractors/explore.py`  
- **Actions** – `extractors/actions.py`

That’s **3 sections × 2 envs = 6 scrapes** for each organisation’s OA.Report per full daily run.

---

## How it knows what to scrape

The configuration lives in **`config/settings.yaml`** and explicitly lists, per environment:

- The **exact org URLs** to visit (with their `orgkey`) for **Insights**, **Explore**, and **Actions**.
- Which **Google Sheet** each scrape should write to, split by env (e.g., `api_insights_parsed_data`, `beta_explore_parsed_data`, etc.).
- Additional settings:
  - `explore.years_to_keep: 5` (keep five years of Explore data)
  - XPaths for each section (e.g., `year_buttons`, `insights_cards`, `explore_table`, `actions_buttons`)
  - Small delays (`page_load`, `data_load`)
  - Output filenames per section (env-specific names derived at runtime)

Each extractor reads the config, opens a **headless Selenium** browser, and navigates to the configured URLs for the chosen env.

---

## What each extractor collects

For each section, generally, **one row = one piece of data**.

### Insights

- Visits each configured org page (on staging/dev), as set in `settings.yaml`.
- Captures **All time** **and** the **last two years including current**.
- Collects the snapshot’s date range, the metric’s name, its corresponding value (percentages for most metrics, e.g. “with open code”, and an absolute value for “total publications” only), the page URL, and its collection date & time. 

### Explore

- Visits each configured org page (on staging/dev), as set in `settings.yaml`.
- Takes a snapshot of the **last five years** (exceptionally set in `settings.yaml`).
- Scrapes the Explore table and **flattens/pivots** it to ensure that **one row = one metric** (e.g., `OPEN ACCESS = 73` for a given year).
- Collects the snapshot’s date range, the metric’s name, its corresponding value (always in absolute numbers), the page URL, and its collection date & time. 

### Actions (known previously as Strategy)

- Visits each configured org page (on staging/dev), as set in `settings.yaml`.
- Captures **All time** **and** the **last two years including current**.
- Collects the snapshot’s date range, the metric’s name, its corresponding value (always in absolute numbers), the page URL, and its collection date & time. 

> **Remember:** this **reads what the UI renders** (i.e. the exact figures a user sees) so this part of QA is meant to reflect the true user-facing state without requiring a human to manually navigate to every organisation and manually track their figures.

---

## Where the data goes

- **Local CSVs** per section/env for quick artifacts.  
- **Google Sheets** via `export/google_sheets.py`:
  - Uses a service account (`config/google_creds.json`) with `gspread`/`oauth2client`.
  - Includes **basic retry logic** for rate limits (“Quota exceeded”), retrying up to 3 times with a delay.
  - Appends rows to one of the six existing Google Sheet (one for each task run) specified in `settings.yaml`.

---

## Scheduling & operations

- The [**GitHub Actions** workflow](https://github.com/oaworks/oareport-parser/actions) (`.github/workflows/schedule.yml`) runs the six scrapes **daily** (and can be triggered manually).
- On failure, the workflow sends a notification via email which should be routed to Front. 

## How QA uses the output

- The **“Statistics QA”** Google Sheet is the human-friendly hub.
- Because the parser writes **timestamped snapshots** daily, QA can pick **two dates** (often 2–3 weeks apart) and use **Sheet formulas** to compute deltas and flag anomalies (spikes/drops).

## Important clarifications

- **No API reading:** the parser **does not** call `api.oa.works` / `beta.oa.works` directly; it reads **the websites** (`staging.oa.report`, `dev.oa.report`) — i.e., what the API **outputs to the UI**.  
- **Independent from Ghost Inspector:** GI is a separate front-end test/alert system. The parser is for **historical QA via Sheets** and is **not** coupled to GI.

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

---
