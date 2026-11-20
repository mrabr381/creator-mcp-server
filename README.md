# Creator MCP Server 🔌

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP SDK v2](https://img.shields.io/badge/MCP-SDK%20v2-purple.svg)](https://modelcontextprotocol.io)
[![No API key required](https://img.shields.io/badge/API%20key-not%20required-brightgreen.svg)](#sample-mode-no-key-needed)

**Creator-workflow tools for AI coding assistants — YouTube outlier research, transcript repurposing, title ideas, single-page SEO + GEO audit, and AI-search brand checks — as one MCP server.**

Give Claude Code, Claude Desktop, Cursor or Codex five tools that actually do creator work, instead of asking the model to guess the numbers. Every number comes from a real API response, a real page fetch, or a clearly labelled sample fixture. Nothing is invented.

## Table of contents

- [Tools](#tools)
- [Sample mode — no key needed](#sample-mode--no-key-needed)
- [Quickstart](#quickstart)
- [Wiring it into your assistant](#wiring-it-into-your-assistant)
- [A real session](#a-real-session)
- [How it works](#how-it-works)
- [Honest limitations](#honest-limitations)
- [Project structure](#project-structure)
- [Testing](#testing)
- [License](#license)

## Tools

| Tool | What it does | Needs a key? |
| --- | --- | --- |
| `youtube_outlier_search` | Finds a channel's outlier videos: views vs channel median, velocity, keyword lift, gap words, title bigrams | No — sample mode without one |
| `repurpose_transcript` | Turns one transcript into a blog post, X thread, LinkedIn post, newsletter, chapters and pull quotes | No — extractive, local only |
| `title_ideas` | Generates scored YouTube title ideas for a topic (deterministic 0-100 scoring, formula documented) | No |
| `seo_audit_page` | Audits one page: title, meta, H1, canonical, Open Graph, alt text, word count, JSON-LD schema, `llms.txt` — 0-100 score + fix list | No |
| `geo_brand_check` | Checks how often AI answers mention a brand across 10 prompts | No — sample mode without one |

Every tool returns a JSON string. Failures come back as `{"ok": false, "error": "..."}` — never a traceback over the protocol.

## Sample mode — no key needed

Two tools need an API key for live data. Without one they still work, on bundled fixtures, and **every sample result says so**:

- `youtube_outlier_search` without a key analyses the bundled fixture channel **Mystery Lane** (`@mysterylane`, 24 videos) and labels the result `"mode": "sample"`. The numbers are real for that fixture: median **12,850** views, **5 outliers**, top outlier **4.86×** — the same numbers the [Open-vidIQ](https://github.com/mrabr381/open-vidiq) project verified for this dataset.
- `geo_brand_check` without a key checks the bundled fixture answers for **toolenix.com**: **4 mentions in 10 prompts = 40.0%**. Asking about any other brand without a key is an error, not a fabricated result — the tool tells you to provide a free Gemini key.

Free keys (both $0):

- **YouTube Data API v3** — 10,000 units/day. Enable it at <https://console.cloud.google.com/apis/library/youtube.googleapis.com> and set `YOUTUBE_API_KEY`.
- **Gemini API** — free tier. Create a key at <https://aistudio.google.com/apikey> and set `GEMINI_API_KEY`.

## Quickstart

```bash
git clone https://github.com/mrabr381/creator-mcp-server.git
cd creator-mcp-server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run it (stdio transport — what Claude Desktop / Claude Code expect):
python -m creator_mcp

# Or serve the same tools over HTTP:
python -m creator_mcp --transport streamable-http --port 8000
```

Check it works:

```bash
python scripts/smoke_test.py
# 51 passed, 0 failed. ALL CHECKS PASSED
```

## Wiring it into your assistant

**Claude Desktop** — add to `claude_desktop_config.json` (full file in [`config/claude_desktop_config.json`](config/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "creator-mcp-server": {
      "command": "/path/to/creator-mcp-server/.venv/bin/python",
      "args": ["-m", "creator_mcp"],
      "env": {
        "YOUTUBE_API_KEY": "",
        "GEMINI_API_KEY": ""
      }
    }
  }
}
```

Replace `/path/to/creator-mcp-server` with your checkout path. Leave the keys empty for sample mode, or paste your free keys.

**Claude Code** — one command (see [`config/claude_code.md`](config/claude_code.md)):

```bash
claude mcp add creator-mcp-server \
  -e YOUTUBE_API_KEY=YOUR_YOUTUBE_DATA_API_KEY \
  -e GEMINI_API_KEY=YOUR_FREE_GEMINI_KEY \
  -- /path/to/creator-mcp-server/.venv/bin/python -m creator_mcp
```

**Cursor** — add the entry from [`config/cursor.md`](config/cursor.md) to `.cursor/mcp.json`, then confirm `creator-mcp-server` shows 5 tools in Settings → MCP.

## A real session

Ask your assistant (sample mode, no keys):

> "Find the outliers for @mysterylane and suggest 5 titles for the top topic."

What happens under the hood:

1. `youtube_outlier_search` returns the fixture analysis — median 12,850, top outlier *"The Tower of London's Lost Princes — What Really Happened?"* at 4.86×, gap words `found`, `london`.
2. `title_ideas` for topic `lost princes` returns 5 scored titles, e.g. *"The Lost Princes Mystery, Finally Solved?"* — **84/100**.
3. The assistant combines them into a grounded answer — no invented views, no invented trends.

A full tool-call transcript from the smoke test is in [`sample_output/smoke_transcript.json`](sample_output/smoke_transcript.json).

## How it works

```
Claude Code / Desktop / Cursor / Codex
        │  MCP (stdio, JSON-RPC)
        ▼
creator_mcp/server.py  ── 5 tools
        │
        ├── outliers.py   median / outlier score / velocity / keyword lift
        │                 (ported from Open-vidIQ, same verified numbers)
        ├── youtube.py    YouTube Data API v3 client (1 unit per call)
        ├── repurpose.py  extractive repurposing (ported from Creator
        │                 Repurpose Agent — quotes are exact sentences)
        ├── titles.py     deterministic title templates + 0-100 scoring
        ├── seo.py        single-page audit (subset of the SEO + GEO
        │                 Site Audit CLI's checks, one page not a crawl)
        └── geo.py        brand-mention detection; live mode calls the
                          Gemini REST API, one call per prompt
```

The analysis logic is copied into this repo from the sibling projects — this server does not import from them, so it runs standalone.

## Honest limitations

- **Sample mode is a fixture, not your channel.** Without a YouTube key you always get Mystery Lane; without a Gemini key you always get Toolenix. The result says so every time — check `"mode"` in the response.
- **Live Gemini calls were not testable in the build sandbox** — the sandbox blocks `generativelanguage.googleapis.com` (the call fails cleanly with a clear error, no traceback). The live path is verified by code path, not by a live call — try it with your own free key.
- **Live GEO answers vary run to run.** One Gemini call per prompt is a snapshot, not a stable metric — re-run to see drift.
- **Repurposing is extractive, not written.** The blog post, newsletter and LinkedIn post reuse your own sentences. That is deliberate — it cannot invent — but the wording reads like a draft, not a polished article.
- **Title scores reward a formula** (length, hook words, questions, numbers, keywords). A high score means "follows proven patterns", not "will go viral".
- **SEO audit is one page, no JavaScript.** Pages are fetched as HTML; JS-rendered content is invisible. Speed is not measured — word count and resource checks are only a proxy. For a full-site crawl use the [SEO + GEO Site Audit CLI](https://github.com/mrabr381/seo-geo-audit-cli).
- **Anti-bot sites get flagged as broken links** in related tools — a 403 or timeout from Medium, LinkedIn or similar is bot-blocking, not a dead link.

## Project structure

```
creator-mcp-server/
├── creator_mcp/
│   ├── server.py        # MCPServer + the 5 tool definitions + CLI
│   ├── outliers.py      # median / outlier / velocity / keyword lift
│   ├── youtube.py       # YouTube Data API client + sample fixture
│   ├── repurpose.py     # extractive repurposing
│   ├── titles.py        # title templates + 0-100 scoring
│   ├── seo.py           # single-page SEO + GEO audit
│   └── geo.py           # GEO brand check (sample + live Gemini)
├── sample_data/         # fixtures: channel + videos, transcript,
│                        # sample prompts + answers, test page + llms.txt
├── sample_output/
│   └── smoke_transcript.json   # real tool-call results from the smoke test
├── scripts/
│   └── smoke_test.py    # MCP protocol-level test (51 checks)
├── config/              # Claude Desktop / Claude Code / Cursor setup
├── requirements.txt     # pinned to tested versions
└── README.md
```

## Testing

`scripts/smoke_test.py` is a real MCP client: it spawns the server over stdio, sends `initialize`, `tools/list` and `tools/call` for every tool, and asserts the results against hand-checked expectations — including the outlier maths (median 12,850, top 4.86×), a hand-computed title score (78), and a hand-computed SEO score (45/100 on the flawed fixture page). Two runs are byte-identical. It also passes from a fresh venv installed from `requirements.txt`.

```bash
python scripts/smoke_test.py
# 51 passed, 0 failed. ALL CHECKS PASSED
```

## License

MIT — see [LICENSE](LICENSE).
