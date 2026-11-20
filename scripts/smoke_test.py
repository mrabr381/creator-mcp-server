#!/usr/bin/env python3
"""Smoke test — talks to the server over the real MCP protocol (stdio).

Spawns `python -m creator_mcp`, sends JSON-RPC (initialize, tools/list,
tools/call for every tool) and asserts the results against hand-checked
expectations:

- youtube_outlier_search (sample mode): median 12,850, 5 outliers,
  top outlier 4.86x "The Tower of London's Lost Princes" — the same
  numbers Open-vidIQ verified for this fixture.
- repurpose_transcript: every pull-quote is an exact substring of the
  transcript; every X post is <= 280 chars.
- title_ideas: 5 titles, each contains the topic; scores in 0-100;
  one score re-computed by hand from the documented formula.
- seo_audit_page (local fixture page): title_length FAIL, meta FAIL,
  single_h1 FAIL, llms.txt PASS, JSON-LD PASS; score in the 40-50 band
  (hand-computed expectation: 45/100).
- geo_brand_check (sample mode): Toolenix 4/10 = 40.0%.
- Error paths: bad URL, unknown brand in sample mode, empty transcript
  all return {"ok": false, ...} with a clear message and no traceback.

Writes sample_output/smoke_transcript.json (the tool-call results).
Exit 0 when every check passes, 1 otherwise. No servers left running.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from creator_mcp.outliers import days_since

SAMPLE_DATA = ROOT / "sample_data"
TRANSCRIPT = (SAMPLE_DATA / "sample_transcript.txt").read_text(encoding="utf-8")

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


class Client:
    """Minimal MCP stdio client (newline-delimited JSON-RPC)."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.next_id = 1

    def _send(self, payload: dict) -> None:
        line = json.dumps(payload) + "\n"
        self.proc.stdin.write(line.encode())
        self.proc.stdin.flush()

    def _read(self, timeout: float = 30.0) -> dict:
        fd = self.proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            raise TimeoutError("No response from the MCP server within 30s.")
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout (crashed?).")
        return json.loads(line.decode())

    def request(self, method: str, params: dict | None = None) -> dict:
        rid = self.next_id
        self.next_id += 1
        self._send(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        )
        resp = self._read()
        assert resp.get("id") == rid, f"Response id mismatch: {resp}"
        if "error" in resp:
            raise RuntimeError(f"JSON-RPC error for {method}: {resp['error']}")
        return resp["result"]

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self.request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        content = result.get("content", [])
        assert content, f"Tool {name} returned no content."
        text = "".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        )
        return json.loads(text)


def serve_fixtures() -> tuple[ThreadingHTTPServer, int]:
    """Serve sample_data/ on 127.0.0.1, ephemeral port, in a thread."""
    os.chdir(SAMPLE_DATA)
    server = ThreadingHTTPServer(("127.0.0.1", 0), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def main() -> int:
    env = {k: v for k, v in os.environ.items()
           if k not in ("YOUTUBE_API_KEY", "GEMINI_API_KEY")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "creator_mcp"],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    transcript_results: dict = {}
    try:
        client = Client(proc)
        print("== initialize ==")
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "0.1.0"},
            },
        )
        check("initialize returns serverInfo", "serverInfo" in init, str(init)[:200])
        client.notify("notifications/initialized")

        print("== tools/list ==")
        tools = client.request("tools/list")["tools"]
        names = sorted(t["name"] for t in tools)
        expected = sorted(
            [
                "youtube_outlier_search",
                "repurpose_transcript",
                "title_ideas",
                "seo_audit_page",
                "geo_brand_check",
            ]
        )
        check("exactly 5 tools listed", names == expected, str(names))
        for tool in tools:
            check(
                f"tool {tool['name']} has inputSchema",
                "inputSchema" in tool and "properties" in tool["inputSchema"],
            )

        print("== youtube_outlier_search (sample) ==")
        out = client.call_tool(
            "youtube_outlier_search", {"channel": "@mysterylane"}
        )
        transcript_results["youtube_outlier_search"] = out
        check("outlier search ok", out.get("ok") is True, str(out)[:300])
        check("outlier mode is sample", out.get("mode") == "sample")
        check("median views 12850", out.get("median_views") == 12850,
              f"got {out.get('median_views')}")
        check("5 outliers", len(out.get("outliers", [])) == 5,
              f"got {len(out.get('outliers', []))}")
        top = out["outliers"][0]
        check("top outlier is Tower of London's Lost Princes",
              top["title"].startswith("The Tower of London's Lost Princes"),
              top["title"])
        check("top outlier score 4.86", top["outlier_score"] == 4.86,
              f"got {top['outlier_score']}")
        # Velocity depends on today's date (views / days since publish),
        # so the expected value is computed from the same days_since()
        # the server uses — a hardcoded 95.1 passed only on 2026-11-19
        # and would fail in CI the next day.
        expected_velocity = round(
            62400 / days_since("2025-02-01T16:00:00Z"), 1
        )
        check("top outlier velocity matches views/days-since-publish",
              top["velocity_per_day"] == expected_velocity,
              f"got {top['velocity_per_day']}, expected {expected_velocity}")
        check("sample note present", "Sample mode" in out.get("note", ""))

        print("== repurpose_transcript ==")
        rep = client.call_tool(
            "repurpose_transcript", {"transcript": TRANSCRIPT}
        )
        transcript_results["repurpose_transcript"] = rep
        check("repurpose ok", rep.get("ok") is True, str(rep)[:300])
        check("engine is local-extractive",
              rep.get("engine") == "local-extractive")
        check("683 words counted", rep.get("words") == 683,
              f"got {rep.get('words')}")
        quotes = rep.get("pull_quotes", [])
        check("5 pull quotes", len(quotes) == 5, f"got {len(quotes)}")
        plain = " ".join(TRANSCRIPT.split())
        check("every quote is an exact substring of the transcript",
              all(" ".join(q.split()) in plain for q in quotes))
        check("quotes are 8-38 words",
              all(8 <= len(q.split()) <= 38 for q in quotes))
        thread = rep.get("x_thread", [])
        check("x thread has posts", len(thread) >= 2, f"got {len(thread)}")
        check("every x post <= 280 chars",
              all(len(p) <= 280 for p in thread),
              f"max {max(len(p) for p in thread)}")
        check("x posts numbered", all("/" in p for p in thread))
        check("chapters use real timestamps",
              all(c["timestamp"].startswith("[") and not c["approximate"]
                  for c in rep.get("chapters", [])),
              str(rep.get("chapters"))[:200])
        check("linkedin post ends with a question",
              rep.get("linkedin_post", "").rstrip().endswith("?"))

        print("== title_ideas ==")
        titles = client.call_tool(
            "title_ideas",
            {"topic": "lost princes", "keywords": ["tower", "london"], "count": 5},
        )
        transcript_results["title_ideas"] = titles
        check("titles ok", titles.get("ok") is True)
        ideas = titles.get("titles", [])
        check("5 title ideas", len(ideas) == 5, f"got {len(ideas)}")
        check("every title contains the topic",
              all("lost princes" in t["title"].lower() for t in ideas))
        check("scores in 0-100",
              all(0 <= t["score"] <= 100 for t in ideas))
        check("titles sorted by score desc",
              [t["score"] for t in ideas] == sorted(
                  (t["score"] for t in ideas), reverse=True))
        # Hand-check one score: "The Lost Princes — What Really Happened?"
        # base 40 +12 length 40-60 (42 chars) +12 hook (lost) +10 question
        # +4 opener (The) = 78.
        first = next(
            (t for t in ideas if t["title"].startswith("The Lost Princes —")),
            None,
        )
        check("hand-checked score 78 for 'The Lost Princes — What Really Happened?'",
              first is not None and first["score"] == 78,
              f"got {first}")

        print("== seo_audit_page (local fixture) ==")
        server, port = serve_fixtures()
        try:
            seo = client.call_tool(
                "seo_audit_page",
                {"url": f"http://127.0.0.1:{port}/sample_page.html"},
            )
        finally:
            server.shutdown()
        transcript_results["seo_audit_page"] = seo
        check("seo audit ok", seo.get("ok") is True, str(seo)[:300])
        checks = {c["check"]: c for c in seo.get("checks", [])}
        check("title_length FAIL (95 chars)",
              checks["title_length"]["score"] == 0.0,
              str(checks.get("title_length")))
        check("meta_description FAIL (missing)",
              checks["meta_description"]["score"] == 0.0)
        check("single_h1 FAIL (2 h1s)",
              checks["single_h1"]["score"] == 0.0
              and checks["single_h1"]["detail"].startswith("2 "),
              str(checks.get("single_h1")))
        check("llms_txt PASS", checks["llms_txt"]["score"] == 1.0,
              str(checks.get("llms_txt")))
        check("json_ld_schema PASS (FAQPage)",
              checks["json_ld_schema"]["score"] == 1.0)
        check("image_alt partial (1/2)", checks["image_alt"]["score"] == 0.5,
              str(checks.get("image_alt")))
        check("seo score in 40-50 band", 40 <= seo.get("score", 0) <= 50,
              f"got {seo.get('score')}")
        check("fixes listed", len(seo.get("fixes", [])) >= 4,
              f"got {len(seo.get('fixes', []))}")

        print("== geo_brand_check (sample) ==")
        geo = client.call_tool("geo_brand_check", {"brand": "toolenix.com"})
        transcript_results["geo_brand_check"] = geo
        check("geo ok", geo.get("ok") is True, str(geo)[:300])
        check("geo mode is sample", geo.get("mode") == "sample")
        check("10 prompts checked", geo.get("prompts_checked") == 10,
              f"got {geo.get('prompts_checked')}")
        check("4 mentions", geo.get("mentions") == 4,
              f"got {geo.get('mentions')}")
        check("mention rate 40.0%", geo.get("mention_rate_percent") == 40.0,
              f"got {geo.get('mention_rate_percent')}")

        print("== error paths ==")
        bad_url = client.call_tool("seo_audit_page", {"url": "not-a-url"})
        check("bad URL returns ok:false, no traceback",
              bad_url.get("ok") is False and "Traceback" not in str(bad_url),
              str(bad_url)[:200])
        unknown_brand = client.call_tool(
            "geo_brand_check", {"brand": "example.com"}
        )
        check("unknown brand in sample mode returns ok:false",
              unknown_brand.get("ok") is False
              and "Sample mode only covers" in unknown_brand.get("error", ""),
              str(unknown_brand)[:200])
        empty_rep = client.call_tool("repurpose_transcript", {"transcript": "hi"})
        check("empty transcript returns ok:false, no traceback",
              empty_rep.get("ok") is False and "Traceback" not in str(empty_rep),
              str(empty_rep)[:200])
        empty_title = client.call_tool("title_ideas", {"topic": "  "})
        check("empty topic returns ok:false",
              empty_title.get("ok") is False, str(empty_title)[:200])
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stderr = proc.stderr.read().decode(errors="replace")
        if "Traceback" in stderr:
            FAIL.append("server stderr has no Traceback")
            print("  FAIL  server stderr contains a Traceback")
            print(stderr[:2000])
        else:
            PASS.append("server stderr has no Traceback")
            print("  PASS  server stderr has no Traceback")

    out_path = ROOT / "sample_output" / "smoke_transcript.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        json.dumps(transcript_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed.")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
