"""
agents/orchestrator.py — Orchestrator for InstaAgent Repost Pipeline.

The Orchestrator coordinates the active agents to pull content from
target profiles, process it, and push it to Meta Graph API.

Posting pattern: reel → image → reel → image → ...
The pattern is enforced regardless of URL order in Google Sheets.
If the preferred type is unavailable, we fall back to whatever is available
and the alternating logic self-corrects on the next run.
"""

from typing import Optional

from agents.poster_agent import PosterAgent
from agents.repost_agent import RepostAgent
from core.sheets_reader import get_pending_row
from core.logger import get_logger
from core.post_state import get_next_post_type, save_post_type

logger = get_logger("Orchestrator")


class Orchestrator:
    """
    Top-level coordinator for the InstaAgent Repost system.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

        # Instantiate active agents
        self.poster_agent = PosterAgent()
        self.repost_agent = RepostAgent()

        logger.info(f"Orchestrator ready (dry_run={dry_run})")

    # ── Public API ────────────────────────────────────────────────────────────

    def repost_now(self) -> None:
        """
        Repost mode (--repost).

        Enforces a strict reel → image → reel → image alternating pattern.
        Reads config to decide which content source to use, tries each
        priority tier in order, and publishes via PosterAgent.
        """
        logger.info("=" * 60)
        logger.info("  REPOST NOW — scrape & publish pipeline (IG + Facebook)")
        logger.info("=" * 60)

        from core.flags import get_config
        config = get_config()
        auto_scrape = config.get("repost", {}).get("auto_scrape_enabled", True)

        # Determine what type we should post this run
        next_type = get_next_post_type()
        logger.info(f"Pattern target: post a {next_type.upper()} this run.")

        result = None

        # ── Priority 1: Auto-Scrape ───────────────────────────────────────────
        if auto_scrape:
            logger.info("[Priority 1] RepostAgent: fetching unseen post from source account...")
            result = self.repost_agent.run(force_duplicate=False)
        else:
            logger.info("[Priority 1 Skipped] auto_scrape_enabled is False.")

        # ── Priority 2: Google Sheets Manual Queue ────────────────────────────
        if not result:
            logger.warning("[Priority 1 Failed] Checking Google Sheets manual queue...")
            logger.info(f"Requesting {next_type.upper()} from sheet (will fall back if unavailable).")

            row = get_pending_row(preferred_type=next_type)
            if row:
                url, cat = row
                logger.info(f"[Priority 2] Processing manual URL: {url}")
                result = self.repost_agent.process_specific_url(url, category=cat)

                # ── BUG FIX: save_post_type was not called for sheet-sourced posts ──
                # We must record what type was *actually* posted (may differ from
                # next_type if the sheet fell back to the opposite type).
                if result:
                    actual_type = "reel" if result.get("is_reel") else "image"
                    save_post_type(actual_type)
                    next_target = "reel" if actual_type == "image" else "image"
                    logger.info(
                        f"[Pattern] Posted {actual_type.upper()} "
                        f"(requested {next_type.upper()}). "
                        f"Next run will target {next_target.upper()}."
                    )

        # ── Priority 3: Duplicate Safeguard ───────────────────────────────────
        if not result:
            logger.warning(
                "[Priority 2 Failed] Google Sheet empty or exhausted. "
                "Forcing a DUPLICATE post to maintain daily streak."
            )
            result = self.repost_agent.run(force_duplicate=True)

        if not result:
            logger.error(
                "All 3 priority tiers failed. "
                "Unable to fetch any content from Instagram today."
            )
            return

        image = result["image"]
        caption = result["caption"]
        source_post_id = result["source_post_id"]

        logger.info(f"Repost ready — source post: {source_post_id}")
        logger.info(f"Caption preview:\n{caption[:300]}...")

        # ── Dry-run shortcut ───────────────────────────────────────────────────
        if self.dry_run:
            logger.info("[DRY RUN] Cycle complete — would post:")
            logger.info(f"  Source : {source_post_id}")
            logger.info(f"  Type   : {'REEL' if result.get('is_reel') else 'IMAGE'}")
            logger.info(f"  Image  : {image.get('local_path', 'N/A')}")
            return

        # ── Step 2: Publish via PosterAgent (Instagram + Facebook) ────────────
        logger.info("Publishing to Instagram (and Facebook if enabled)...")
        ig_post_id: Optional[str] = self.poster_agent.post(
            image=image,
            caption=caption,
            topic="repost",
        )

        if not ig_post_id:
            logger.error("Post failed. Check logs/errors.log for details.")
            return

        logger.info(f"Repost complete. IG post ID: {ig_post_id}")
