"""Single-page SEO + GEO audit — fetch a URL, score what is really there.

A focused subset of the SEO + GEO Site Audit CLI's checks (mrabr381/
seo-geo-audit-cli), run against one page instead of a whole crawl.
Every score is computed from the live HTML — nothing is hardcoded.

Checks (weight in brackets, score 0.0-1.0 each):
- https [2], title present [2], title length 30-60 [2],
  meta description 50-160 [2], single H1 [2], canonical [1],
  Open Graph tags [1], image alt coverage [2], word count [2],
  JSON-LD FAQ/HowTo schema [1], llms.txt [2].
Total weight 19; final score = earned / 19 * 100, rounded.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment

REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (compatible; CreatorMCPServer/0.1; +https://github.com/"
    "mrabr381/creator-mcp-server)"
)

DATE_RE = re.compile(
    r"\b(19|20)\d{2}[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b"
    r"|\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+(19|20)\d{2}\b",
    re.IGNORECASE,
)


class SeoError(Exception):
    """User-facing error: bad URL or an unreachable page."""


def _fetch(url: str) -> tuple[str, BeautifulSoup]:
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
    except requests.RequestException as exc:
        raise SeoError(f"Could not fetch {url} ({exc}).") from exc
    if resp.status_code != 200:
        raise SeoError(f"{url} returned HTTP {resp.status_code}, not 200.")
    if "text/html" not in resp.headers.get("Content-Type", "text/html"):
        raise SeoError(f"{url} is not an HTML page.")
    return resp.text, BeautifulSoup(resp.text, "html.parser")


def _visible_text(soup: BeautifulSoup) -> str:
    parts = []
    for element in soup.find_all(string=True):
        # HTML comments are not visible text — the old version counted
        # them, so editing a comment changed the word count.
        if isinstance(element, Comment):
            continue
        if element.parent.name in ("script", "style", "noscript"):
            continue
        text = element.strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _check_llms_txt(url: str) -> tuple[float, str]:
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    try:
        resp = requests.get(
            llms_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
    except requests.RequestException:
        return 0.0, f"llms.txt unreachable at {llms_url}"
    if resp.status_code == 200 and len(resp.text.strip()) > 50:
        return 1.0, f"llms.txt present ({len(resp.text)} bytes)"
    return 0.0, f"llms.txt missing (HTTP {resp.status_code} at {llms_url})"


def audit_page(url: str) -> dict:
    """Audit one page. Returns a dict with score, checks and fixes."""
    url = (url or "").strip()
    if not url:
        raise SeoError("URL is empty — give a page URL to audit.")
    if not url.startswith(("http://", "https://")):
        raise SeoError(f"{url!r} is not a URL — it must start with http:// or https://.")
    html, soup = _fetch(url)
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if title_tag else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    meta_desc = (meta_desc_tag.get("content") or "").strip() if meta_desc_tag else ""
    h1s = soup.find_all("h1")
    canonical = soup.find("link", attrs={"rel": "canonical"})
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    images = soup.find_all("img")
    with_alt = [img for img in images if (img.get("alt") or "").strip()]
    words = len(_visible_text(soup).split())

    json_ld_types: set[str] = set()
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and "@type" in item:
                json_ld_types.add(str(item["@type"]))
            if isinstance(item, dict) and "@graph" in item:
                for node in item["@graph"]:
                    if isinstance(node, dict) and "@type" in node:
                        json_ld_types.add(str(node["@type"]))

    llms_score, llms_detail = _check_llms_txt(url)

    checks: list[dict] = []

    def add(name: str, weight: int, score: float, detail: str, fix: str | None = None):
        checks.append(
            {
                "check": name,
                "weight": weight,
                "score": score,
                "detail": detail,
                "fix": fix,
            }
        )

    add("https", 2, 1.0 if urlparse(url).scheme == "https" else 0.0,
        "Served over HTTPS" if urlparse(url).scheme == "https" else "Served over plain HTTP",
        None if urlparse(url).scheme == "https" else "Serve the page over HTTPS.")
    add("title_present", 2, 1.0 if title else 0.0,
        f"Title: {title[:80]!r}" if title else "No <title> tag",
        None if title else "Add a <title> tag.")
    add("title_length", 2,
        1.0 if 30 <= len(title) <= 60 else (0.5 if title and 20 <= len(title) < 30 else 0.0),
        f"Title is {len(title)} characters (ideal 30-60)",
        None if 30 <= len(title) <= 60 else "Rewrite the title to 30-60 characters.")
    add("meta_description", 2,
        1.0 if 50 <= len(meta_desc) <= 160 else 0.0,
        f"Meta description is {len(meta_desc)} characters (ideal 50-160)"
        if meta_desc else "No meta description",
        None if 50 <= len(meta_desc) <= 160 else "Write a 50-160 character meta description.")
    add("single_h1", 2,
        1.0 if len(h1s) == 1 else 0.0,
        f"{len(h1s)} <h1> tag(s) on the page",
        None if len(h1s) == 1 else "Use exactly one <h1> per page.")
    add("canonical", 1, 1.0 if canonical else 0.0,
        "Canonical link present" if canonical else "No canonical link",
        None if canonical else "Add a canonical link.")
    og_score = (0.5 if og_title else 0.0) + (0.5 if og_desc else 0.0)
    add("open_graph", 1, og_score,
        f"og:title {'present' if og_title else 'missing'}, "
        f"og:description {'present' if og_desc else 'missing'}",
        None if og_score == 1.0 else "Add og:title and og:description.")
    alt_score = (len(with_alt) / len(images)) if images else 1.0
    add("image_alt", 2, round(alt_score, 2),
        f"{len(with_alt)}/{len(images)} images have alt text"
        if images else "No images on the page",
        None if alt_score == 1.0 else "Write descriptive alt text for every image.")
    word_score = 1.0 if words >= 300 else (0.5 if words >= 100 else 0.0)
    add("word_count", 2, word_score,
        f"{words} visible words (300+ is a good minimum for an article page)",
        None if words >= 300 else "Expand thin pages to 300+ words.")
    geo_types = json_ld_types & {"FAQPage", "HowTo", "Article", "WebPage"}
    add("json_ld_schema", 1, 1.0 if geo_types else 0.0,
        f"Schema found: {', '.join(sorted(geo_types))}" if geo_types
        else "No FAQPage/HowTo/Article JSON-LD schema",
        None if geo_types else "Add FAQPage or HowTo JSON-LD so AI answers can cite the page.")
    add("llms_txt", 2, llms_score, llms_detail,
        None if llms_score == 1.0 else "Add an llms.txt file at the site root.")

    total_weight = sum(c["weight"] for c in checks)
    earned = sum(c["weight"] * c["score"] for c in checks)
    score = round(earned / total_weight * 100) if total_weight else 0
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    return {
        "url": url,
        "score": score,
        "grade": grade,
        "checks": checks,
        "fixes": [c["fix"] for c in checks if c["fix"]],
        "facts": {
            "title": title,
            "title_length": len(title),
            "meta_description_length": len(meta_desc),
            "h1_count": len(h1s),
            "images": len(images),
            "images_with_alt": len(with_alt),
            "words": words,
            "json_ld_types": sorted(json_ld_types),
            "has_date": bool(DATE_RE.search(_visible_text(soup))),
        },
        "note": (
            "Single-page audit: title, meta, headings, alt text, schema and "
            "llms.txt only. For a full-site crawl use the SEO + GEO Site "
            "Audit CLI (mrabr381/seo-geo-audit-cli). Speed is not measured "
            "here — page size and render-blocking resources are only a proxy."
        ),
    }
