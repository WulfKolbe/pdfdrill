#!/usr/bin/env python3
"""pdfdrill_mcp_http — the REMOTE (Streamable HTTP) transport for the pdfdrill
MCP server, for a claude.ai / web custom connector.

This is a SEPARATE entry point from the stdio server (`pdfdrill_mcp.py`, used by
Claude Desktop / Claude Code). It does NOT modify or replace it — it IMPORTS it
and reuses the exact same tools (`drill`/`md`/`tiddlers`/`report`), resource
registry, and dispatch, so the two transports stay in lockstep and the stdio
interface you use all the time is untouched.

Transport: MCP **Streamable HTTP** (the 2025 successor to the old HTTP+SSE
transport) — a single endpoint:
  POST /mcp   one JSON-RPC message → a response delivered as an SSE `message`
              event (Content-Type: text/event-stream) when the client accepts
              it, else a plain application/json body. Notifications → 202.
  GET  /mcp   opens an SSE stream for server-initiated messages (kept alive with
              comments; we have none, so it's just a heartbeat).
  DELETE /mcp ends the session.
A session id is minted on `initialize` and returned in `Mcp-Session-Id`.

Pure stdlib (http.server + threading) — no `mcp` SDK, matching the rest of the
repo. TLS is terminated by your front (the sensorcloud HTTPS host / a reverse
proxy); this serves plain HTTP on --host/--port behind it. Optional shared-secret
auth via --token (or $PDFDRILL_MCP_TOKEN): clients must send
`Authorization: Bearer <token>`.

Run:
  python3 tools/pdfdrill_mcp_http.py --host 127.0.0.1 --port 8765 --token SECRET
Then point a claude.ai custom connector at  https://<your-host>/mcp .
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pdfdrill_mcp as core   # reuse TOOLS / RESOURCES / PROTOCOL / SERVER_INFO


def log(*a):
    print("[pdfdrill_mcp_http]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Pure JSON-RPC dispatch — mirrors core.handle() but RETURNS the response object
# (or None for a notification) instead of writing to stdout. Reuses core's tools
# + resource registry verbatim, so both transports expose identical behaviour.
# ---------------------------------------------------------------------------

_SESSIONS: set[str] = set()


def dispatch(msg: dict):
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

    if method == "initialize":
        client_proto = params.get("protocolVersion", core.PROTOCOL)
        return ok({
            "protocolVersion": client_proto,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"subscribe": False, "listChanged": True}},
            "serverInfo": core.SERVER_INFO,
            "instructions": "Drill PDFs/arXiv URLs; result files come back as resources."})

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        return ok({"tools": [
            {"name": n, "description": t["description"], "inputSchema": t["schema"]}
            for n, t in core.TOOLS.items()]})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = core.TOOLS.get(name)
        if not tool:
            return err(-32602, f"unknown tool: {name}")
        try:
            content = tool["fn"](args)
            return ok({"content": content, "isError": False})
        except Exception as e:  # noqa: BLE001
            import traceback
            log("tool error:", traceback.format_exc())
            return ok({"content": [{"type": "text", "text": f"error: {e}"}],
                       "isError": True})

    if method == "resources/list":
        return ok({"resources": [
            {"uri": r["uri"], "name": r["name"], "mimeType": r["mimeType"]}
            for r in core.RESOURCES.values()]})

    if method == "resources/read":
        uri = params.get("uri")
        rec = core.RESOURCES.get(uri)
        if not rec:
            return err(-32602, f"unknown resource: {uri}")
        import base64
        p = Path(rec["path"])
        if rec["mimeType"].startswith("text/") or rec["mimeType"] in (
                "application/json", "application/xml", "image/svg+xml"):
            return ok({"contents": [{"uri": uri, "mimeType": rec["mimeType"],
                                     "text": p.read_text(errors="replace")}]})
        return ok({"contents": [{"uri": uri, "mimeType": rec["mimeType"],
                                 "blob": base64.b64encode(p.read_bytes()).decode()}]})

    if id_ is not None:
        return err(-32601, f"method not found: {method}")
    return None


# ---------------------------------------------------------------------------
# HTTP layer (Streamable HTTP)
# ---------------------------------------------------------------------------

TOKEN: "str | None" = None
ENDPOINT = "/mcp"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):       # quiet default logging; we log to stderr
        pass

    # ---- helpers ----
    def _auth_ok(self) -> bool:
        if not TOKEN:
            return True
        got = self.headers.get("Authorization", "")
        return got == f"Bearer {TOKEN}"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, Mcp-Session-Id, MCP-Protocol-Version")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")

    def _send_json(self, obj, status=200, session=None):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", session)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, obj, session=None):
        """One JSON-RPC response as a single SSE `message` event, then close."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if session:
            self.send_header("Mcp-Session-Id", session)
        self._cors()
        self.end_headers()
        self.wfile.write(f"event: message\ndata: {json.dumps(obj)}\n\n".encode())
        self.wfile.flush()

    def _empty(self, status, session=None):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        if session:
            self.send_header("Mcp-Session-Id", session)
        self._cors()
        self.end_headers()

    # ---- methods ----
    def do_OPTIONS(self):
        self._empty(204)

    def do_GET(self):
        if self.path.split("?")[0] != ENDPOINT:
            return self._empty(404)
        if not self._auth_ok():
            return self._empty(401)
        # Open an SSE stream for server-initiated messages. We have none, so this
        # is a heartbeat the client can hold open; it ends on disconnect.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        try:
            import time
            while True:
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_DELETE(self):
        if self.path.split("?")[0] != ENDPOINT:
            return self._empty(404)
        sid = self.headers.get("Mcp-Session-Id")
        if sid:
            _SESSIONS.discard(sid)
        self._empty(204)

    def do_POST(self):
        if self.path.split("?")[0] != ENDPOINT:
            return self._empty(404)
        if not self._auth_ok():
            return self._empty(401)
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            msg = json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return self._send_json(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "parse error"}}, status=400)

        # session: mint on initialize, require thereafter (lenient — we accept
        # missing ids so simple clients still work).
        session = self.headers.get("Mcp-Session-Id")
        is_init = isinstance(msg, dict) and msg.get("method") == "initialize"
        if is_init:
            session = uuid.uuid4().hex
            _SESSIONS.add(session)

        # a batch (list) or a single message
        if isinstance(msg, list):
            responses = [r for r in (dispatch(m) for m in msg) if r is not None]
            if not responses:
                return self._empty(202, session)
            return self._reply(responses, session)

        resp = dispatch(msg)
        if resp is None:                      # a notification
            return self._empty(202, session)
        return self._reply(resp, session)

    def _reply(self, obj, session):
        """SSE when the client accepts it (Streamable HTTP default), else JSON."""
        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept:
            return self._send_sse(obj, session)
        return self._send_json(obj, session=session)


def main():
    global TOKEN
    ap = argparse.ArgumentParser(description="pdfdrill MCP — Streamable HTTP transport (web connector)")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1; use 0.0.0.0 behind a proxy)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=os.environ.get("PDFDRILL_MCP_TOKEN"),
                    help="shared secret; clients send Authorization: Bearer <token> ($PDFDRILL_MCP_TOKEN)")
    args = ap.parse_args()
    TOKEN = args.token or None

    core.CACHE.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"Streamable HTTP MCP on http://{args.host}:{args.port}{ENDPOINT}"
        + ("  (auth: Bearer token required)" if TOKEN else "  (no auth — set --token behind a public proxy)"))
    log("point a claude.ai custom connector at  https://<public-host>" + ENDPOINT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
        httpd.shutdown()


if __name__ == "__main__":
    main()
