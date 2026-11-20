# Cursor setup

Cursor reads MCP servers from `.cursor/mcp.json` in the project root
(or `~/.cursor/mcp.json` for a global install). Add this entry
(replace the path with your checkout):

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

Leave the keys empty to run the YouTube and GEO tools in labelled sample
mode, or paste your free keys:

- YouTube Data API v3 key — free, 10,000 units/day. Create one at
  https://console.cloud.google.com/apis/library/youtube.googleapis.com
- Gemini API key — free tier. Create one at https://aistudio.google.com/apikey

After saving, open Cursor Settings → MCP and confirm
`creator-mcp-server` shows 5 tools. Then ask the agent, for example:

> "Audit https://toolenix.com with the creator-mcp-server seo tool and
> tell me the three highest-impact fixes."
```
