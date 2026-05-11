"""
agents/orchestrator.py — Orchestrator for InstaAgent Repost Pipeline.

Content source: Google Sheets only (Instagram scraping is disabled).

Posting order: sequential — takes whatever row is next in the sheet.
No alternating image/reel pattern enforced.

3-tier priority:
  P1: skipped (auto_scrape_enabled: false — Instagram is blocking)
  P2: Google Sheets — next unposted URL from the sheet
  P3: Google Sheets safeguard — ANY sheet URL (force_any=True), even if
      already posted, to maintain the daily posting streak.

mark_reposted() is called ONLY after a successful publish to Instagram,
so dry-runs and failed posts never corrupt the dedup tracker.
"""

from typing import Optional

from agents.poster_agent import PosterAgent
from agents.repost_agent import RepostAgent
from core.sheets_reader import get_pending_row
from core.logger import get_logger
from core.repost_tracker import mark_reposted

logger = get_logger("Orchestrator")


class Orchestrator:
    """
    Top-level coordinator for the InstaAgent Repost system.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run  = dry_run
        self.poster_agent = PosterAgent()
        self.repost_agent = RepostAgent()
        logger.info(f"Orchestrator ready (dry_run={dry_run})")

    # ── Public API ────────────────────────────────────────────────────────────

    def repost_now(self) -> None:
        """
        Repost mode (--repost).

        Pulls content from Google Sheets (no Instagram scraping).
        Posts the next available row from the sheet — no type filtering.
        Records the post in the dedup tracker only after a confirmed publish.
        """
        logger.info("=" * 60)
        logger.info("  REPOST NOW — Google Sheets → Instagram pipeline")
        logger.info("=" * 60)

        result      = None
        source_url  = None
        is_safeguard = False   # True when Priority 3 fires

        # ── Priority 1: Auto-Scrape — DISABLED (Instagram is blocking) ────────
        logger.info("[Priority 1 Skipped] Instagram scraping is disabled.")

        # ── Priority 2: Google Sheets — unposted URL ──────────────────────────
        logger.info("[Priority 2] Checking Google Sheets for an unposted URL...")
        row = get_pending_row(force_any=False)

        if row:
            source_url = row["url"]
            logger.info(f"[Priority 2] Processing URL: {source_url}")
            result = self.repost_agent.process_specific_url(
                url            = source_url,
                category       = row.get("category", ""),
                sheet_caption  = row.get("caption", ""),
                owner_username = row.get("owner_username", ""),
            )

        # ── Priority 3: Google Sheets Safeguard — force any URL ───────────────
        if not result:
            logger.warning(
                "[Priority 2 Failed] No unposted URLs found. "
                "Activating safeguard — will re-use a URL from the sheet."
            )
            row = get_pending_row(force_any=True)

            if row:
                source_url   = row["url"]
                is_safeguard = True
                logger.info(f"[Priority 3 Safeguard] Re-using URL: {source_url}")
                result = self.repost_agent.process_specific_url(
                    url            = source_url,
                    category       = row.get("category", ""),
                    sheet_caption  = row.get("caption", ""),
                    owner_username = row.get("owner_username", ""),
                )

        # ── All tiers failed ──────────────────────────────────────────────────
        if not result:
            logger.error(
                "All priority tiers failed. "
                "Google Sheet appears to be empty or unreachable."
            )
            return

        image          = result["image"]
        caption        = result["caption"]
        source_post_id = result["source_post_id"]
        actual_type    = "reel" if result.get("is_reel") else "image"
        category       = result.get("category", "general")

        logger.info(f"Content ready — type: {actual_type.upper()}, source: {source_post_id}")
        if is_safeguard:
            logger.warning(f"[Safeguard] This is a repeat post of {source_post_id}.")
        logger.info(f"Caption preview:\n{caption[:300]}...")

        # ── Dry-run: stop here — do NOT write to tracker ──────────────────────
        if self.dry_run:
            logger.info("[DRY RUN] Cycle complete — would post:")
            logger.info(f"  Source  : {source_post_id}")
            logger.info(f"  Type    : {actual_type.upper()}")
            logger.info(f"  Image   : {image.get('local_path', 'N/A')}")
            logger.info("[DRY RUN] Tracker NOT updated (no actual publish).")
            return

        # ── Publish via PosterAgent ───────────────────────────────────────────
        logger.info("Publishing to Instagram (and Facebook if enabled)...")
        ig_post_id: Optional[str] = self.poster_agent.post(
            image=image,
            caption=caption,
            topic="repost",
        )

        if not ig_post_id:
            logger.error("Publish failed — tracker NOT updated. Check logs.")
            return

        # ── Record ONLY after confirmed publish ───────────────────────────────
        mark_reposted(
            shortcode  = source_post_id,
            post_type  = actual_type,
            source_url = source_url or "",
            category   = category,
        )

        logger.info(f"Repost complete. IG post ID: {ig_post_id}")
