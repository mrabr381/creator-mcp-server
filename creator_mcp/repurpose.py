"""Extractive content repurposing — no AI, no invented content.

Ported from the Creator Repurpose Agent (mrabr381/creator-repurpose-agent).

Quality contract:
- Every pull-quote is an EXACT sentence copied from the transcript.
- Every chapter timestamp comes from a real ``[MM:SS]`` marker in the
  transcript. When the transcript has no timing at all, chapters are
  labelled honestly as approximate, estimated from word count at ~150 wpm.
- The blog post, newsletter and LinkedIn post only use points that
  actually appear in the transcript. The generator is extractive: it
  ranks the transcript's own sentences and reuses them.
"""

from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = set(
    "a an the and or but if then else when while of to in on for with at by from as is are "
    "was were be been being have has had do does did will would shall should can could may "
    "might must i you he she it we they this that these those there here what which who whom "
    "how why not no yes so very just really actually basically literally like get got gets "
    "getting make makes made take takes took taking know knows knew think thinks thought "
    "feel feels felt want wants wanted need needs needed say says said see sees saw go goes "
    "going gone come comes came thing things lot lots way ways part parts one two three "
    "first second third every each all also still even back around over under into out up "
    "down off about between through after before during without within upon per via etc "
    "really kinda sorta um uh yeah okay right most more less much many few "
    "own same other another any some no nor".split()
)

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]")
MIN_QUOTE_WORDS = 8
MAX_QUOTE_WORDS = 38
WORDS_PER_MINUTE = 150


def _sentences(text: str) -> list[str]:
    """Split text into clean, de-duplicated sentences (min 4 words)."""
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    parts = SENTENCE_RE.split(clean)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        sentence = part.strip()
        if len(sentence.split()) < 4:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
    return out


def _score_sentences(sentences: list[str]) -> list[tuple[float, str]]:
    """Rank sentences by content-word frequency (extractive summarisation)."""
    words: Counter[str] = Counter()
    for sentence in sentences:
        for word in re.findall(r"[a-z][a-z\-']+", sentence.lower()):
            if word not in STOPWORDS:
                words[word] += 1
    scored = []
    for sentence in sentences:
        content = [w for w in re.findall(r"[a-z][a-z\-']+", sentence.lower())
                   if w not in STOPWORDS]
        if not content:
            continue
        score = sum(words[w] for w in content) / math.sqrt(len(content))
        scored.append((score, sentence))
    scored.sort(key=lambda pair: -pair[0])
    return scored


def _extract_timestamps(text: str) -> list[tuple[str, str]]:
    """[(timestamp, following sentence)] for [MM:SS] markers in the text."""
    markers = [(m.start(), m.group(0)) for m in TIMESTAMP_RE.finditer(text)]
    if not markers:
        return []
    chapters = []
    for i, (pos, stamp) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        chunk = text[pos + len(stamp) : end].strip()
        first = _sentences(chunk)
        chapters.append((stamp, first[0] if first else ""))
    return chapters


def _approximate_chapters(sentences: list[str]) -> list[tuple[str, str]]:
    """Chapters estimated from word count at ~150 wpm, labelled approximate."""
    total_words = sum(len(s.split()) for s in sentences)
    if total_words < 200:
        return []
    n = max(2, min(6, total_words // 250))
    per = max(1, len(sentences) // n)
    chapters = []
    for i in range(n):
        idx = min(i * per, len(sentences) - 1)
        words_before = sum(len(s.split()) for s in sentences[:idx])
        minutes = words_before / WORDS_PER_MINUTE
        stamp = f"[{int(minutes):02d}:{int((minutes % 1) * 60):02d} approx]"
        chapters.append((stamp, sentences[idx]))
    return chapters


def _split_x_thread(text: str, limit: int = 280) -> list[str]:
    """Split text into numbered posts, each <= limit chars, on word boundaries."""
    words = text.split()
    posts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                posts.append(current)
            current = word
    if current:
        posts.append(current)
    numbered = [f"{post} {i + 1}/{len(posts)}" for i, post in enumerate(posts)]
    # Re-check: numbering adds a few chars; re-split if any post overflows.
    if any(len(p) > limit for p in numbered):
        return _split_x_thread(text, limit - 8)
    return numbered


def repurpose(transcript: str, outputs: list[str] | None = None) -> dict:
    """Generate the requested outputs from a transcript. Deterministic.

    outputs may include: blog_post, x_thread, linkedin_post, newsletter,
    chapters, pull_quotes. Default: all of them.
    """
    text = (transcript or "").strip()
    if len(text) < 100:
        raise ValueError(
            "Transcript is too short (under 100 characters). Paste a real "
            "transcript — at least a few sentences."
        )
    wanted = set(outputs or ["blog_post", "x_thread", "linkedin_post",
                             "newsletter", "chapters", "pull_quotes"])
    sentences = _sentences(re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*", "", text))
    if len(sentences) < 3:
        raise ValueError(
            "Could not find enough sentences in the transcript "
            f"({len(sentences)} found). Check the text and try again."
        )
    ranked = _score_sentences(sentences)
    top = [s for _, s in ranked]
    result: dict[str, object] = {
        "engine": "local-extractive",
        "note": (
            "Local extractive generation — no AI key needed. Quotes are "
            "exact sentences from your transcript; nothing was invented."
        ),
        "sentences_found": len(sentences),
        "words": len(text.split()),
    }

    if "pull_quotes" in wanted:
        quotes = [s for s in top
                  if MIN_QUOTE_WORDS <= len(s.split()) <= MAX_QUOTE_WORDS][:5]
        result["pull_quotes"] = quotes

    if "chapters" in wanted:
        stamped = _extract_timestamps(text)
        if stamped:
            result["chapters"] = [
                {"timestamp": stamp, "title": title, "approximate": False}
                for stamp, title in stamped
            ]
        else:
            result["chapters"] = [
                {"timestamp": stamp, "title": title, "approximate": True}
                for stamp, title in _approximate_chapters(sentences)
            ]

    if "blog_post" in wanted:
        hook = top[0]
        body = top[1:6]
        result["blog_post"] = (
            f"# {hook}\n\n"
            + "\n\n".join(body)
            + "\n\n---\n*Generated extractively from the transcript — "
            "every sentence above appears in the original recording.*"
        )

    if "newsletter" in wanted:
        result["newsletter"] = (
            "The big idea:\n" + top[0] + "\n\n3 keepers:\n"
            + "\n".join(f"- {s}" for s in top[1:4])
            + "\n\nVerbatim quote:\n> " + (top[4] if len(top) > 4 else top[0])
        )

    if "linkedin_post" in wanted:
        takeaways = top[1:4]
        result["linkedin_post"] = (
            f"{top[0]}\n\n"
            + "\n".join(f"→ {s}" for s in takeaways)
            + "\n\nWhat is the one thing you would add from your own "
            "experience?"
        )

    if "x_thread" in wanted:
        thread_text = " ".join(top[:8])
        result["x_thread"] = _split_x_thread(thread_text)

    return result
