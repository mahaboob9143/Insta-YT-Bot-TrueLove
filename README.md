# InstaAgent — Cloud Repost Pipeline

A fully autonomous Instagram repost agent that reposts entertainment & dance content from public creators, rewrites captions using a rule-based engagement engine, and publishes automatically via the official Meta Graph API.

**Source Account:** [@bulebarbie_official](https://www.instagram.com/bulebarbie_official/)
**Niche:** Entertainment / Dance / Reel Creator

## Features
- **3-Tier Fallback Architecture:** Guaranteed daily posts via a robust fallback system:
  1. **Auto-Scrape:** Autonomously scrapes public creator content using `instaloader`.
  2. **Manual Queue (Google Sheets):** If scraping fails, automatically falls back to a public Google Sheet to fetch specific user-provided URLs.
  3. **Duplicate Safeguard:** If the manual queue is empty, forcefully grabs an older post to maintain daily consistency.
- **Alternating Pattern Logic:** Strictly enforces an alternating `Image -> Reel -> Image -> Reel` schedule, even when fetching URLs manually from Google Sheets.
- **Rule-based Captioning:** Categorizes content (dance/humor/lifestyle/trending/motivation) and weaves engaging English hooks/CTAs automatically.
- **Auto Image Optimization:** Filters out non-compliant aspect ratios and prepares assets for Instagram.
- **Cloud-native Uploads:** Uses Cloudinary to host images publicly so the Meta Graph API can pull them.
- **Deduplication:** Excel-based tracker to ensure content is never reposted twice.
- **YouTube Shorts:** Simultaneously publishes reels to YouTube as Shorts (Entertainment category).
- **Headless Execution:** Designed to run in CI/CD (GitHub Actions) with randomized cron scheduling.

## Local Setup

1. Create a `.env` file containing only the parameters required for your features:
   - `META_ACCESS_TOKEN` & `IG_ACCOUNT_ID` (Required for publishing)
   - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` (Required for hosting public images)
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the repost pipeline once:
   ```bash
   python main.py --repost
   ```

## Cloud Deployment
See [DEPLOYMENT.md](DEPLOYMENT.md) for full instructions on running this on GitHub Actions for free.
