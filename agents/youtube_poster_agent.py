"""
agents/youtube_poster_agent.py — Uploads videos to YouTube via YouTube Data API v3.

Posting flow:
  1. Build OAuth2 credentials from env vars (uses refresh token — no browser needed at runtime).
  2. Upload the local video file using a resumable multi-chunk upload.
  3. Video is published publicly as a YouTube Short.

YouTube Shorts auto-detection criteria (as of Oct 2024):
  - Duration : ≤ 3 minutes / 180 seconds (YouTube raised limit from 60s → 3 min)
  - Orientation: Vertical/portrait (width < height, ideally 9:16 aspect ratio)
  - Title     : Containing #Shorts boosts Shorts feed discovery

Since our source content is Instagram Reels (already vertical), Shorts detection
is automatic — no manual flagging required beyond adding #Shorts to the title.
"""

import os
from typing import Optional

from core.logger import get_logger
from core.flags import get_config

logger = get_logger("YouTubePoster")

# YouTube Data API constants
_TOKEN_URI        = "https://oauth2.googleapis.com/token"
_SCOPES           = ["https://www.googleapis.com/auth/youtube.upload"]
_MAX_TITLE_LEN    = 100     # YouTube hard limit for video titles
_SHORTS_TAG       = "#Shorts"
_DEFAULT_CATEGORY = "24"    # "Entertainment" — best fit for dance/reel content


class YouTubePosterAgent:
    """
    Publishes short-form videos to YouTube as YouTube Shorts.

    Authenticates using an OAuth2 refresh token — no browser interaction
    needed at runtime. The token is exchanged automatically for a
    short-lived access token on each call.
    """

    def __init__(self):
        self.client_id: Optional[str]     = os.getenv("YT_CLIENT_ID")
        self.client_secret: Optional[str] = os.getenv("YT_CLIENT_SECRET")
        self.refresh_token: Optional[str] = os.getenv("YT_REFRESH_TOKEN")

    def is_configured(self) -> bool:
        """Returns True only if all three OAuth2 credentials are present in env."""
        return bool(self.client_id and self.client_secret and self.refresh_token)

    # ── Public entry point ────────────────────────────────────────────────────

    def post(self, video_path: str, caption: str) -> Optional[str]:
        """
        Upload a local video file to YouTube as a Short.

        Args:
            video_path:  Absolute (or relative) path to the local .mp4 file.
            caption:     Caption string from RepostAgent — used as title + description.

        Returns:
            YouTube video ID string on success (e.g. 'dQw4w9WgXcQ'), None on failure.
        """
        if not self.is_configured():
            logger.warning(
                "YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN not set "
                "— skipping YouTube post."
            )
            return None

        if not video_path or not os.path.isfile(video_path):
            logger.error(f"YouTube: video file not found: '{video_path}'")
            return None

        # Lazy-import heavy Google SDK — only loaded when actually posting to YT
        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
        except ImportError:
            logger.error(
                "Google API client libraries not installed. "
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            )
            return None

        try:
            youtube   = self._build_client(Credentials, Request, build)
            title     = self._make_title(caption)
            desc      = self._make_description(caption)

            logger.info(f"YouTube: starting Short upload — \"{title[:70]}...\"")
            video_id = self._upload(youtube, video_path, title, desc, MediaFileUpload, HttpError)

            if video_id:
                logger.info(f"✅ YouTube Short published! Video ID: {video_id}")
                logger.info(f"   → https://www.youtube.com/shorts/{video_id}")
            return video_id

        except Exception as exc:
            # Catch-all so a YT failure never blocks Instagram posting
            logger.error(f"YouTube upload failed unexpectedly: {exc}", exc_info=True)
            return None

    # ── OAuth2 client builder ─────────────────────────────────────────────────

    def _build_client(self, Credentials, Request, build):
        """
        Build an authenticated YouTube API service client.

        Uses the stored refresh token to obtain a short-lived access token.
        Fails fast (raises) if the credentials are invalid/revoked so the
        caller can log the error cleanly.
        """
        creds = Credentials(
            token         = None,          # No cached access token — will be fetched fresh
            refresh_token = self.refresh_token,
            token_uri     = _TOKEN_URI,
            client_id     = self.client_id,
            client_secret = self.client_secret,
            scopes        = _SCOPES,
        )

        # Force a token refresh NOW — catches expired/revoked tokens immediately
        creds.refresh(Request())
        logger.info("YouTube: OAuth2 token refreshed successfully.")

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    # ── Resumable upload ──────────────────────────────────────────────────────

    def _upload(
        self,
        youtube,
        video_path: str,
        title: str,
        description: str,
        MediaFileUpload,
        HttpError,
    ) -> Optional[str]:
        """
        Execute a resumable chunked upload to YouTube.

        Uses chunksize=-1 (single-chunk upload) for files that fit in memory.
        For larger files, the Google SDK handles retries internally.
        """
        config      = get_config()
        yt_cfg      = config.get("youtube", {})
        category_id = str(yt_cfg.get("category_id", _DEFAULT_CATEGORY))
        tags        = yt_cfg.get("tags", ["Shorts", "Entertainment", "Dance", "ViralReels"])

        body = {
            "snippet": {
                "title"      : title,
                "description": description,
                "tags"       : tags,
                "categoryId" : category_id,
            },
            "status": {
                "privacyStatus"            : "public",
                "selfDeclaredMadeForKids"  : False,
            },
        }

        media   = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"YouTube upload progress: {progress}%")
            except HttpError as e:
                if e.status_code in (500, 502, 503, 504):
                    # Transient server error — the resumable upload can retry
                    logger.warning(f"YouTube transient error {e.status_code} — retrying chunk...")
                    continue
                raise  # Non-retriable error — bubble up

        video_id: Optional[str] = response.get("id")
        return video_id

    # ── Caption → title / description helpers ─────────────────────────────────

    def _make_title(self, caption: str) -> str:
        """
        Extract the first non-empty line of the caption as the video title.

        YouTube titles are hard-capped at 100 characters.
        We reserve 8 chars for ' #Shorts' suffix to boost Shorts discoverability.

        Examples:
            'Drop a 🔥 if you can do this move!\\n\\nThis transition is EVERYTHING...' 
            → 'Drop a 🔥 if you can do this move! #Shorts'
        """
        first_line = next(
            (line.strip() for line in caption.splitlines() if line.strip()),
            "Entertainment Reel"
        )

        shorts_suffix = f" {_SHORTS_TAG}"
        max_base      = _MAX_TITLE_LEN - len(shorts_suffix)

        if len(first_line) > max_base:
            first_line = first_line[:max_base - 3] + "..."

        return f"{first_line}{shorts_suffix}"

    def _make_description(self, caption: str) -> str:
        """
        Use the full caption as the YouTube video description.

        Appends #Shorts on a new line if not already present (belt-and-suspenders
        for Shorts feed discovery alongside the title tag).
        """
        if _SHORTS_TAG not in caption:
            return f"{caption}\n\n{_SHORTS_TAG}"
        return caption
