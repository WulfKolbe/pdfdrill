# pdfdrill MCP server

The fix for "the result link doesn't open in chat." drillui's `/artifact?path=…`
is a localhost bridge route — from claude.ai it resolves against the client host
and 404s. MCP returns each produced file as a **resource** the client fetches
over the MCP connection (`resources/read`), so there's no port and no dead link.

`tools/pdfdrill_mcp.py` is pure stdlib — JSON-RPC 2.0 over stdin/stdout, no `mcp`
SDK, drops into `tools/` like the rest of pdfdrill.

## Tools

| Tool | Runs | Returns |
|---|---|---|
| `drill(url, profile)` | shallow\|standard\|deep ladder | summary + produced files as resources |
| `md(url)` | `pdfdrill md` | `<name>.md` (embedded text + resource_link) |
| `tiddlers(url, bibkey)` | `pdfdrill tiddlers` | `<bibkey>.tiddlers.json` resource |
| `report(url)` | `pdfdrill report --embed` | self-contained `formula-report.html` |

Every tool result carries a `resource_link` per file and embeds small text files
inline, so the md shows immediately and large/binary ones download. The server
also implements `resources/list` + `resources/read`.

## Where it runs (be deliberate)

- **Claude Desktop / Claude Code (local stdio):** the natural fit — pdfdrill runs
  on your machine with your MathPix keys and (if you install it) Ghostscript.
  Add to `claude_desktop_config.json`:

  ```json
  {
    "mcpServers": {
      "pdfdrill": {
        "command": "python3",
        "args": ["/ABS/PATH/pdfdrill/tools/pdfdrill_mcp.py"]
      }
    }
  }
  ```

  Then in chat: "drill arxiv.org/abs/2305.04710 standard" → the md/tiddlers come
  back as openable resources.

- **claude.ai web (remote connector):** the web client can't speak stdio — use
  **`tools/pdfdrill_mcp_http.py`**, the Streamable HTTP transport. It IMPORTS the
  stdio server (same `drill`/`md`/`tiddlers`/`report` tools + resource registry),
  so the two stay in lockstep and the stdio interface you use daily is untouched.

  ```bash
  python3 tools/pdfdrill_mcp_http.py --host 127.0.0.1 --port 8765 --token SECRET
  ```

  One endpoint `/mcp`: POST a JSON-RPC message → response as an SSE `message`
  event (or `application/json`); GET opens a heartbeat SSE stream; a session id is
  minted on `initialize` (`Mcp-Session-Id`). Optional bearer auth via `--token` /
  `$PDFDRILL_MCP_TOKEN`; CORS preflight handled. Terminate TLS at your front (the
  sensorcloud HTTPS host / a reverse proxy → `http://127.0.0.1:8765`), then add a
  claude.ai **custom connector** at `https://<your-host>/mcp`. Client rendering of
  returned resources varies, so validate in your target client.

## Proven (stdio + Streamable HTTP)

```
initialize → proto 2025-06-18 | caps tools,resources | server pdfdrill
tools/list → drill, md, tiddlers, report
tools/call md → text + resource_link + embedded resource (48 KB md inline), isError false
resources/list → 1312.6114.md, …, Kingma2013.tiddlers.json
resources/read → 1312.6114.md | text/markdown | 48051 bytes
```

Drive it yourself with any JSON-RPC-over-stdio client; no SDK required.

The **HTTP** transport is proven the same way (a stdlib urllib client):
`initialize` mints a session (returned via an SSE `message` event) → `tools/list`
→ `tools/call md` → text + resource_link + embedded resource → `resources/read`
returns the file (152 KB); a tokenless POST is 401; the CORS preflight is 204.
