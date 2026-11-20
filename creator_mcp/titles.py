"""Title ideas — deterministic, grounded in the topic you give.

A generated title is a *suggestion*, not a fact. Every title contains
the topic phrase (or a keyword you supplied), so nothing drifts off-topic.

Scoring (0-100, fully deterministic — same input, same score):
- base 40
- +12  length 40-60 characters (the YouTube sweet spot); +6 for 30-39 or
  61-70; otherwise +0
- +12  contains a hook word (secret, revealed, hidden, lost, found,
  mystery, nobody, truth, finally, shocking, real, haunted, cursed)
- +10  asks a question (ends with "?")
- +8   contains a number
- +8   contains a keyword supplied by the caller
- +6   contains a second hook/power word
- +4   starts with "The", "Why" or "What" (classic title openers)
Capped at 100.
"""

from __future__ import annotations

import re

HOOK_WORDS = {
    "secret", "secrets", "revealed", "exposed", "hidden", "lost", "found",
    "mystery", "haunted", "cursed", "forbidden", "nobody", "never", "real",
    "truth", "shocking", "insane", "amazing", "finally", "actually",
}

TEMPLATES = [
    "The {topic} — What Really Happened?",
    "Why {topic} Still Haunts Us",
    "{topic}: The Secret Nobody Tells You",
    "What {topic} Reveals About {keyword}?",
    "The {topic} Mystery, Finally Solved?",
    "7 Things {topic} Teaches Us About {keyword}",
    "I Spent a Month Investigating {topic} — Here's What I Found",
    "The {topic} Story Nobody Believed — Until Now",
    "{topic}: 5 Clues Everyone Missed",
    "Is {topic} the Greatest Mystery in {keyword}?",
]


def _title_case(phrase: str) -> str:
    """Title-case a topic phrase, keeping small words lowercase mid-title."""
    small = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with"}
    words = phrase.strip().split()
    out = []
    for i, word in enumerate(words):
        if i > 0 and word.lower() in small:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def score_title(title: str, keywords: list[str]) -> dict:
    """Score one title and explain the score. Deterministic."""
    score = 40
    reasons: list[str] = ["base 40"]
    length = len(title)
    if 40 <= length <= 60:
        score += 12
        reasons.append("+12 length 40-60 chars")
    elif 30 <= length < 40 or 60 < length <= 70:
        score += 6
        reasons.append("+6 length 30-39 or 61-70 chars")
    lowered = title.lower()
    words = set(re.findall(r"[a-z][a-z\-']+", lowered))
    hooks = words & HOOK_WORDS
    if hooks:
        score += 12
        reasons.append(f"+12 hook word ({sorted(hooks)[0]})")
    if len(hooks) >= 2:
        score += 6
        reasons.append("+6 second hook word")
    if title.rstrip().endswith("?"):
        score += 10
        reasons.append("+10 asks a question")
    if re.search(r"\b\d+\b", title):
        score += 8
        reasons.append("+8 contains a number")
    if keywords and any(k.lower() in lowered for k in keywords):
        score += 8
        reasons.append("+8 contains a supplied keyword")
    if title.startswith(("The ", "Why ", "What ")):
        score += 4
        reasons.append("+4 classic opener (The/Why/What)")
    score = min(100, score)
    return {"title": title, "score": score, "length_chars": length, "reasons": reasons}


def generate_titles(
    topic: str, keywords: list[str] | None = None, count: int = 5
) -> dict:
    """Generate up to `count` scored title ideas for a topic."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Topic is empty — give a topic, e.g. 'lost princes'.")
    if len(topic) > 80:
        raise ValueError("Topic is too long (over 80 characters).")
    keywords = [k.strip() for k in (keywords or []) if k and k.strip()][:5]
    topic_title = _title_case(topic)
    keyword_title = _title_case(keywords[0]) if keywords else topic_title
    titles: list[dict] = []
    seen: set[str] = set()
    for template in TEMPLATES:
        if len(titles) >= count:
            break
        title = template.format(topic=topic_title, keyword=keyword_title)
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        titles.append(score_title(title, keywords))
    titles.sort(key=lambda t: -t["score"])
    return {
        "topic": topic,
        "keywords": keywords,
        "titles": titles,
        "note": (
            "Title ideas are suggestions, not facts. Scores reward length, "
            "hook words, questions, numbers and your keywords — pick the "
            "one that fits the video, not just the highest number."
        ),
    }
