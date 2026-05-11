import os
import sys
import requests
import json
from pprint import pprint
from dotenv import load_dotenv

# Fix windows terminal encoding for emojis
sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

LONG_LIVED_USER_TOKEN = os.environ.get("META_ACCESS_TOKEN") or os.environ.get("LONG_LIVED_USER_TOKEN")

if not LONG_LIVED_USER_TOKEN:
    print("ERROR: Could not find META_ACCESS_TOKEN or LONG_LIVED_USER_TOKEN in .env")
    exit(1)

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


def get_json(url, params=None):
    r = requests.get(url, params=params)
    try:
        return r.json()
    except:
        return {"error": r.text}


# =========================
# GET ALL FACEBOOK PAGES
# =========================

pages = get_json(
    f"{BASE_URL}/me/accounts",
    {
        "access_token": LONG_LIVED_USER_TOKEN
    }
)

final_output = []

for page in pages.get("data", []):

    page_name = page.get("name")
    page_id = page.get("id")
    page_token = page.get("access_token")
    page_category = page.get("category")
    page_tasks = page.get("tasks")

    # =========================
    # PAGE DETAILS
    # =========================

    page_details = get_json(
        f"{BASE_URL}/{page_id}",
        {
            "fields": ",".join([
                "id",
                "name",
                "username",
                "link",
                "followers_count",
                "fan_count",
                "verification_status",
                "about",
                "category",
                "website",
                "picture"
            ]),
            "access_token": page_token
        }
    )

    # =========================
    # INSTAGRAM BUSINESS ACCOUNT
    # =========================

    ig_data = get_json(
        f"{BASE_URL}/{page_id}",
        {
            "fields": "instagram_business_account",
            "access_token": page_token
        }
    )

    ig_user_id = None
    ig_details = None

    if ig_data.get("instagram_business_account"):

        ig_user_id = ig_data["instagram_business_account"]["id"]

        ig_details = get_json(
            f"{BASE_URL}/{ig_user_id}",
            {
                "fields": ",".join([
                    "id",
                    "username",
                    "name",
                    "biography",
                    "followers_count",
                    "follows_count",
                    "media_count",
                    "profile_picture_url",
                    "website"
                ]),
                "access_token": page_token
            }
        )

    final_output.append({
        "facebook_page": {
            "page_name": page_name,
            "page_id": page_id,
            "page_category": page_category,
            "page_tasks": page_tasks,
            "page_access_token": page_token,

            "details": page_details
        },

        "instagram_account": {
            "ig_user_id": ig_user_id,
            "details": ig_details
        }
    })

# =========================
# PRINT CLEAN OUTPUT
# =========================

print("\n" + "="*100)
print("META ACCOUNTS SUMMARY")
print("="*100 + "\n")

for idx, acc in enumerate(final_output, start=1):

    print(f"\n{'#'*100}")
    print(f"ACCOUNT #{idx}")
    print(f"{'#'*100}\n")

    fb = acc["facebook_page"]
    ig = acc["instagram_account"]

    print("FACEBOOK PAGE")
    print("-"*50)

    pprint(fb)

    print("\nINSTAGRAM ACCOUNT")
    print("-"*50)

    pprint(ig)

    print("\n")

# =========================
# OPTIONAL JSON SAVE
# =========================

with open("meta_accounts_dump.json", "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4, ensure_ascii=False)

print("Saved: meta_accounts_dump.json")
