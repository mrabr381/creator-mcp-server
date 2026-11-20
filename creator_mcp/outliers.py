"""Outlier analysis — pure functions, no network, no invented data.

Ported from the Open-vidIQ project (mrabr381/open-vidiq), whose numbers
were verified against its sample dataset: median 12,850 views, 5 outliers,
top outlier 4.86x ("The Tower of London's Lost Princes", 62,400 views).

Definitions:
- outlier_score = a video's views / the channel's median views.
  1.0x is exactly average; 2.0x means double the typical video.
- velocity = views / days since publish.
- keyword lift = how much more often a word appears in outlier videos
  than in the rest (1.0 = no difference).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import datetime, timezone

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "by", "at", "from", "is", "are", "was", "were", "be", "been", "it",
    "its", "this", "that", "these", "those", "i", "you", "he", "she",
    "we", "they", "my", "your", "his", "her", "our", "their", "as",
    "but", "not", "no", "so", "if", "then", "than", "too", "very",
    "can", "could", "will", "would", "should", "do", "does", "did",
    "have", "has", "had", "what", "when", "where", "who", "whom",
    "which", "why", "how", "about", "into", "over", "under", "out",
    "up", "down", "all", "any", "some", "more", "most", "other",
    "new", "one", "two", "also", "just", "like", "get", "got",
    "against", "between", "through", "during", "before", "after",
    "without", "within", "upon", "among", "towards", "toward",
    "read", "look", "looks", "check", "take", "takes", "give", "made",
    "make", "find", "say", "says", "said", "tell", "tells", "know",
    "think", "want", "need", "see", "saw", "come", "went", "go",
    "man", "woman", "people", "person", "nobody", "someone",
    "something", "anyone", "everyone", "thing", "things",
    "way", "ways", "day", "days", "year", "years", "time",
    "still", "even", "back", "first", "last", "every", "each",
    "really", "actually", "very", "quite", "rather", "truly",
    "definitely", "probably", "maybe", "perhaps", "almost", "nearly",
}

HOOK_WORDS = {
    "secret", "secrets", "revealed", "exposed", "hidden", "lost", "found",
    "mystery", "haunted", "cursed", "forbidden", "nobody", "never", "real",
    "truth", "shocking", "insane", "amazing", "finally", "actually",
}

WORD_RE = re.compile(r"[a-z][a-z\-']{1,}")


def tokenize(text: str) -> list[str]:
    """Lowercase words minus stopwords."""
    return [w for w in WORD_RE.findall((text or "").lower()) if w not in STOPWORDS]


def days_since(published_at: str, now: datetime | None = None) -> int:
    """Whole days between an ISO-8601 timestamp and now (min 1)."""
    now = now or datetime.now(timezone.utc)
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 1
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(1, (now - published).days)


def median_views(videos: list[dict]) -> float:
    views = sorted(v["views"] for v in videos)
    return float(statistics.median(views)) if views else 0.0


def enrich_videos(
    videos: list[dict], subscribers: int | None, now: datetime | None = None
) -> list[dict]:
    """Add outlier_score, views_per_sub and velocity to copies of the dicts."""
    median = median_views(videos)
    enriched = []
    for video in videos:
        days = days_since(video["published_at"], now=now)
        item = dict(video)
        item["days_old"] = days
        item["outlier_score"] = round(video["views"] / median, 2) if median else 0.0
        item["views_per_sub"] = (
            round(video["views"] / subscribers, 2) if subscribers else None
        )
        item["velocity"] = round(video["views"] / days, 1)
        item["is_short"] = (
            video.get("duration_seconds", 0) > 0 and video["duration_seconds"] < 60
        )
        enriched.append(item)
    return enriched


def find_outliers(
    enriched: list[dict], threshold: float = 2.0
) -> tuple[list[dict], list[dict]]:
    """(outliers, notable) — outliers score >= threshold, notable 1.5–threshold."""
    outliers = [v for v in enriched if v["outlier_score"] >= threshold]
    notable = [v for v in enriched if 1.5 <= v["outlier_score"] < threshold]
    outliers.sort(key=lambda v: v["outlier_score"], reverse=True)
    notable.sort(key=lambda v: v["outlier_score"], reverse=True)
    return outliers, notable


def keyword_analysis(enriched: list[dict]) -> dict:
    """Word frequency in titles + descriptions, and outlier lift.

    Words appearing in fewer than 2 videos are ignored — a single video
    proves nothing.
    """
    outliers, _ = find_outliers(enriched)
    outlier_ids = {v["video_id"] for v in outliers}
    counts: Counter = Counter()
    outlier_counts: Counter = Counter()
    for video in enriched:
        words = set(tokenize(video.get("title", "")) + tokenize(video.get("description", "")))
        for word in words:
            counts[word] += 1
            if video["video_id"] in outlier_ids:
                outlier_counts[word] += 1
    n_out = max(1, len(outliers))
    n_rest = max(1, len(enriched) - len(outliers))
    rows = []
    for word, total in counts.most_common():
        if total < 2:
            continue
        in_out = outlier_counts.get(word, 0)
        in_rest = total - in_out
        share_out = in_out / n_out
        share_rest = in_rest / n_rest if n_rest else 0
        lift = round(share_out / share_rest, 2) if share_rest > 0 else (99.0 if in_out else 0.0)
        rows.append(
            {
                "word": word,
                "videos": total,
                "in_outliers": in_out,
                "lift": lift,
            }
        )
    rows.sort(key=lambda r: (-r["lift"], -r["videos"], r["word"]))
    return {
        # Fully deterministic tie-breaks: set iteration order is randomised
        # per process, so ties must never depend on insertion order.
        "top_overall": sorted(rows, key=lambda r: (-r["videos"], -r["lift"], r["word"]))[:15],
        "highest_lift": rows[:10],
        "gap_words": [r["word"] for r in rows if r["lift"] >= 2.0 and r["videos"] >= 3],
    }


def title_bigrams(enriched: list[dict], outliers: list[dict], limit: int = 8) -> list[str]:
    """Two-word topic phrases from the channel's own titles.

    Single keywords make broken titles ("The Nobody: ..."). Real topics
    are phrases — "lost princes", "secret tunnels" — so seeds are adjacent
    non-stopwords from titles, ranked by frequency with an outlier bonus.
    Each phrase is one the channel has actually used.
    """
    counts: Counter = Counter()
    outlier_ids = {v["video_id"] for v in outliers}
    for video in enriched:
        words = WORD_RE.findall((video.get("title", "") or "").lower())
        words = [w for w in words if w not in STOPWORDS]
        for a, b in zip(words, words[1:]):
            phrase = f"{a} {b}"
            counts[phrase] += 2 if video["video_id"] in outlier_ids else 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [phrase for phrase, _ in ranked[:limit]]


def analyse_channel(
    channel: dict, videos: list[dict], now: datetime | None = None
) -> dict:
    """Full analysis dict for one channel + its videos."""
    enriched = enrich_videos(videos, channel.get("subscribers"), now=now)
    outliers, notable = find_outliers(enriched)
    keywords = keyword_analysis(enriched)
    return {
        "channel": {
            "title": channel.get("title"),
            "handle": channel.get("handle"),
            "subscribers": channel.get("subscribers"),
            "video_count": channel.get("video_count", len(videos)),
            "url": channel.get("url"),
        },
        "videos_analysed": len(enriched),
        "median_views": median_views(videos),
        "outliers": [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "views": v["views"],
                "outlier_score": v["outlier_score"],
                "velocity_per_day": v["velocity"],
                "days_old": v["days_old"],
                "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            }
            for v in outliers
        ],
        "notable": [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "views": v["views"],
                "outlier_score": v["outlier_score"],
                "velocity_per_day": v["velocity"],
            }
            for v in notable
        ],
        "keywords": keywords,
        "title_bigrams": title_bigrams(enriched, outliers),
        "all_videos": [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "views": v["views"],
                "published_at": v["published_at"],
                "outlier_score": v["outlier_score"],
                "velocity_per_day": v["velocity"],
            }
            for v in enriched
        ],
    }
