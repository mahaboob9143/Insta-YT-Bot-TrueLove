"""
core/sheets_reader.py — Reads a public Google Sheet CSV to fetch manual URLs.

Priority 2: Returns an unposted URL matching the preferred type.
Priority 3: With force_any=True, returns ANY URL from the sheet (ignores dedup),
            so the system can still post something even when all URLs are exhausted.
"""
import csv
import io
import requests
from typing import Optional, Tuple

from core.logger import get_logger
from core.repost_tracker import is_reposted

logger = get_logger("SheetsReader")

# The public CSV export URL for the user's Google Sheet
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1UG-xzmeIt_0aCTrih4kCWYFY2fUFyPPYxJQE18Ext6w/export?format=csv"


def get_pending_row(
    preferred_type: str = "image",
    force_any: bool = False,
) -> Optional[Tuple[str, str]]:
    """
    Downloads the public Google Sheet as CSV and returns a URL to post.

    Normal mode (force_any=False — Priority 2):
      - Skips URLs that are already in the dedup tracker.
      - Tries to match the preferred_type (image or reel) first.
      - Falls back to any unposted URL if preferred type is unavailable.
      - Returns None if all URLs in the sheet have already been posted.

    Force mode (force_any=True — Priority 3 safeguard):
      - Ignores the dedup tracker entirely — treats all URLs as available.
      - Still tries to match preferred_type first, then falls back.
      - This ensures we can always post something even when the sheet
        appears exhausted, rather than falling back to Instagram scraping.
      - The URL selected will be re-posted (duplicate), which is intentional
        to maintain the daily posting streak.

    Returns:
        (url, category) tuple, or None if the sheet is empty/unreachable.
    """
    try:
        mode_label = "FORCE ANY (safeguard)" if force_any else f"preferred={preferred_type.upper()}"
        logger.info(f"Fetching manual queue from Google Sheets [{mode_label}]...")

        resp = requests.get(SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))

        preferred_match = None   # exact type match
        fallback_match  = None   # any available URL (wrong type or already posted)

        for row in reader:
            url      = row.get("URL", "").strip()
            category = row.get("Category", "").strip()

            if not url:
                continue

            # Extract shortcode from URL
            shortcode = url.strip("/").split("/")[-1].split("?")[0]

            # Dedup check — skipped entirely in force mode
            already_posted = is_reposted(shortcode)
            if already_posted and not force_any:
                logger.debug(f"Skipping {url} — already in tracker")
                continue

            is_reel_url = "/reel/" in url.lower() or "/tv/" in url.lower()
            type_matches = (preferred_type == "reel" and is_reel_url) or \
                           (preferred_type != "reel" and not is_reel_url)

            if type_matches and preferred_match is None:
                preferred_match = (url, category)
                if not force_any:
                    # In normal mode, return immediately on first exact match
                    logger.info(
                        f"Found EXACT match for {preferred_type.upper()}: "
                        f"{url} (Category: {category or 'general'})"
                    )
                    return preferred_match

            if fallback_match is None:
                fallback_match = (url, category)

        # In force mode, prefer exact type match but accept any
        if force_any and preferred_match:
            logger.info(
                f"[Safeguard] Re-using {preferred_type.upper()} URL: "
                f"{preferred_match[0]} (Category: {preferred_match[1] or 'general'})"
            )
            return preferred_match

        if fallback_match:
            label = "any available (safeguard)" if force_any else f"no {preferred_type} available, falling back"
            logger.warning(
                f"Could not find a {preferred_type.upper()} — "
                f"using fallback URL [{label}]: {fallback_match[0]}"
            )
            return fallback_match

        logger.info("No URLs found in Google Sheet.")
        return None

    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return None
