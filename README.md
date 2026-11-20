# Creator MCP Server 🔌

[![CI](https://github.com/mrabr381/creator-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/mrabr381/creator-mcp-server/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP SDK v2](https://img.shields.io/badge/MCP-SDK%20v2-purple.svg)](https://modelcontextprotocol.io)
[![No API key required](https://img.shields.io/badge/API%20key-not%20required-brightgreen.svg)](#sample-mode--no-key-needed)

![Creator MCP Server — give your AI assistant five real creator tools, no guessing](assets/hero.svg)

**Give your AI assistant five real creator tools — no guessing, no invented numbers.** YouTube outlier research, transcript repurposing, title ideas, single-page SEO + GEO audit, and AI-search brand checks, as one MCP server for Claude Code, Claude Desktop, Cursor or Codex. Every number comes from a real API response, a real page fetch, or a clearly labelled sample fixture.

## Install in one command

```bash
claude mcp add creator-mcp-server \
  -- /path/to/creator-mcp-server/.venv/bin/python -m creator_mcp
```

No API key needed to start (sample mode, below). With free keys, add `-e YOUTUBE_API_KEY=... -e GEMINI_API_KEY=...` before the `--` (full form in [`config/claude_code.md`](config/claude_code.md)). Verify with `claude mcp list`.

## 30 seconds, real output

The smoke test talks to the server over the real MCP protocol — this is its actual output:

```text
== youtube_outlier_search (sample) ==
  PASS  outlier search ok
  PASS  outlier mode is sample
  PASS  median views 12850
  PASS  5 outliers
  PASS  top outlier is Tower of London's Lost Princes
  PASS  top outlier score 4.86
  PASS  top outlier velocity matches views/days-since-publish
  PASS  sample note present
...
51 passed, 0 failed. ALL CHECKS PASSED
```

Ask your assistant (sample mode, no keys): *"Find the outliers for @mysterylane and suggest 5 titles for the top topic."* It returns median **12,850** views, top outlier *"The Tower of London's Lost Princes — What Really Happened?"* at **4.86×**, plus 5 scored titles (e.g. *"The Lost Princes Mystery, Finally Solved?"* — **84/100**). Full tool-call transcript: [`sample_output/smoke_transcript.json`](sample_output/smoke_transcript.json).

## The 5 tools

| Tool | What it does | Needs a key? |
| --- | --- | --- |
| `youtube_outlier_search` | A channel's outlier videos: views vs median, velocity, keyword lift, gap words, title bigrams | No — sample mode |
| `repurpose_transcript` | One transcript → blog post, X thread, LinkedIn post, newsletter, chapters, pull quotes | No — extractive, local only |
| `title_ideas` | Scored YouTube title ideas (deterministic 0–100 scoring, formula documented) | No |
| `seo_audit_page` | One page audited: title, meta, H1, canonical, Open Graph, alt text, word count, JSON-LD, `llms.txt` — 0–100 + fix list | No |
| `geo_brand_check` | How often AI answers mention a brand across 10 prompts | No — sample mode |

Every tool returns a JSON string. Failures come back as `{"ok": false, "error": "..."}` — never a traceback over the protocol.

## Sample mode — no key needed

Without a key, two tools still work on bundled fixtures and **every sample result says so**:

- `youtube_outlier_search` analyses the fixture channel **Mystery Lane** (`@mysterylane`, 24 videos), labelled `"mode": "sample"`. Median **12,850** views, **5 outliers**, top outlier **4.86×** — the same numbers the [Open-vidIQ](https://github.com/mrabr381/open-vidiq) project verified for this dataset.
- `geo_brand_check` checks fixture answers for **toolenix.com**: **4 mentions in 10 prompts = 40.0%**. Any other brand without a key is an error, not a fabricated result.

Free keys (both $0): **YouTube Data API v3** (10,000 units/day) at <https://console.cloud.google.com/apis/library/youtube.googleapis.com> → `YOUTUBE_API_KEY`; **Gemini API** (free tier) at <https://aistudio.google.com/apikey> → `GEMINI_API_KEY`.

## Quickstart

```bash
git clone https://github.com/mrabr381/creator-mcp-server.git
cd creator-mcp-server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m creator_mcp                                  # stdio (Claude Desktop / Code)
python -m creator_mcp --transport streamable-http --port 8000   # or over HTTP
python scripts/smoke_test.py                           # 51 passed, 0 failed
```

**Claude Desktop** — full file in [`config/claude_desktop_config.json`](config/claude_desktop_config.json) (command = your checkout's `.venv/bin/python -m creator_mcp`, keys empty for sample mode). **Cursor** — entry from [`config/cursor.md`](config/cursor.md) in `.cursor/mcp.json`; confirm 5 tools in Settings → MCP. The analysis logic is copied into this repo from the sibling projects, so the server runs standalone.

## Honest limitations

- **Sample mode is a fixture, not your channel.** Without a YouTube key you always get Mystery Lane; without a Gemini key you always get Toolenix. Check `"mode"` in the response.
- **Live Gemini calls were not testable in the build sandbox** (it blocks `generativelanguage.googleapis.com` — the call fails cleanly with a clear error), and live GEO answers vary run to run — one call per prompt is a snapshot, not a stable metric.
- **Repurposing is extractive, not written** — the blog/newsletter reuse your own sentences. Deliberate (it cannot invent), but it reads like a draft. Title scores likewise reward a formula (length, hook words, questions, numbers, keywords): high score = "follows proven patterns", not "will go viral".
- **SEO audit is one page, no JavaScript.** For a full-site crawl use the [SEO + GEO Site Audit CLI](https://github.com/mrabr381/seo-geo-audit-cli).

## Tests

```bash
pip install pytest
python -m pytest                 # outlier maths: median 12850, top 4.86x, gap words
python scripts/smoke_test.py     # real MCP protocol test: 51 checks
```

CI runs both on every push (see the badge at the top).

```
creator-mcp-server/
├── creator_mcp/       # server.py + 5 tool modules (outliers, youtube, repurpose, titles, seo, geo)
├── sample_data/       # fixtures: channel + videos, transcript, prompts + answers, test page
├── sample_output/     # smoke_transcript.json — real tool-call results
├── scripts/smoke_test.py   # MCP protocol-level test (51 checks)
└── config/            # Claude Desktop / Claude Code / Cursor setup
```

MIT — see [LICENSE](LICENSE).
