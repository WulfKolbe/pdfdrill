"""The drop-zone HTTP server (I-B), stdlib-only.

Route shape deliberately mirrors what a future drillui-hosted endpoint would
expose, so this can be replaced by a Bun handler in ``drillui_bridge.ts`` without
the client changing:

    GET  /                      the drop zone
    GET  /job/<job>/manifest    the live ingest.json
    POST /job/<job>/pages       multipart upload  → raw/ + manifest entries
    POST /job/<job>/paths       text/uri-list     → reference entries (allowlisted)
    GET  /job/<job>/thumb/<seq> a page preview

Why stdlib and not the Bun bridge yet: pdfdrill integration is explicitly a later
step, and ``tools/DRILLUI.md`` states there is exactly ONE canonical copy of
``drillui_bridge.ts`` — editing another repo's canonical file is not this
project's call to make yet. The manifest/ingest logic all lives in
:mod:`scandrill.producers.upload`, which a Bun host would call through the same
Python entry points the bridge already uses for ``drillui_chat.py``.

**Binds to 127.0.0.1 by default.** This endpoint writes files and, in reference
mode, reads any path under the allowlisted roots — it is not hardened for a
hostile network.
"""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .manifest import Manifest
from .producers import upload as up

MAX_BODY = 200 * 1024 * 1024


class JobStore:
    """Holds one job's manifest + where its files live. The manifest IS the state."""

    def __init__(self, job: str, job_dir: Path, created: str, lang: str,
                 roots: list[Path]):
        self.job = job
        self.job_dir = Path(job_dir)
        self.roots = roots
        self.manifest = Manifest(job=job, created=created, lang=lang,
                                 source_root=str(self.job_dir))
        self.job_dir.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.job_dir / f"{self.job}.ingest.json"

    def save(self) -> Path:
        return self.manifest.save(self.manifest_path)

    def resolve_page(self, seq: int) -> Path | None:
        for p in self.manifest.pages:
            if p.seq == seq:
                src = Path(p.src)
                return src if src.is_absolute() else self.job_dir / src
        return None


DROP_ZONE = """<!doctype html>
<meta charset="utf-8"><title>SCANDRILL drop zone</title>
<style>
 body{font:14px system-ui;margin:0;padding:24px;background:#111;color:#eee}
 h1{font-size:16px;font-weight:600;margin:0 0 4px}
 .sub{color:#888;margin-bottom:16px}
 #zone{border:2px dashed #444;border-radius:8px;padding:48px;text-align:center;
       color:#888;transition:.15s}
 #zone.hot{border-color:#6af;background:#0d1a26;color:#6af}
 table{width:100%;border-collapse:collapse;margin-top:16px;font-size:13px}
 th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #222}
 th{color:#888;font-weight:500}
 .blank{color:#c84} .kept{color:#6c6}
 img{height:40px;border:1px solid #333;background:#fff}
 #err{color:#e66;white-space:pre-wrap;margin-top:8px}
</style>
<h1>SCANDRILL — job <code>%%JOB%%</code></h1>
<div class="sub">Drop images or a folder selection. The table is a render of
 <a href="/job/%%JOB%%/manifest" style="color:#6af">ingest.json</a>.</div>
<div id="zone">drop page images here</div>
<div id="err"></div>
<table><thead><tr><th>#</th><th></th><th>src</th><th>mode</th><th>mean</th>
 <th>status</th></tr></thead><tbody id="rows"></tbody></table>
<script>
const JOB = "%%JOB%%", zone = document.getElementById("zone"),
      rows = document.getElementById("rows"), err = document.getElementById("err");

async function refresh() {
  const r = await fetch(`/job/${JOB}/manifest`);
  const m = await r.json();
  rows.innerHTML = "";
  for (const p of m.pages) {
    const tr = document.createElement("tr");
    const cls = p.status === "pending" ? "kept" : "blank";
    tr.innerHTML = `<td>${p.seq}</td>
      <td><img src="/job/${JOB}/thumb/${p.seq}" loading="lazy"></td>
      <td>${p.src}</td><td>${p.origin.mode || ""}</td>
      <td>${p.blank_mean?.toFixed(4) ?? ""}</td>
      <td class="${cls}">${p.status}</td>`;
    rows.appendChild(tr);
  }
}

zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("hot"); });
zone.addEventListener("dragleave", () => zone.classList.remove("hot"));
zone.addEventListener("drop", async e => {
  e.preventDefault(); zone.classList.remove("hot"); err.textContent = "";
  // A drop gives EITHER file bytes OR a uri-list of paths, depending on the
  // source (file manager vs another app) and the desktop environment.
  const uris = e.dataTransfer.getData("text/uri-list");
  const files = [...e.dataTransfer.files];
  try {
    if (files.length) {
      const fd = new FormData();
      for (const f of files) fd.append("file", f, f.name);
      const r = await fetch(`/job/${JOB}/pages`, { method: "POST", body: fd });
      const j = await r.json();
      if (j.errors?.length) err.textContent = j.errors.join("\\n");
    } else if (uris) {
      const r = await fetch(`/job/${JOB}/paths`, {
        method: "POST", headers: { "Content-Type": "text/uri-list" }, body: uris });
      const j = await r.json();
      if (j.errors?.length) err.textContent = j.errors.join("\\n");
    }
  } catch (ex) { err.textContent = String(ex); }
  refresh();
});
refresh();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    store: JobStore = None          # set by serve()
    server_version = "SCANDRILL"

    def log_message(self, fmt, *args):      # quiet by default
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    # -- helpers --
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, code=400):
        self._json({"error": msg}, code)

    def _job_route(self, path: str) -> list[str] | None:
        parts = [unquote(s) for s in path.strip("/").split("/")]
        if len(parts) >= 2 and parts[0] == "job" and parts[1] == self.store.job:
            return parts[2:]
        return None

    # -- GET --
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = DROP_ZONE.replace("%%JOB%%", self.store.job).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        rest = self._job_route(path)
        if rest is None:
            return self._err("not found", 404)
        if rest[:1] == ["manifest"]:
            return self._json(self.store.manifest.to_dict())
        if len(rest) == 2 and rest[0] == "thumb":
            try:
                src = self.store.resolve_page(int(rest[1]))
            except ValueError:
                return self._err("bad seq", 400)
            if src is None or not src.exists():
                return self._err("no such page", 404)
            data = src.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             mimetypes.guess_type(src.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return self._err("not found", 404)

    # -- POST --
    def do_POST(self):
        path = urlparse(self.path).path
        rest = self._job_route(path)
        if rest is None:
            return self._err("not found", 404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._err("bad Content-Length")
        if length <= 0:
            return self._err("empty body")
        if length > MAX_BODY:
            return self._err("body too large", 413)
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")

        if rest[:1] == ["pages"]:
            return self._post_pages(ctype, body)
        if rest[:1] == ["paths"]:
            return self._post_paths(body)
        return self._err("not found", 404)

    def _post_pages(self, ctype: str, body: bytes):
        try:
            parts = up.parse_multipart(ctype, body)
        except up.UploadError as exc:
            return self._err(str(exc))
        added, errors = [], []
        for filename, data in parts:
            try:
                pg = up.add_upload(self.store.manifest, filename, data,
                                   job_dir=self.store.job_dir)
                added.append(pg.seq)
            except up.UploadError as exc:
                errors.append(str(exc))
        self.store.save()
        self._json({"added": added, "errors": errors,
                    "pages": len(self.store.manifest.pages)})

    def _post_paths(self, body: bytes):
        text = body.decode("utf-8", errors="replace")
        pages, errors = up.add_drop(self.store.manifest, text,
                                    roots=self.store.roots)
        self.store.save()
        self._json({"added": [p.seq for p in pages], "errors": errors,
                    "pages": len(self.store.manifest.pages)})


def make_server(store: JobStore, host: str = "127.0.0.1", port: int = 8799,
                verbose: bool = False) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": store})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.verbose = verbose
    return httpd
