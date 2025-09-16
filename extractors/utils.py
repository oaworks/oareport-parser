from pathlib import Path
from datetime import datetime
import pytz
import re
ORG_RE = re.compile(r"https?://(?:(?:dev|staging|migration)\.)?oa\.report/([^/?#]+)", re.I)

def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[^a-z0-9\- ]+", "", s)      # keep letters, digits, space, dash
    s = re.sub(r"\s+", "-", s)               # spaces become dashes
    s = re.sub(r"-{2,}", "-", s).strip("-")  # collapse and trim dashes
    return s

def _section_key(section: str, figure: str) -> str:
    """
    Derive a clean section label from the figure’s trailing parentheses if present.
    Normalises:
      (insight) -> insights
      (action)  -> actions
      (Explore …) -> explore[-…]
    Falls back to the provided section.
    """
    m = re.search(r"\(([^)]*)\)\s*$", figure or "", flags=re.I)
    if m:
        inside = _slugify(m.group(1))  # e.g. "insight", "action", "explore-preprints"
        if inside in {"insight", "insights"}:
            return "insights"
        if inside in {"action", "actions"}:
            return "actions"
        if inside.startswith("explore"):
            return inside            # "explore" or "explore-preprints"
    return (section or "").strip().lower()


def make_id(date_range: str, figure: str, section: str, url: str) -> str:
    """
    Build a row ID in the form: {range}_{figure-slug}_{section-key}_{org-slug}.

    - range: e.g. "2025" or "All time"
    - figure-slug: figure lowercased, accents removed, spaces convert to '-', trailing "(...)" stripped
    - section-key: base section plus optional qualifier from "(...)" (e.g. "explore-preprints")
    - org-slug: first path segment from oa.report URL (e.g. ".../hhmi" → "hhmi")

    Underscores separate parts; hyphens within slugs.
    """
    base_fig = re.sub(r"\s*\([^)]*\)\s*$", "", figure or "").strip()  # strip trailing (... )
    org = (ORG_RE.search(url or "") or [None, ""])[1].lower()
    return f"{_slugify(date_range)}_{_slugify(base_fig)}_{_section_key(section, figure)}_{org}"

def _today_str(tz_name="Europe/London"):
    tz = pytz.timezone(tz_name)
    return datetime.now(tz).strftime("%Y-%m-%d")

def write_daily_csv(df, env_tag: str, section: str, out_dir: str = "snapshots", tz: str = "Europe/London"):
    """
    Writes a CSV named: {env_tag}_{section}_parsed_data__{yyyy-mm-dd}.csv
    Columns are preserved exactly as in df.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    date_str = _today_str(tz)
    fname = f"{env_tag}_{section}_parsed_data__{date_str}.csv"
    fpath = Path(out_dir) / fname
    df.to_csv(fpath, index=False)
    print(f"Wrote daily CSV: {fpath} ({len(df)} rows)")
    return str(fpath)
