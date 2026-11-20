"""YouTube Data API v3 client + bundled sample fixture.

Free tier: $0, 10,000 quota units/day (channels.list / playlistItems.list /
videos.list cost 1 unit each; search costs 100, so channel resolution
prefers the cheap forHandle lookup and only falls back to search).

Nothing here invents data: every video dict comes straight from the API
response, or — in sample mode — from the bundled fixture, clearly labelled.
A missing/invalid key or an empty result is an error, never a fabricated
dataset.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT = 30
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


class YouTubeError(Exception):
    """User-facing error: bad input, missing key, or a failed API call."""


def load_sample() -> tuple[dict, list[dict]]:
    """Bundled fixture: the fictional 'Mystery Lane' channel, 24 videos."""
    channel = json.loads((SAMPLE_DIR / "channel.json").read_text(encoding="utf-8"))
    videos = json.loads((SAMPLE_DIR / "videos.json").read_text(encoding="utf-8"))
    return channel, videos


def _get(endpoint: str, api_key: str, **params) -> dict:
    params["key"] = api_key
    try:
        resp = requests.get(
            f"{API_BASE}/{endpoint}", params=params, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        raise YouTubeError(
            f"Could not reach the YouTube API ({exc}). Check your connection "
            "and try again."
        ) from exc
    if resp.status_code == 400:
        raise YouTubeError(
            "YouTube API rejected the request (400). Your API key may be "
            "invalid or the channel could not be found."
        )
    if resp.status_code == 403:
        detail = ""
        try:
            detail = resp.json()["error"]["errors"][0].get("reason", "")
        except Exception:
            pass
        if "quota" in detail.lower():
            raise YouTubeError(
                "YouTube API daily quota is exhausted (10,000 units/day on "
                "the free tier). Wait until tomorrow or use another Google "
                "Cloud project key."
            )
        raise YouTubeError(
            "YouTube API refused the request (403). The key may be invalid, "
            "the YouTube Data API v3 may not be enabled in your Google "
            "Cloud project, or the key is restricted to another API."
        )
    if resp.status_code != 200:
        raise YouTubeError(
            f"YouTube API returned HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?)?$"
)


def parse_duration_iso8601(value: str) -> int:
    """'PT12M34S' -> 754 seconds. Returns 0 for anything unparseable."""
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    return (
        parts.get("days", 0) * 86400
        + parts.get("hours", 0) * 3600
        + parts.get("minutes", 0) * 60
        + parts.get("seconds", 0)
    )


def extract_channel_ref(query: str) -> tuple[str, str]:
    """Return (kind, value) for a channel ID, @handle, URL, or plain name.

    kind is one of: 'id', 'handle', 'name'.
    """
    query = (query or "").strip()
    if not query:
        raise YouTubeError("Channel is empty — give a channel ID, @handle or URL.")
    if query.startswith("UC") and len(query) == 24:
        return "id", query
    if query.startswith("@"):
        return "handle", query[1:]
    parsed = urlparse(query)
    if parsed.netloc.endswith("youtube.com") or parsed.netloc == "youtu.be":
        path = parsed.path.strip("/")
        if path.startswith("@"):
            return "handle", path[1:]
        if path.startswith("channel/"):
            return "id", path.split("/")[1]
        if path:
            return "handle", path.split("/")[0]
    return "name", query


def _channel_from_item(item: dict) -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    subs_hidden = stats.get("hiddenSubscriberCount", False)
    return {
        "channel_id": item["id"],
        "title": snippet.get("title"),
        "handle": snippet.get("customUrl", "").lstrip("@") or None,
        "subscribers": None if subs_hidden else int(stats.get("subscriberCount", 0)),
        "subscribers_hidden": subs_hidden,
        "video_count": int(stats.get("videoCount", 0)),
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt"),
        "thumbnail_url": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
        "url": f"https://www.youtube.com/channel/{item['id']}",
        "_uploads_playlist": item.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads"),
    }


def resolve_channel(api_key: str, query: str) -> dict:
    """Resolve a channel ref to a channel dict (with _uploads_playlist)."""
    kind, value = extract_channel_ref(query)
    if kind == "id":
        data = _get("channels", api_key, part="snippet,statistics,contentDetails", id=value)
    elif kind == "handle":
        data = _get(
            "channels", api_key, part="snippet,statistics,contentDetails",
            forHandle=value,
        )
    else:
        data = _get(
            "search", api_key, part="snippet", q=value, type="channel", maxResults=1
        )
        if not data.get("items"):
            raise YouTubeError(f"No YouTube channel found for {query!r}.")
        channel_id = data["items"][0]["id"]["channelId"]
        data = _get(
            "channels", api_key, part="snippet,statistics,contentDetails",
            id=channel_id,
        )
    if not data.get("items"):
        raise YouTubeError(f"No YouTube channel found for {query!r}.")
    return _channel_from_item(data["items"][0])


def fetch_channel_videos(api_key: str, channel: dict, max_videos: int = 25) -> list[dict]:
    """Fetch up to max_videos from the channel's uploads playlist."""
    playlist_id = channel.get("_uploads_playlist")
    if not playlist_id:
        raise YouTubeError("This channel has no uploads playlist.")
    video_ids: list[str] = []
    page_token = ""
    while len(video_ids) < max_videos:
        params: dict = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_videos - len(video_ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get("playlistItems", api_key, **params)
        for item in data.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    videos = []
    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start : start + 50]
        data = _get(
            "videos", api_key, part="snippet,statistics,contentDetails",
            id=",".join(chunk),
        )
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            videos.append(
                {
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "duration_seconds": parse_duration_iso8601(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                    "thumbnail_url": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
                }
            )
    return videos
