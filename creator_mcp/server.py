"""MCP server — five creator tools for AI coding assistants.

Transport: stdio by default (what Claude Desktop / Claude Code / Cursor
expect). `--transport streamable-http` (or `sse`) serves the same tools
over HTTP for clients that need it.

Every tool returns a JSON string. Failures are returned as
{"ok": false, "error": "..."} — never a traceback over the protocol.
Keys are read from the tool argument first, then the environment
(YOUTUBE_API_KEY / GEMINI_API_KEY); they are never logged.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import __version__
from .geo import GeoError, check_brand
from .outliers import analyse_channel
from .repurpose import repurpose
from .seo import SeoError, audit_page
from .titles import generate_titles
from .youtube import (
    YouTubeError,
    fetch_channel_videos,
    load_sample,
    resolve_channel,
)

mcp = MCPServer(
    name="creator-mcp-server",
    version=__version__,
    instructions=(
        "Creator-workflow tools: YouTube outlier research, transcript "
        "repurposing, title ideas, single-page SEO+GEO audit and AI-search "
        "brand checks. Tools that need an API key work in a documented "
        "sample mode without one — sample results are always labelled."
    ),
)


def _ok(payload: dict) -> str:
    return json.dumps({"ok": True, **payload}, indent=2, ensure_ascii=False)


def _fail(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, indent=2)


@mcp.tool()
def youtube_outlier_search(
    channel: str,
    max_videos: int = 25,
    api_key: str | None = None,
) -> str:
    """Find a YouTube channel's outlier videos (views vs channel median).

    Args:
        channel: Channel ID, @handle, URL or name (e.g. "@mysterylane").
        max_videos: How many recent videos to analyse (1-50, default 25).
        api_key: YouTube Data API v3 key. If omitted, YOUTUBE_API_KEY is
            used; if neither is set, the bundled sample channel is
            analysed instead (labelled "sample" mode).
    """
    try:
        key = api_key or os.environ.get("YOUTUBE_API_KEY")
        max_videos = max(1, min(50, int(max_videos)))
        if not key:
            sample_channel, sample_videos = load_sample()
            analysis = analyse_channel(sample_channel, sample_videos)
            analysis["mode"] = "sample"
            analysis["note"] = (
                "Sample mode — no API key set. This is the bundled fixture "
                "channel 'Mystery Lane' (@mysterylane, 24 videos), not live "
                f"data for {channel!r}. Set YOUTUBE_API_KEY (free, 10,000 "
                "units/day) or pass api_key for live data."
            )
            return _ok(analysis)
        live_channel = resolve_channel(key, channel)
        videos = fetch_channel_videos(key, live_channel, max_videos=max_videos)
        if not videos:
            return _fail(f"Channel {channel!r} has no public videos to analyse.")
        analysis = analyse_channel(live_channel, videos)
        analysis["mode"] = "live"
        return _ok(analysis)
    except (YouTubeError, ValueError) as exc:
        return _fail(str(exc))


@mcp.tool()
def repurpose_transcript(
    transcript: str,
    outputs: list[str] | None = None,
    transcript_path: str | None = None,
) -> str:
    """Turn one transcript into a blog post, X thread, LinkedIn post,
    newsletter, chapters and pull quotes — extractively, no AI needed.

    Args:
        transcript: The transcript text itself.
        outputs: Which outputs to generate (default: all). Any of
            blog_post, x_thread, linkedin_post, newsletter, chapters,
            pull_quotes.
        transcript_path: Read the transcript from this local file instead
            (used when the transcript is too long to paste).
    """
    try:
        text = transcript or ""
        if not text.strip() and transcript_path:
            path = Path(transcript_path).expanduser()
            if not path.is_file():
                return _fail(f"Transcript file not found: {transcript_path}")
            text = path.read_text(encoding="utf-8")
        result = repurpose(text, outputs)
        return _ok(result)
    except ValueError as exc:
        return _fail(str(exc))


@mcp.tool()
def title_ideas(
    topic: str,
    keywords: list[str] | None = None,
    count: int = 5,
) -> str:
    """Generate scored YouTube title ideas for a topic.

    Args:
        topic: The video topic, e.g. "lost princes".
        keywords: Optional niche keywords the titles should include.
        count: How many ideas (1-10, default 5).
    """
    try:
        count = max(1, min(10, int(count)))
        return _ok(generate_titles(topic, keywords, count))
    except ValueError as exc:
        return _fail(str(exc))


@mcp.tool()
def seo_audit_page(url: str) -> str:
    """Audit one web page for SEO + AI-search (GEO) readiness.

    Checks title, meta description, headings, canonical, Open Graph,
    image alt text, word count, JSON-LD schema and llms.txt. Returns a
    0-100 score with per-check results and a fix list.

    Args:
        url: The page URL, e.g. "https://toolenix.com".
    """
    try:
        return _ok(audit_page(url))
    except SeoError as exc:
        return _fail(str(exc))


@mcp.tool()
def geo_brand_check(
    brand: str,
    prompts: list[str] | None = None,
    api_key: str | None = None,
) -> str:
    """Check how often AI answers mention a brand across prompts.

    Args:
        brand: Brand name or domain, e.g. "toolenix.com".
        prompts: Questions to ask (default: the 10 bundled sample
            prompts about free online tools).
        api_key: Free Gemini API key. If omitted, GEMINI_API_KEY is used;
            if neither is set, the bundled sample answers are checked
            instead — sample mode only covers "toolenix.com".
    """
    try:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        return _ok(check_brand(brand, prompts, key))
    except GeoError as exc:
        return _fail(str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="creator-mcp-server",
        description="Creator MCP Server — YouTube, repurposing, SEO and GEO tools.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport to serve on (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000).")
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
