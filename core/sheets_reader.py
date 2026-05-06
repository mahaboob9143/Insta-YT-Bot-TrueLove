"""
core/sheets_reader.py — Reads a public Google Sheet CSV to fetch manual URLs.

Priority 2: Returns an unposted URL matching the preferred type.
Priority 3: With force_any=True, returns the OLDEST-POSTED URL from the sheet
            (i.e. the one posted the longest time ago), so repeated content is
            always the stalest — not the most recently posted.
"""
import csv
import io
import requests
from typing import Optional, Tuple, List

from core.logger import get_logger
from core.repost_tracker import is_reposted, get_last_posted_at

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
      - Falls back to any unposted URL if the preferred type is unavailable.
      - Returns None if all URLs have already been posted.

    Safeguard mode (force_any=True — Priority 3):
      - Ignores the dedup check — all sheet URLs are candidates.
      - Picks the URL that was posted the LONGEST time ago (oldest posted_at
        in tracker.xlsx), so the repeated content is as stale as possible.
      - Still prefers the correct type (image/reel) for the alternating pattern.
        Falls back to any type if the preferred type has no match.
      - Returns None only if the sheet is empty or unreachable.

    Returns:
        (url, category) tuple, or None.
    """
    try:
        mode_label = "FORCE OLDEST (safeguard)" if force_any else f"preferred={preferred_type.upper()}"
        logger.info(f"Fetching manual queue from Google Sheets [{mode_label}]...")

        resp = requests.get(SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))

        # ── Normal mode (Priority 2) ───────────────────────────────────────────
        if not force_any:
            preferred_match = None
            fallback_match  = None

            for row in reader:
                url      = row.get("URL", "").strip()
                category = row.get("Category", "").strip()
                if not url:
                    continue

                shortcode = url.strip("/").split("/")[-1].split("?")[0]
                if is_reposted(shortcode):
                    logger.debug(f"Skipping {url} — already in tracker")
                    continue

                is_reel_url  = "/reel/" in url.lower() or "/tv/" in url.lower()
                type_matches = (preferred_type == "reel" and is_reel_url) or \
                               (preferred_type != "reel" and not is_reel_url)

                if type_matches:
                    logger.info(
                        f"Found EXACT match for {preferred_type.upper()}: "
                        f"{url} (Category: {category or 'general'})"
                    )
                    return (url, category)

                if fallback_match is None:
                    fallback_match = (url, category)

            if fallback_match:
                logger.warning(
                    f"No unposted {preferred_type.upper()} found — "
                    f"falling back to: {fallback_match[0]}"
                )
                return fallback_match

            logger.info("No unposted URLs found in Google Sheet.")
            return None

        # ── Safeguard mode (Priority 3): pick the OLDEST-POSTED URL ───────────
        # Collect every URL in the sheet (all types, ignore dedup)
        preferred_candidates: List[Tuple[str, str]] = []   # correct type
        fallback_candidates:  List[Tuple[str, str]] = []   # any type

        for row in reader:
            url      = row.get("URL", "").strip()
            category = row.get("Category", "").strip()
            if not url:
                continue

            is_reel_url  = "/reel/" in url.lower() or "/tv/" in url.lower()
            type_matches = (preferred_type == "reel" and is_reel_url) or \
                           (preferred_type != "reel" and not is_reel_url)

            if type_matches:
                preferred_candidates.append((url, category))
            else:
                fallback_candidates.append((url, category))

        def _sort_key(entry: Tuple[str, str]):
            """Sort ascending by posted_at — oldest first."""
            url = entry[0]
            shortcode = url.strip("/").split("/")[-1].split("?")[0]
            return get_last_posted_at(shortcode)

        if preferred_candidates:
            preferred_candidates.sort(key=_sort_key)
            chosen = preferred_candidates[0]
            logger.info(
                f"[Safeguard] Re-posting OLDEST {preferred_type.upper()}: "
                f"{chosen[0]} (posted longest ago)"
            )
            return chosen

        if fallback_candidates:
            fallback_candidates.sort(key=_sort_key)
            chosen = fallback_candidates[0]
            logger.warning(
                f"[Safeguard] No {preferred_type.upper()} in sheet — "
                f"re-posting oldest available: {chosen[0]}"
            )
            return chosen

        logger.error("[Safeguard] Google Sheet is empty — nothing to post.")
        return None

    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return None
