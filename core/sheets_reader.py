"""
core/sheets_reader.py — Reads a public Google Sheet CSV to fetch manual URLs.

Sheet columns expected:
    id | url | caption | type | ownerId | ownerUsername

Priority 2: Returns the next unposted row from the sheet (sheet order).
Priority 3: With force_any=True, returns the OLDEST-POSTED row from the sheet
            (i.e. the one posted the longest time ago), so repeated content is
            always the stalest — not the most recently posted.

Return value is a dict with keys:
    url, category, caption, post_type, owner_username
"""
import csv
import io
import requests
from typing import Optional, List, Dict

from core.logger import get_logger
from core.repost_tracker import is_reposted, get_last_posted_at

logger = get_logger("SheetsReader")

# The public CSV export URL for the user's Google Sheet
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1DHJcZW3q3uCGZr4rn8-mBiLX0FHBrXl5e75Y7S1OOXs/export?format=csv"


def _parse_row(row: dict) -> Optional[Dict]:
    """
    Parse a single CSV row into a normalised dict.
    Handles both old sheet format (URL/Category) and new format (url/type/caption/ownerUsername).
    Returns None if the row has no usable URL.
    """
    # Support both old uppercase URL and new lowercase url column
    url = row.get("url", row.get("URL", "")).strip()
    if not url:
        return None

    # "type" column: "Image" | "Video" → normalise to "image" | "reel"
    raw_type = row.get("type", "").strip().lower()
    if raw_type == "video":
        post_type = "reel"
    elif raw_type == "image":
        post_type = "image"
    else:
        # Fall back to URL-sniffing for old rows
        post_type = "reel" if ("/reel/" in url.lower() or "/tv/" in url.lower()) else "image"

    # Shortcode from URL
    shortcode = url.strip("/").split("/")[-1].split("?")[0]

    return {
        "url":           url,
        "shortcode":     shortcode,
        "post_type":     post_type,
        "caption":       row.get("caption", "").strip(),       # pre-scraped caption
        "owner_username": row.get("ownerUsername", "").strip(), # credit handle
        "category":      row.get("Category", "").strip(),      # optional manual category
    }


def get_pending_row(
    preferred_type: str = "",   # ignored — kept for backward compat only
    force_any: bool = False,
) -> Optional[Dict]:
    """
    Downloads the public Google Sheet as CSV and returns a row dict to post.

    Normal mode (force_any=False — Priority 2):
      - Skips rows whose URL shortcode is already in the dedup tracker.
      - Returns the first unposted row in sheet order (no type filtering).
      - Returns None if all URLs have already been posted.

    Safeguard mode (force_any=True — Priority 3):
      - Ignores the dedup check — all sheet rows are candidates.
      - Picks the row whose URL was posted the LONGEST time ago (oldest posted_at).
      - Returns None only if the sheet is empty or unreachable.

    Returns:
        Dict with keys: url, shortcode, post_type, caption, owner_username, category
        or None.
    """
    try:
        mode_label = "FORCE OLDEST (safeguard)" if force_any else f"preferred={preferred_type.upper()}"
        logger.info(f"Fetching manual queue from Google Sheets [{mode_label}]...")

        resp = requests.get(SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))

        # ── Normal mode (Priority 2) — first unposted row in sheet order ───────
        if not force_any:
            for raw_row in reader:
                entry = _parse_row(raw_row)
                if entry is None:
                    continue

                if is_reposted(entry["shortcode"]):
                    logger.debug(f"Skipping {entry['url']} — already in tracker")
                    continue

                logger.info(f"Found unposted row: {entry['url']} | @{entry['owner_username'] or 'unknown'} | type={entry['post_type']}")
                return entry

            logger.info("No unposted URLs found in Google Sheet.")
            return None

        # ── Safeguard mode (Priority 3): pick the OLDEST-POSTED row ────────────
        all_candidates: List[Dict] = []

        for raw_row in reader:
            entry = _parse_row(raw_row)
            if entry is None:
                continue
            all_candidates.append(entry)

        def _sort_key(entry: Dict):
            """Sort ascending by posted_at — oldest first."""
            return get_last_posted_at(entry["shortcode"])

        if all_candidates:
            all_candidates.sort(key=_sort_key)
            chosen = all_candidates[0]
            logger.info(
                f"[Safeguard] Re-posting OLDEST row: "
                f"{chosen['url']} (posted longest ago)"
            )
            return chosen

        logger.error("[Safeguard] Google Sheet is empty — nothing to post.")
        return None

    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return None
