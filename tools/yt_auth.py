"""
tools/yt_auth.py — One-time OAuth2 flow to generate a YouTube refresh token.

Run this script ONCE locally in your browser.
It will open a browser window asking you to log in to your Google account
and grant the app permission to upload to YouTube.

On success, it prints your YT_REFRESH_TOKEN — copy it to your .env file.
You will never need to run this again unless the token is revoked.

Usage:
    python tools/yt_auth.py

Requirements:
    pip install google-auth-oauthlib
"""

import os
import sys

# ── Load .env if present ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Not a hard dependency for this script

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: google-auth-oauthlib is not installed.")
    print("Run:  pip install google-auth-oauthlib")
    sys.exit(1)


# ── YouTube upload scope ──────────────────────────────────────────────────────
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    print("=" * 60)
    print("  YouTube OAuth2 — Refresh Token Generator")
    print("=" * 60)

    # 1. Read credentials (from .env or prompt)
    client_id = os.getenv("YT_CLIENT_ID") or _prompt("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET") or _prompt("YT_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\nERROR: Both YT_CLIENT_ID and YT_CLIENT_SECRET are required.")
        sys.exit(1)

    # 2. Build the OAuth2 flow (uses a local server to receive the callback)
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)

    print("\n→ Opening browser for Google sign-in...")
    print("  Log in with the Google account that owns your YouTube channel.\n")

    # 3. Run the local web server flow — opens your browser automatically
    creds = flow.run_local_server(
        port=0,
        prompt="consent",          # Force consent screen so refresh_token is always returned
        access_type="offline",
        open_browser=True,
    )

    # 4. Print the result
    print("\n" + "=" * 60)
    print("✅ Authentication successful!")
    print("\nAdd these lines to your .env file:")
    print("-" * 60)
    print(f"YT_CLIENT_ID={client_id}")
    print(f"YT_CLIENT_SECRET={client_secret}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    print("-" * 60)
    print("\n⚠️  Keep your refresh token secret — treat it like a password.")
    print("=" * 60)


def _prompt(key: str) -> str:
    """Prompt the user to enter a credential value interactively."""
    value = input(f"Enter your {key}: ").strip()
    return value


if __name__ == "__main__":
    main()
