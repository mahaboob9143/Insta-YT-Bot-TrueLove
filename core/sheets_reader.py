"""
core/sheets_reader.py — Reads a public Google Sheet CSV to fetch manual URLs.
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

def get_pending_row() -> Optional[Tuple[str, str]]:
    """
    Downloads the public Google Sheet as a CSV.
    Iterates through rows.
    Finds the first row where the URL is NOT in our reposted_ids.txt.
    Returns (URL, Category).
    Returns None if the sheet is empty, unreachable, or all URLs are processed.
    """
    try:
        logger.info("Fetching manual queue from Google Sheets...")
        resp = requests.get(SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        
        # Parse the CSV
        csv_text = resp.text
        reader = csv.DictReader(io.StringIO(csv_text))
        
        for row in reader:
            url = row.get("URL", "").strip()
            category = row.get("Category", "").strip()
            
            if not url:
                continue
            
            # Extract shortcode from the URL to check the dedup tracker
            # Example URLs: 
            # https://www.instagram.com/reel/C-123456789/
            # https://www.instagram.com/p/C-123456789/
            parts = url.strip("/").split("/")
            if len(parts) >= 1:
                shortcode = parts[-1]
                # Sometimes URLs have query params: ?utm_source=ig_web_copy_link
                shortcode = shortcode.split("?")[0]
                
                if not is_reposted(shortcode):
                    logger.info(f"Found unprocessed manual URL: {url} (Category: {category or 'general'})")
                    return (url, category)
                else:
                    logger.debug(f"Skipping {url} — already in reposted_ids.txt")

        logger.info("No unprocessed URLs found in Google Sheet.")
        return None
        
    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return None
