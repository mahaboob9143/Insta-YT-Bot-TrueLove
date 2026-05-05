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

def get_pending_row(preferred_type: str = "image") -> Optional[Tuple[str, str]]:
    """
    Downloads the public Google Sheet as a CSV.
    Iterates through rows.
    Attempts to find an unprocessed URL that matches the preferred_type.
    If no match is found for the preferred_type, returns the first unprocessed URL available.
    Returns None if the sheet is empty, unreachable, or all URLs are processed.
    """
    try:
        logger.info(f"Fetching manual queue from Google Sheets (looking for a {preferred_type.upper()})...")
        resp = requests.get(SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        
        # Parse the CSV
        csv_text = resp.text
        reader = csv.DictReader(io.StringIO(csv_text))
        
        fallback_row = None
        
        for row in reader:
            url = row.get("URL", "").strip()
            category = row.get("Category", "").strip()
            
            if not url:
                continue
            
            # Extract shortcode from the URL
            parts = url.strip("/").split("/")
            if len(parts) >= 1:
                shortcode = parts[-1]
                shortcode = shortcode.split("?")[0]
                
                if not is_reposted(shortcode):
                    is_url_reel = "/reel/" in url.lower() or "/tv/" in url.lower()
                    
                    if (preferred_type == "reel" and is_url_reel) or (preferred_type != "reel" and not is_url_reel):
                        logger.info(f"Found EXACT match for {preferred_type}: {url} (Category: {category or 'general'})")
                        return (url, category)
                    
                    # Save the first non-matching unprocessed row as a fallback
                    if not fallback_row:
                        fallback_row = (url, category)
                else:
                    logger.debug(f"Skipping {url} — already in reposted_ids.txt")

        # If we couldn't find the preferred type, but found SOMETHING unprocessed, return it
        if fallback_row:
            logger.warning(f"Could not find a {preferred_type} in the sheet. Falling back to next available URL: {fallback_row[0]}")
            return fallback_row

        logger.info("No unprocessed URLs found in Google Sheet.")
        return None
        
    except Exception as e:
        logger.error(f"Failed to read Google Sheet: {e}")
        return None
