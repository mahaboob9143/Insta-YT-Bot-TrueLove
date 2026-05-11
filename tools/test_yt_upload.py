"""
tools/test_yt_upload.py — Standalone YouTube Short upload tester.

Tests the YouTubePosterAgent in complete isolation:
  - Does NOT touch Instagram, Google Sheets, or Cloudinary
  - Does NOT affect the repost tracker or post_state
  - Uploads a single local video file to YouTube as a Short

Usage:
    # Use any local .mp4 you have:
    python tools/test_yt_upload.py --video path/to/your_reel.mp4

    # Or drop any .mp4 into media/reposts/ and run without args:
    python tools/test_yt_upload.py

    # Custom caption:
    python tools/test_yt_upload.py --video myreel.mp4 --caption "My test caption"

Requirements:
    - YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN must be set in .env
    - If token is expired, regenerate with:  python tools/yt_auth.py
"""

import argparse
import os
import sys
import glob

# ── Bootstrap path so core/ and agents/ are importable ───────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.youtube_poster_agent import YouTubePosterAgent
from core.logger import get_logger

logger = get_logger("YT-Test")

_DEFAULT_CAPTION = """\
سبحان الله — Glory be to Allah ☁️

Every moment is a reminder of His mercy.
Take a moment to reflect and be grateful.

#islamic #quran #islamicshorts #deen"""


def find_any_local_video() -> str:
    """
    Scan common locations for a local .mp4 file to use as test input.
    Returns the first one found, or empty string if none.
    """
    search_dirs = [
        "media/reposts",
        "media",
        ".",
    ]
    for d in search_dirs:
        mp4_files = glob.glob(os.path.join(d, "*.mp4"))
        if mp4_files:
            return mp4_files[0]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test YouTube Short upload without touching Instagram."
    )
    parser.add_argument(
        "--video",
        type=str,
        default="",
        help="Path to a local .mp4 video file. "
             "If not provided, scans media/reposts/ for any .mp4.",
    )
    parser.add_argument(
        "--caption",
        type=str,
        default=_DEFAULT_CAPTION,
        help="Caption / description for the YouTube Short.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  YouTube Short — Standalone Upload Test")
    print("=" * 60)

    # ── 1. Resolve video file ─────────────────────────────────────────────────
    video_path = args.video.strip()

    if not video_path:
        print("\n[Auto-scan] No --video provided. Scanning media/reposts/ for .mp4...")
        video_path = find_any_local_video()

    if not video_path or not os.path.isfile(video_path):
        print(
            "\nERROR: No video file found.\n"
            "  • Provide one with:  python tools/test_yt_upload.py --video your_reel.mp4\n"
            "  • Or drop any .mp4 into media/reposts/ and re-run."
        )
        sys.exit(1)

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"\n[Video] {video_path}  ({file_size_mb:.1f} MB)")
    print(f"[Caption] {args.caption[:80]}...")

    # ── 2. Check credentials ──────────────────────────────────────────────────
    yt = YouTubePosterAgent()

    if not yt.is_configured():
        print(
            "\nERROR: YouTube credentials not found in .env\n"
            "  Required:\n"
            "    YT_CLIENT_ID=...\n"
            "    YT_CLIENT_SECRET=...\n"
            "    YT_REFRESH_TOKEN=...\n"
            "\n  If token is expired, regenerate with:  python tools/yt_auth.py"
        )
        sys.exit(1)

    print("\n[Auth] Credentials found. Attempting OAuth2 token refresh...")

    # ── 3. Upload ─────────────────────────────────────────────────────────────
    print("[Upload] Starting upload to YouTube...\n")
    video_id = yt.post(video_path=video_path, caption=args.caption)

    # ── 4. Result ─────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if video_id:
        print(f"SUCCESS! YouTube Short published.")
        print(f"  Video ID : {video_id}")
        print(f"  URL      : https://www.youtube.com/shorts/{video_id}")
        print(f"  Studio   : https://studio.youtube.com/video/{video_id}/edit")
        print()
        print("NOTE: YouTube Shorts may take a few minutes to appear")
        print("      in the Shorts feed after processing.")
    else:
        print("FAILED. Check the log output above for the error.")
        print()
        print("Common fixes:")
        print("  - Expired token     → python tools/yt_auth.py")
        print("  - Wrong credentials → double-check YT_CLIENT_ID / YT_CLIENT_SECRET")
        print("  - API not enabled   → enable 'YouTube Data API v3' in Google Cloud Console")
    print("=" * 60)


if __name__ == "__main__":
    main()
