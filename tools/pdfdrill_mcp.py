#!/usr/bin/env python3
"""pdfdrill_mcp — a stdio MCP server for pdfdrill.

Why this exists: in a chat client a result file is only "clickable" if it comes
back through a channel the client can actually fetch. drillui's `/artifact` URL
is a localhost bridge route — unreachable from claude.ai (it resolves against the
client host, 404). MCP fixes that: a tool returns the produced files as
`resource_link` + embedded `resource` content, and the client pulls them over the
MCP connection via `resources/read`. No exposed port, no dead links.

Design: pure stdlib (no `mcp` SDK), JSON-RPC 2.0 over newline-delimited stdin/
stdout, exactly like the rest of pdfdrill's tooling. stdout is the protocol
channel — all logging goes to stderr.

Tools (each runs pdfdrill on the resolved doc and returns a text summary PLUS
the produced files as resources):
  drill(url, profile)   shallow|standard|deep ladder (via drillbatch)
  md(url)               pdfdrill md      -> <name>.md
  tiddlers(url, bibkey) pdfdrill tiddlers-> <bibkey>.tiddlers.json
  report(url)           pdfdrill report  -> formula-report.html

Run (Claude Desktop / Claude Code — claude_desktop_config.json):
  { "mcpServers": { "pdfdrill": {
      "command": "python3",
      "args": ["/abs/path/to/pdfdrill/tools/pdfdrill_mcp.py"] } } }
"""
from __future__ import annotations

import base64
import json
import mimetypes
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drillbatch as db  # resolve(), pdfdrill_base(), run_cmd(), collect_outputs()

PROTOCOL = "2025-06-18"
SERVER_INFO = {"name": "pdfdrill", "version": "0.1.0"}
CACHE = HERE / ".mcp-pdfcache"
EMBED_LIMIT = 256 * 1024  # inline text files up to 256 KB; link the rest

# uri -> filesystem path, populated as tools produce artifacts
RESOURCES: dict[str, dict] = {}


def log(*a):
    print("[pdfdrill_mcp]", *a, file=sys.stderr, flush=True)


def uri_for(path: str) -> str:
    return Path(path).resolve().as_uri()  # file:///...


def register(path: str, kind: str = "") -> dict:
    p = Path(path).resolve()
    uri = p.as_uri()
    mime = mimetypes.guess_type(p.name)[0] or (
        "text/markdown" if p.suffix == ".md" else "application/octet-stream")
    rec = {"uri": uri, "name": p.name, "path": str(p), "mimeType": mime, "kind": kind}
    RESOURCES[uri] = rec
    return rec


def run_pdfdrill(args: list[str], timeout: float = 600.0):
    base, env = db.pdfdrill_base()
    return db.run_cmd(base, env, args, timeout)


# ---- tool implementations -------------------------------------------------

def _resolve(url: str):
    pdf, meta = db.resolve(url, CACHE, timeout=60.0)
    if not pdf:
        raise ValueError(meta.get("error", f"could not resolve {url!r}"))
    return pdf, meta


def _outputs_content(pdf: str) -> list[dict]:
    """Produced files as MCP content: a resource_link each, plus embedded text
    for small text artifacts so they render immediately."""
    content: list[dict] = []
    for o in db.collect_outputs(pdf):
        rec = register(o["path"], o["kind"])
        content.append({"type": "resource_link", "uri": rec["uri"],
                        "name": rec["name"], "mimeType": rec["mimeType"],
                        "description": f"{o['kind']} ({o['bytes']//1024} KB)"})
        p = Path(o["path"])
        if rec["mimeType"].startswith("text/") and o["bytes"] <= EMBED_LIMIT:
            content.append({"type": "resource", "resource": {
                "uri": rec["uri"], "mimeType": rec["mimeType"],
                "text": p.read_text(errors="replace")}})
    return content


def tool_md(args: dict) -> list[dict]:
    pdf, meta = _resolve(args["url"])
    ok, out = run_pdfdrill(["md", pdf])
    content = [{"type": "text", "text": out or "(no output)"}]
    content += _outputs_content(pdf)
    return content


def tool_tiddlers(args: dict) -> list[dict]:
    pdf, meta = _resolve(args["url"])
    cmd = ["tiddlers", pdf]
    if args.get("bibkey"):
        cmd += ["--bibkey", str(args["bibkey"])]
    ok, out = run_pdfdrill(cmd)
    return [{"type": "text", "text": out or "(no output)"}] + _outputs_content(pdf)


def tool_report(args: dict) -> list[dict]:
    pdf, meta = _resolve(args["url"])
    ok, out = run_pdfdrill(["report", pdf, "--embed"])
    return [{"type": "text", "text": out or "(no output)"}] + _outputs_content(pdf)


def tool_drill(args: dict) -> list[dict]:
    pdf, meta = _resolve(args["url"])
    profile = args.get("profile", "shallow")
    if profile not in db.LADDER:
        profile = "shallow"
    base, env = db.pdfdrill_base()
    card = db.drill_one(base, env, pdf, CACHE, 600.0, profile)
    lines = []
    h = card.get("headline", {})
    lines.append(f"{meta.get('arxiv_id') or args['url']} — {h.get('pages','?')} pp, "
                 f"{h.get('mb','?')} MB, "
                 f"{'text layer' if h.get('text_layer') else 'scanned/OCR' if h.get('scanned') else 'unknown layer'}")
    for k in ("abstract", "toc", "links"):
        st = card["steps"].get(k)
        if st and st.get("ok") and st["out"] and "not found" not in st["out"].lower():
            lines.append(f"\n[{k}]\n{st['out']}")
    content = [{"type": "text", "text": "\n".join(lines)}]
    content += _outputs_content(pdf)
    return content


TOOLS = {
    "drill": {
        "fn": tool_drill,
        "description": "Drill a PDF/arXiv URL shallow-first and return a summary plus any produced result files as resources. Use profile=shallow to triage (size/links/abstract/toc), standard to also build md+tiddlers, deep for report/gaps/rulebook.",
        "schema": {"type": "object", "properties": {
            "url": {"type": "string", "description": "arXiv id, /abs/, /pdf/, or any PDF URL"},
            "profile": {"type": "string", "enum": ["shallow", "standard", "deep"], "default": "shallow"}},
            "required": ["url"]},
    },
    "md": {
        "fn": tool_md,
        "description": "Extract the document to Markdown (math as LaTeX, citations/refs as transclusions) and return the .md file as a resource.",
        "schema": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]},
    },
    "tiddlers": {
        "fn": tool_tiddlers,
        "description": "Emit a TiddlyWiki tiddler-array JSON for the document and return it as a resource for import.",
        "schema": {"type": "object", "properties": {
            "url": {"type": "string"},
            "bibkey": {"type": "string", "description": "title prefix / filename, e.g. Kingma2013"}},
            "required": ["url"]},
    },
    "report": {
        "fn": tool_report,
        "description": "Build the inline+display math report (LaTeX|KaTeX|MathPix-image) as a self-contained HTML and return it as a resource.",
        "schema": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]},
    },
}


# ---- JSON-RPC plumbing ----------------------------------------------------

def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict):
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        client_proto = params.get("protocolVersion", PROTOCOL)
        return reply(id_, {
            "protocolVersion": client_proto,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"subscribe": False, "listChanged": True}},
            "serverInfo": SERVER_INFO,
            "instructions": "Drill PDFs/arXiv URLs; result files come back as resources."})

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return  # notifications: no response

    if method == "ping":
        return reply(id_, {})

    if method == "tools/list":
        return reply(id_, {"tools": [
            {"name": n, "description": t["description"], "inputSchema": t["schema"]}
            for n, t in TOOLS.items()]})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if not tool:
            return reply(id_, error={"code": -32602, "message": f"unknown tool: {name}"})
        try:
            content = tool["fn"](args)
            return reply(id_, {"content": content, "isError": False})
        except Exception as e:  # noqa: BLE001
            log("tool error:", traceback.format_exc())
            return reply(id_, {"content": [{"type": "text", "text": f"error: {e}"}],
                               "isError": True})

    if method == "resources/list":
        return reply(id_, {"resources": [
            {"uri": r["uri"], "name": r["name"], "mimeType": r["mimeType"]}
            for r in RESOURCES.values()]})

    if method == "resources/read":
        uri = params.get("uri")
        rec = RESOURCES.get(uri)
        if not rec:
            return reply(id_, error={"code": -32602, "message": f"unknown resource: {uri}"})
        p = Path(rec["path"])
        if rec["mimeType"].startswith("text/") or rec["mimeType"] in (
                "application/json", "application/xml", "image/svg+xml"):
            return reply(id_, {"contents": [{"uri": uri, "mimeType": rec["mimeType"],
                                             "text": p.read_text(errors="replace")}]})
        return reply(id_, {"contents": [{"uri": uri, "mimeType": rec["mimeType"],
                                         "blob": base64.b64encode(p.read_bytes()).decode()}]})

    # unknown method
    if id_ is not None:
        return reply(id_, error={"code": -32601, "message": f"method not found: {method}"})


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    log("ready on stdio")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log("bad json:", line[:120])
            continue
        try:
            handle(msg)
        except Exception:  # noqa: BLE001
            log("handler crash:", traceback.format_exc())
            if msg.get("id") is not None:
                reply(msg["id"], error={"code": -32603, "message": "internal error"})


if __name__ == "__main__":
    main()
