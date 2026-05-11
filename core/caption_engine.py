"""
core/caption_engine.py — Rule-based Instagram Caption Engine.

Pipeline:
  1. Clean    — strip hashtags, normalize whitespace
  2. Classify — keyword scoring → category
  3. Build    — [PRE-HOOK CTA] + [HOOK] + [BODY] + [HASHTAGS]

Caption structure:
  Line 1 (PRE-HOOK): Direct engagement ask — "🔥 Comment if this is you"
                     Visible before "...more" — drives engagement immediately.
  Line 2 blank
  Line 3+ (HOOK): Short, punchy opener (same category)
  blank
  (BODY): Original caption, cleaned
  blank
  (HASHTAGS): Category-specific

One CTA per caption (the pre-hook). No separate CTA at bottom.
All components drawn from the SAME category — never mixed.

Categories: dance | humor | lifestyle | trending | motivation | general
"""

import re
import random
from typing import Optional

# ── Category keyword banks (lowercase) ────────────────────────────────────────
_KEYWORDS: dict[str, list[str]] = {
    "dance": [
        "dance", "dancing", "choreography", "moves", "steps", "rhythm",
        "groove", "performance", "routine", "reel", "dancer", "beat",
        "transition", "freestyle", "shuffle", "hip hop", "ballet",
    ],
    "humor": [
        "funny", "lol", "lmao", "comedy", "joke", "laugh", "hilarious",
        "skit", "acting", "prank", "relatable", "mood", "same", "vibes",
        "cringe", "meme", "haha", "wtf", "omg",
    ],
    "lifestyle": [
        "lifestyle", "vlog", "day in my life", "get ready", "ootd",
        "fashion", "aesthetic", "coffee", "morning", "routine", "glow up",
        "self care", "travel", "food", "outfit", "beauty", "makeup",
    ],
    "trending": [
        "trending", "viral", "challenge", "duet", "trend", "fyp",
        "foryou", "explore", "hot", "new", "latest", "everyone is doing",
        "tiktok", "popular", "hit",
    ],
    "motivation": [
        "motivation", "inspire", "confidence", "boss", "grind", "hustle",
        "believe", "mindset", "goals", "success", "transformation",
        "glow up", "level up", "never give up", "dream big",
    ],
}

# ── Per-category content pools ─────────────────────────────────────────────────

# PRE-HOOK: The very first line — direct engagement ask.
# Shown before "...more" — drives comments immediately.
_PRE_HOOKS: dict[str, list[str]] = {
    "dance": [
        "Drop a 🔥 if you can do this move!",
        "Tag your dance partner 👇 — they NEED to see this!",
        "Comment 💃 if this made you want to get up and dance!",
        "Tag someone who dances like this 🙌",
    ],
    "humor": [
        "Comment 😂 if this is literally you!",
        "Tag the friend who would do this 👇😂",
        "Drop a 💀 if you couldn't stop laughing!",
        "Tag your funniest friend — they'll relate 😂👇",
    ],
    "lifestyle": [
        "Drop a ❤️ if your aesthetic is on point like this!",
        "Save this for inspo 📌 — you'll thank yourself later!",
        "Tag someone who lives like this 🔥👇",
        "Comment ✨ if this is your vibe!",
    ],
    "trending": [
        "Drop a 🔥 if you've seen this trend!",
        "Have you tried this yet? Comment below 👇",
        "Tag a friend who's obsessed with this trend 💥",
        "Comment YES if you're doing this next 👇🔥",
    ],
    "motivation": [
        "Drop a 💪 if this motivated you today!",
        "Tag someone who needs to hear this 👇",
        "Comment 🔥 if you're levelling up this year!",
        "Save this — you'll need this reminder 📌",
    ],
    "general": [
        "Drop a ❤️ if this made your day!",
        "Tag someone who needs to see this 👇",
        "Comment 🔥 if you loved this!",
        "Share this with someone who'd vibe with it 💥",
    ],
}

_HOOKS: dict[str, list[str]] = {
    "dance": [
        "This transition is EVERYTHING ✨",
        "When the beat drops and you just feel it 🎵🔥",
        "This choreography is living rent-free in my head 💃",
        "That's how you own the floor 🕺✨",
        "The footwork. The timing. PERFECT. 🔥",
    ],
    "humor": [
        "We all have that one friend 😂",
        "This is too real 💀",
        "I can't stop replaying this 😂🔁",
        "The accuracy is SCARY 😭😂",
        "Who approved this energy? Because I need it 😂✨",
    ],
    "lifestyle": [
        "This is the vibe we're chasing 🌟",
        "Soft life? Yes please. ✨",
        "Aesthetic unlocked 🔓💫",
        "This is what living well looks like ✨",
        "Goals. That's it. That's the caption. 🎯",
    ],
    "trending": [
        "Everyone's doing this — have you tried it yet? 🔥",
        "This is taking over the internet for a reason 💥",
        "The trend that just won't stop ✨",
        "Why is everyone obsessed with this? 👀",
        "Viral for a reason. Watch till the end 🔁",
    ],
    "motivation": [
        "This is your sign to go after it 💪",
        "Level up starts NOW 🚀",
        "The glow up is real and it's yours 🌟",
        "Your future self will thank you for this 🙌",
        "Stop waiting. Start doing. 🔥",
    ],
    "general": [
        "This content just hits different 🔥",
        "Watch this twice. You're welcome. 🎬",
        "The energy in this reel is unmatched ✨",
        "This is why I never put my phone down 📱🔥",
        "Best thing you'll see today 💥",
    ],
}

_HASHTAGS: dict[str, str] = {
    "dance": (
        "#DanceReels #DanceChallenge #Choreography #ReelItFeelIt #DancerLife "
        "#Trending #Entertainment #ViralReels #InstaDance #Shorts "
        "#ReelCreator #DanceVideo #HipHop #DanceMove #Groove"
    ),
    "humor": (
        "#FunnyReels #Comedy #Relatable #FunnyVideos #Humor "
        "#Trending #ViralReels #Entertainment #ReelItFeelIt #Shorts "
        "#Laugh #FunnyMoments #Comedyskits #Memes #FunContent"
    ),
    "lifestyle": (
        "#Lifestyle #Aesthetic #OOTD #VibeCheck #DailyLife "
        "#Trending #ReelItFeelIt #GlowUp #SelfCare #Shorts "
        "#LifestyleReels #FashionReels #AestheticVibes #Inspo #Goals"
    ),
    "trending": (
        "#Trending #ViralReels #FYP #ForYou #Explore "
        "#Entertainment #Shorts #ReelItFeelIt #ViralVideo #TrendAlert "
        "#NewTrend #Viral #PopularReels #HotRight Now #ReelCreator"
    ),
    "motivation": (
        "#Motivation #Inspiration #GlowUp #LevelUp #BossVibes "
        "#Mindset #Goals #Hustle #Trending #ViralReels "
        "#Shorts #ReelItFeelIt #Success #Believe #Confidence"
    ),
    "general": (
        "#Entertainment #ReelItFeelIt #ViralReels #Trending #Shorts "
        "#ReelCreator #FunnyReels #DanceReels #Lifestyle #Explore "
        "#ForYou #FYP #ViralVideo #ContentCreator #InstagramReels"
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

def clean_caption(text: str) -> str:
    """
    Remove hashtags and normalize whitespace.
    Keeps emojis intact — they add authentic personality.
    Returns cleaned body text only.
    """
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.rstrip() for l in text.splitlines()]
    return "\n".join(lines).strip()


def classify_caption(text: str) -> str:
    """
    Score the cleaned caption against each category's keyword bank.
    Returns the highest-scoring category name, or 'general' if no match.
    """
    lower = text.lower()
    scores: dict[str, int] = {cat: 0 for cat in _KEYWORDS}

    for category, keywords in _KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[category] += 1

    best_cat = max(scores, key=lambda c: scores[c])
    return best_cat if scores[best_cat] > 0 else "general"


def build_caption(
    original: str,
    add_credit: bool = False,
    credit_handle: str = "bulebarbie_official",
    category_override: Optional[str] = None,
) -> str:
    """
    Full pipeline:
      1. Clean the original caption (strip hashtags, normalize whitespace)
      2. Classify into a category via keyword scoring
      3. Assemble:
           [PRE-HOOK CTA]   ← direct engagement ask, shown before "...more"
           [HOOK]           ← short punchy opener
           [BODY]           ← cleaned original
           [HASHTAGS]       ← category-specific
      4. All components come from the SAME category — never mixed.
      5. One CTA only (the pre-hook). No repeat at the bottom.
    """
    body = clean_caption(original)

    if category_override and category_override in _KEYWORDS:
        category = category_override
    else:
        category = classify_caption(body)

    pre_hook = random.choice(_PRE_HOOKS[category])
    hook = random.choice(_HOOKS[category])
    hashtags = _HASHTAGS[category]

    parts = [
        pre_hook,    # "🔥 Comment if you can do this move!"
        "",
        hook,        # "This transition is EVERYTHING ✨"
        "",
        body,        # original caption (cleaned)
        "",
        hashtags,
    ]

    if add_credit:
        parts += ["", f"Via @{credit_handle} 🎬"]

    return "\n".join(parts)
