"""GEO brand check — how often do AI answers mention your brand?

Two modes, always labelled:
- sample mode (no key): the bundled fixture — 10 prompts about free
  online tools and the sample answers that go with them. Only valid for
  the fixture brand (toolenix.com). Any other brand without a key is an
  error, not a fabricated result.
- live mode (BYO free Gemini key): each prompt is asked to Gemini
  (gemini-2.0-flash via the REST API, no SDK needed) and the answer is
  scanned for a mention of the brand.

Mention detection: the brand name and domain, matched case-insensitively
on word boundaries — "Toolenix" and "toolenix.com" both count; a
substring inside another word does not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
GEMINI_TIMEOUT = 30
SAMPLE_BRAND = "toolenix.com"


class GeoError(Exception):
    """User-facing error: bad input, missing key, or a failed API call."""


def _brand_patterns(brand: str) -> list[re.Pattern]:
    """Regexes matching the brand name / domain on word boundaries."""
    brand = (brand or "").strip().lower()
    brand = re.sub(r"^https?://", "", brand).removeprefix("www.")
    brand = brand.rstrip("/")
    name = brand.split(".")[0]
    patterns = {re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)}
    if "." in brand:
        patterns.add(re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE))
    return list(patterns)


def mentions_brand(answer: str, brand: str) -> bool:
    """True when any brand pattern matches the answer text."""
    return any(p.search(answer or "") for p in _brand_patterns(brand))


def _load_sample() -> tuple[list[str], dict[str, str]]:
    prompts_data = (SAMPLE_DIR / "sample_prompts.yaml").read_text(encoding="utf-8")
    prompts: list[str] = []
    for line in prompts_data.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            prompts.append(stripped[2:].strip().strip('"').strip("'"))
    answers = json.loads((SAMPLE_DIR / "sample_answers.json").read_text(encoding="utf-8"))
    return prompts, answers


def _ask_gemini(prompt: str, api_key: str) -> str:
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Answer briefly, as a helpful assistant would. "
                            f"Question: {prompt}"
                        )
                    }
                ]
            }
        ]
    }
    try:
        resp = requests.post(
            GEMINI_API_URL,
            params={"key": api_key},
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeoError(f"Could not reach the Gemini API ({exc}).") from exc
    if resp.status_code != 200:
        raise GeoError(
            f"Gemini API returned HTTP {resp.status_code}: "
            f"{resp.text[:200]} — check the API key."
        )
    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise GeoError("Gemini returned an unexpected response (no text).")


def check_brand(
    brand: str,
    prompts: list[str] | None = None,
    api_key: str | None = None,
) -> dict:
    """Check brand mentions across prompts. Returns a result dict."""
    brand = (brand or "").strip()
    if not brand:
        raise GeoError("Brand is empty — give a brand name or domain, e.g. 'toolenix.com'.")
    if prompts is not None and not prompts:
        raise GeoError("Prompts list is empty — give at least one prompt.")
    if api_key:
        mode = "live"
        prompt_list = prompts or _load_sample()[0]
        answers = {prompt: _ask_gemini(prompt, api_key) for prompt in prompt_list}
    else:
        mode = "sample"
        sample_prompts, sample_answers = _load_sample()
        if brand.lower().rstrip("/").removeprefix("https://").removeprefix(
            "http://"
        ).removeprefix("www.") not in (SAMPLE_BRAND, "toolenix"):
            raise GeoError(
                f"Sample mode only covers the bundled fixture brand "
                f"'{SAMPLE_BRAND}' (10 prompts, 4 mentions). To check "
                f"{brand!r}, provide a free Gemini API key — set "
                "GEMINI_API_KEY or pass api_key."
            )
        prompt_list = prompts or sample_prompts
        answers = {}
        for prompt in prompt_list:
            if prompt not in sample_answers:
                raise GeoError(
                    f"Sample mode has no answer for prompt {prompt!r}. "
                    "Use the bundled prompts or provide a Gemini API key."
                )
            answers[prompt] = sample_answers[prompt]
    results = []
    mentioned = 0
    for prompt in prompt_list:
        answer = answers[prompt]
        hit = mentions_brand(answer, brand)
        mentioned += 1 if hit else 0
        results.append(
            {
                "prompt": prompt,
                "mentioned": hit,
                "excerpt": (answer[:200] + "…") if len(answer) > 200 else answer,
            }
        )
    total = len(prompt_list)
    rate = round(mentioned / total * 100, 1) if total else 0.0
    return {
        "brand": brand,
        "mode": mode,
        "prompts_checked": total,
        "mentions": mentioned,
        "mention_rate_percent": rate,
        "results": results,
        "note": (
            "Sample mode: bundled fixture answers (Toolenix, 4/10 = 40%), "
            "not a live AI call. Live mode: one Gemini call per prompt — "
            "answers vary run to run, so treat the rate as a snapshot, "
            "not a stable metric."
            if mode == "sample"
            else "Live Gemini answers — a snapshot; re-run to see drift."
        ),
    }
