"""Outlier-maths tests for creator-mcp-server.

The numbers come from the bundled fixture channel (Mystery Lane,
@-mysterylane, 24 videos in sample_data/videos.json) — the same dataset
the smoke test and the Open-vidIQ project verified: median 12,850 views,
5 outliers, top outlier 4.86x.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from creator_mcp.outliers import (
    analyse_channel,
    days_since,
    enrich_videos,
    find_outliers,
    keyword_analysis,
    median_views,
    title_bigrams,
)

ROOT = Path(__file__).resolve().parent.parent
# Pinned "now": 656 days after the top video was published
# (2025-02-01T16:00Z), so its velocity is the documented 95.1/day.
# Velocity is views / days-since-publish, so it changes every day —
# pinning `now` keeps the test deterministic.
NOW = datetime(2026, 11, 19, 16, 0, 0, tzinfo=timezone.utc)


def _load():
    channel = json.loads((ROOT / "sample_data" / "channel.json").read_text())
    videos = json.loads((ROOT / "sample_data" / "videos.json").read_text())
    return channel, videos


def test_median_views_is_12850():
    _, videos = _load()
    assert median_views(videos) == 12850.0


def test_median_of_no_videos_is_zero():
    assert median_views([]) == 0.0


def test_five_outliers_and_top_is_tower_of_london_at_4_86x():
    channel, videos = _load()
    result = analyse_channel(channel, videos, now=NOW)
    assert result["videos_analysed"] == 24
    assert result["median_views"] == 12850.0
    assert len(result["outliers"]) == 5
    top = result["outliers"][0]
    assert top["title"].startswith("The Tower of London's Lost Princes")
    assert top["views"] == 62400
    assert top["outlier_score"] == 4.86
    assert top["velocity_per_day"] == 95.1


def test_outliers_sorted_by_score_descending():
    channel, videos = _load()
    result = analyse_channel(channel, videos, now=NOW)
    scores = [v["outlier_score"] for v in result["outliers"]]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 2.0 for s in scores)


def test_gap_words_are_found_and_london():
    channel, videos = _load()
    result = analyse_channel(channel, videos, now=NOW)
    assert result["keywords"]["gap_words"] == ["found", "london"]


def test_title_bigrams_include_lost_princes():
    channel, videos = _load()
    result = analyse_channel(channel, videos, now=NOW)
    assert "lost princes" in result["title_bigrams"]


def test_find_outliers_threshold_splits_outliers_from_notable():
    _, videos = _load()
    enriched = enrich_videos(videos, subscribers=12400, now=NOW)
    outliers, notable = find_outliers(enriched)
    assert len(outliers) == 5
    assert len(notable) == 2
    assert all(v["outlier_score"] >= 2.0 for v in outliers)
    assert all(1.5 <= v["outlier_score"] < 2.0 for v in notable)


def test_keyword_lift_is_real_maths_not_a_guess():
    _, videos = _load()
    enriched = enrich_videos(videos, subscribers=12400, now=NOW)
    analysis = keyword_analysis(enriched)
    found = next(r for r in analysis["highest_lift"] if r["word"] == "found")
    # "found" appears in 3 videos, 2 of them outliers: heavily
    # over-represented in outliers, so lift must exceed 2.
    assert found["videos"] == 3
    assert found["in_outliers"] == 2
    assert found["lift"] == 7.6


def test_days_since_handles_bad_timestamps():
    assert days_since("not-a-date", now=NOW) == 1
    assert days_since("2025-02-01T16:00:00Z", now=NOW) == 656
