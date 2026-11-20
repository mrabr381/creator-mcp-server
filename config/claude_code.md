# Claude Code setup

Add the server with one command (replace the path with your checkout):

```bash
claude mcp add creator-mcp-server \
  -- /path/to/creator-mcp-server/.venv/bin/python -m creator_mcp
```

With API keys (both optional — without them the YouTube and GEO tools run
in labelled sample mode):

```bash
claude mcp add creator-mcp-server \
  -e YOUTUBE_API_KEY=YOUR_YOUTUBE_DATA_API_KEY \
  -e GEMINI_API_KEY=YOUR_FREE_GEMINI_KEY \
  -- /path/to/creator-mcp-server/.venv/bin/python -m creator_mcp
```

Verify it is connected:

```bash
claude mcp list
```

Then ask Claude Code, for example:

> "Use the creator-mcp-server tools to find the outliers for @mysterylane
> and suggest 5 titles for the top topic."
```

```text
Claude Code reads MCP servers from `.mcp.json` in the project root, or
from the user-level config. The `claude mcp add` command writes it for
you — no hand-editing needed.
```
