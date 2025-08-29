import re, unicodedata
ORG_RE = re.compile(r"https?://(?:[^/]*\.)?oa\.report/([^/?#]+)", re.I)

def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)

def _section_key(section: str, figure: str) -> str:
    """
    Derive a section key from the base section and any parenthetical qualifier
    present in the figure text.

    Rules:
    - If figure contains '(...)', slugify the inside.
    - If that slug starts with a known section prefix ('explore', 'actions', 'insights'),
      return it as-is (e.g. 'explore-preprints').
    - Otherwise, return '{base}-{qualifier}' (e.g. 'actions-email-nudges').
    - If no qualifier, return the base section.
    """
    base = (section or "").lower()
    m = re.search(r"\(([^)]*)\)", figure or "")
    if not m:
        return base

    inside = m.group(1).replace("–", "-").replace("—", "-")
    qual = _slugify(inside)

    if not qual:
        return base

    if qual.startswith(("explore", "actions", "insights")):
        return qual

    return f"{base}-{qual}"


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
    return f"{date_range}_{_slugify(base_fig)}_{_section_key(section, figure)}_{org}"