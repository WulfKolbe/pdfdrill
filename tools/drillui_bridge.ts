#!/usr/bin/env bun
/**
 * drillui_bridge.ts — a tiny Bun bridge between the browser terminal
 * (drillui_term.html) and a live `drillui_chat.py <doc>` REPL subprocess.
 *
 * A browser can't spawn a process, so this does it: one subprocess per
 * WebSocket connection, kept alive for the whole session so drillui_chat's
 * own continuity history works. The REPL writes its `\n? ` prompt to stdout
 * after each turn; we detect that, strip it, and tell the client it's its
 * turn to read a line (the browser owns the visible prompt).
 *
 *   bun drillui_bridge.ts <doc> [--src src] [--model NAME] [--k N]
 *                                [--no-store] [--port 8787]
 *                                [-- <extra args passed straight to drillui_chat>]
 *
 * Stdlib + Bun only. Serves the sibling drillui_term.html at http://localhost:<port>/.
 */

import { dirname, join, resolve, normalize, sep, extname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";

// ---- arg parsing -----------------------------------------------------------
// Self-locate the repo root from THIS file (tools/drillui_bridge.ts → repo),
// so launch location never matters: `bun tools/drillui_bridge.ts` from the repo
// root and `cd tools && bun run drillui_bridge.ts` behave identically. Using
// process.cwd() made artifacts-root = wherever you launched (e.g. tools/), so
// produced files under data/*.drill or ~/Downloads/*.drill weren't served.
const REPO_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const argv = process.argv.slice(2);
let doc = "";
let src: string | null = null;
let model: string | null = null;
let k = 8;
let store = true;
let port = 8787;
let artifactsRoot = REPO_ROOT;       // default; --artifacts overrides
let opener: string | null = null;    // host browser launcher; null → auto/none
let chatPath: string | null = null;  // explicit path to drillui_chat.py
let pythonBin = process.env.DRILLUI_PYTHON ?? "python3";
const passthrough: string[] = [];

for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--") { passthrough.push(...argv.slice(i + 1)); break; }
  else if (a === "--src") src = argv[++i];
  else if (a === "--model") model = argv[++i];
  else if (a === "--k") k = parseInt(argv[++i], 10);
  else if (a === "--no-store") store = false;
  else if (a === "--port") port = parseInt(argv[++i], 10);
  else if (a === "--artifacts") artifactsRoot = argv[++i];
  else if (a === "--opener") opener = argv[++i];          // e.g. firefox, xdg-open
  else if (a === "--no-open") opener = "";                // disable host-open
  else if (a === "--chat") chatPath = argv[++i];          // path to drillui_chat.py
  else if (a === "--python") pythonBin = argv[++i];       // interpreter (e.g. a venv python)
  else if (!doc && !a.startsWith("-")) doc = a;
  else passthrough.push(a);
}

if (argv.includes("-h") || argv.includes("--help")) {
  console.error(
    "usage: bun drillui_bridge.ts [doc] [flags]      (see tools/DRILLUI.md)\n" +
    "  [doc]  OPTIONAL — a drilled PDF/.md, an https URL, or a bare arXiv id.\n" +
    "         Omit it to start with an empty context and use `add <doc>` in the\n" +
    "         terminal (the doc is optional now that `add` exists).\n" +
    "  Zero config from the repo: `bun tools/drillui_bridge.ts data/paper.pdf`\n" +
    "  finds drillui_chat.py as its sibling and pdfdrill in ../src.\n" +
    "  flags: [--port N] [--model NAME] [--k N] [--no-store] [--python BIN]\n" +
    "         [--chat PATH] [--src DIR] [--artifacts DIR]\n" +
    "         [--opener firefox|xdg-open|...] [--no-open]");
  process.exit(0);
}

// Resolve drillui_chat.py to an ABSOLUTE, EXISTING path. Order: --chat flag,
// $DRILLUI_CHAT, then a sibling of this bridge. We never hand python a bare or
// unverified name — if nothing resolves to a real file, we say exactly what was
// tried and exit, instead of letting python fail with a cryptic "can't open".
function resolveChatScript(): string {
  const tried: string[] = [];
  for (const cand of [chatPath, process.env.DRILLUI_CHAT,
                      join(dirname(fileURLToPath(import.meta.url)), "drillui_chat.py")]) {
    if (!cand) continue;
    const abs = resolve(cand);
    tried.push(abs);
    if (existsSync(abs)) return abs;
  }
  console.error(
    "drillui_bridge: could not find drillui_chat.py.\n" +
    "  Point at it explicitly with  --chat PATH  (PATH = the path to your\n" +
    "  drillui_chat.py), or set the DRILLUI_CHAT environment variable.\n" +
    (tried.length ? "  tried: " + tried.join(", ") : "  no candidate given"));
  process.exit(2);
}
const CHAT_SCRIPT = resolveChatScript();

function buildCmd(): string[] {
  // doc is OPTIONAL — without it drillui_chat starts empty (use `add` in the UI).
  const cmd = [pythonBin, CHAT_SCRIPT, ...(doc ? [doc] : []), "--k", String(k)];
  if (src) cmd.push("--src", src);
  if (model) cmd.push("--model", model);
  if (!store) cmd.push("--no-store");
  cmd.push(...passthrough);
  return cmd;
}

const HTML_PATH = join(dirname(fileURLToPath(import.meta.url)), "drillui_term.html");

// ---- artifact serving ------------------------------------------------------
// pdfdrill prints artifact paths RELATIVE TO THE DOCUMENT'S folder (e.g.
// "1906.02691.pdf.drill/formula-report.html" for a doc in data/), but the
// bridge's cwd is the repo root — so resolving against cwd alone misses the
// "data/" segment and 404s. We therefore resolve against BOTH the cwd
// (artifactsRoot) AND the document's own directory, and serve whichever exists.
const ART_ROOT = resolve(artifactsRoot);
const DOC_DIR = (() => {
  if (!doc) return null;
  try { const abs = resolve(doc); return existsSync(abs) ? dirname(abs) : null; }
  catch { return null; }
})();
// The pdfdrill download dir (config `download_dir`, default ~/Downloads) is where
// drilled docs + their `.drill` artifacts (report.html / *.md / *.json …) live, so
// serve from there too — else links to ~/Downloads/<doc>.drill/* would 404.
const DOWNLOAD_DIR = (() => {
  const cands = [process.env.PDFDRILL_CONFIG,
                 join(homedir(), ".config", "pdfdrill", "config.json"),
                 join(homedir(), ".pdfdrill.json")].filter(Boolean) as string[];
  for (const c of cands) {
    try {
      const d = JSON.parse(readFileSync(c, "utf8"));
      if (d && d.download_dir)
        return resolve(String(d.download_dir).replace(/^~(?=$|\/)/, homedir()));
    } catch { /* not present / not json */ }
  }
  const dl = join(homedir(), "Downloads");
  return existsSync(dl) ? dl : null;
})();
const ART_ROOTS = [...new Set(
  [ART_ROOT, DOC_DIR, DOWNLOAD_DIR].filter(Boolean) as string[])];

// `add <doc>` can bring in a doc from ANY directory (e.g. ~/Scans/x.pdf). Its
// PDF + `.drill` artifacts then live outside cwd / the launch-doc dir / the
// download dir, so /artifact + /open would refuse them (the link is dead and the
// PDF won't open). Register the doc's own directory — expanding a leading ~ —
// so those files become servable. ART_ROOTS is a const array but we push to it.
function registerDocDir(rawPath: string): void {
  const p = rawPath.replace(/^~(?=$|\/)/, homedir());
  if (/^https?:\/\//i.test(p)) return;            // a URL, not a local file
  try {
    const dir = dirname(resolve(p));
    if (dir && !ART_ROOTS.includes(dir)) {
      ART_ROOTS.push(dir);
      console.error(`  + serving added-doc dir: ${dir}`);
    }
  } catch { /* ignore */ }
}

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
  ".svg": "image/svg+xml", ".pdf": "application/pdf",
  ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8", ".tex": "text/plain; charset=utf-8",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".txt": "text/plain; charset=utf-8",
};

/** A path under a single root, or null if it escapes that root (no traversal). */
function underRoot(root: string, p: string): string | null {
  const abs = resolve(root, normalize(p));         // relative → under root; absolute → as-is
  if (abs !== root && !abs.startsWith(root + sep)) return null;
  return abs;
}

/** Resolve a user path under ANY allowed root, preferring one where the file
 *  actually exists (so a doc-relative path like "X.pdf.drill/report.html"
 *  resolves under the doc dir). Falls back to the first root's path (which then
 *  404s with a real location) so callers can still report a sensible error. */
function safeResolve(p: string): string | null {
  if (!p) return null;
  let firstValid: string | null = null;
  for (const root of ART_ROOTS) {
    const abs = underRoot(root, p);
    if (!abs) continue;
    if (firstValid === null) firstValid = abs;
    if (existsSync(abs)) return abs;               // existing match wins
  }
  return firstValid;                               // none exist → first valid (will 404)
}

// ---- local image server (sidecar proxy) ------------------------------------
// The MathPix-free image source: `pdfdrill imageserve <doc>` serves the doc's
// local 600-DPI DZI pyramid as a drop-in cdn.mathpix.com (/cropped/<id>?…) plus
// the deep-zoom viewer (/viewer.html). The bridge spawns it LAZILY (first request
// to an image route) when the launch doc has a built pyramid, then proxies the
// image routes to it so the browser sees one same-origin host. Run `pdfdrill
// pyramid <doc>` first to build the tiles.
const IMG_PORT = port + 1;
const PDFDRILL_BIN = join(REPO_ROOT, "pdfdrill");   // the repo's PYTHONPATH wrapper
let imgProc: ReturnType<typeof Bun.spawn> | null = null;
let imgReady: Promise<number | null> | null = null;

// The ACTIVE doc the viewer routes serve. Starts as the launch doc, and — the
// "add rischextra.pdf, pyramid, viewer: file not found" fix — SWITCHES when the
// user `add`s a doc in the terminal, so the pyramid/viewer of the doc you are
// actually working on is the one the bridge serves.
let activeDoc = doc;

/** The ACTIVE doc's absolute path IF it has a built pyramid (<doc>.drill/viewer/
 *  manifest.json), else null (URL/arXiv-id docs and un-pyramided docs included). */
function docWithPyramid(): string | null {
  if (!activeDoc) return null;
  try {
    const abs = resolve(activeDoc.replace(/^~(?=$|\/)/, homedir()));
    if (!existsSync(abs)) return null;               // URL / arXiv id / missing
    const mani = join(dirname(abs), basename(abs) + ".drill", "viewer", "manifest.json");
    return existsSync(mani) ? abs : null;
  } catch { return null; }
}

/** Switch the active doc (the terminal's `add`). Kills a sidecar bound to the
 *  previous doc so the next /cropped respawns it for the new one. */
function setActiveDoc(rawPath: string): void {
  if (/^https?:\/\//i.test(rawPath)) return;         // URLs resolve via pdfdrill later
  const next = rawPath.replace(/^~(?=$|\/)/, homedir());
  if (next === activeDoc) return;
  activeDoc = next;
  if (imgProc) { try { imgProc.kill(); } catch {} }  // sidecar was for the old doc
}

// ---- auto-build: the state machine reacting to the missing pyramid ----------
// Opening /viewer.html for a doc WITHOUT a pyramid used to dead-end in a JSON
// 404. Now the bridge STARTS `pdfdrill pyramid --offline` itself (once per doc,
// no timeout — a 211-page 600-DPI build takes many minutes) and serves a live
// progress page that polls /pyramid-status and reloads into the real viewer
// when the manifest lands. build.json ({done,total}) is the builder's marker.
let pyramidBuildDoc: string | null = null;
let pyramidBuildProc: ReturnType<typeof Bun.spawn> | null = null;

function activeDocAbs(): string | null {
  if (!activeDoc || /^https?:\/\//i.test(activeDoc)) return null;
  const abs = resolve(activeDoc.replace(/^~(?=$|\/)/, homedir()));
  return existsSync(abs) ? abs : null;
}

function activeViewerDirAbs(): string | null {
  const abs = activeDocAbs();
  return abs ? join(dirname(abs), basename(abs) + ".drill", "viewer") : null;
}

function ensurePyramidBuild(): void {
  const abs = activeDocAbs();
  if (!abs || docWithPyramid()) return;             // nothing to build / already there
  if (pyramidBuildProc && pyramidBuildDoc === abs) return;   // one build per doc
  // a build from a previous bridge (orphan) keeps its build.json fresh — if the
  // marker was touched in the last 2 minutes, someone is building; don't clash.
  const vd = activeViewerDirAbs();
  if (vd && existsSync(join(vd, "build.json"))) {
    try {
      const age = Date.now() - Bun.file(join(vd, "build.json")).lastModified;
      if (age < 120_000) return;
    } catch { /* stat race — proceed */ }
  }
  const env: Record<string, string> = { ...process.env as any };
  env.PYTHONPATH = [src ? resolve(src) : join(REPO_ROOT, "src"), env.PYTHONPATH]
    .filter(Boolean).join(":");
  console.error(`  auto-building pyramid for ${abs} (pdfdrill pyramid --offline)`);
  pyramidBuildDoc = abs;
  pyramidBuildProc = Bun.spawn({
    cmd: [PDFDRILL_BIN, "pyramid", abs, "--offline"],
    env, stdout: "ignore", stderr: "ignore",
  });
  pyramidBuildProc.exited.then(() => { pyramidBuildProc = null; });
}

function pyramidStatus(): Response {
  const vd = activeViewerDirAbs();
  const ready = docWithPyramid() !== null;
  let progress: any = null;
  if (!ready && vd && existsSync(join(vd, "build.json"))) {
    try { progress = JSON.parse(readFileSync(join(vd, "build.json"), "utf8")); }
    catch { /* mid-write */ }
  }
  return Response.json({ ready, building: pyramidBuildProc !== null,
                         doc: activeDoc || null, progress },
                       { headers: { "cache-control": "no-store" } });
}

const WAIT_HTML = (docName: string) => `<!doctype html><html><head><meta charset="utf-8">
<title>Building pyramid — ${docName}</title><style>
:root{color-scheme:dark}body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#0d0f12;color:#e6e9ee;font:15px/1.5 ui-sans-serif,system-ui,sans-serif}
.card{max-width:520px;padding:28px 32px;background:#16191f;border:1px solid #262b33;border-radius:12px}
h1{font-size:17px;margin:0 0 8px}p{color:#8a93a0;margin:8px 0}
.bar{height:8px;background:#1e232b;border-radius:5px;overflow:hidden;margin:14px 0}
.bar div{height:100%;width:0;background:#6ea8fe;transition:width .8s}
code{background:#1e232b;border-radius:4px;padding:1px 6px}</style></head><body>
<div class="card"><h1>Building the 600-DPI pyramid…</h1>
<p><code>${docName}</code> has no deep-zoom pyramid yet — pdfdrill is building it
now (one page at a time; large documents take a few minutes).</p>
<div class="bar"><div id="b"></div></div><p id="s">starting…</p></div>
<script>
async function poll(){
  try{
    const r = await fetch("/pyramid-status", {cache:"no-store"});
    const j = await r.json();
    if (j.ready) { location.reload(); return; }
    const p = j.progress;
    if (p && p.total) {
      document.getElementById("b").style.width = Math.round(100*p.done/p.total)+"%";
      document.getElementById("s").textContent = "page "+p.done+" / "+p.total+" tiled";
    } else if (!j.building) {
      document.getElementById("s").textContent =
        "no build running — type 'pyramid' in the drillui terminal, then keep this page open";
    }
  }catch(e){}
  setTimeout(poll, 2000);
}
poll();
</script></body></html>`;

/** Spawn `pdfdrill imageserve` once (foreground child the bridge owns), wait for
 *  /healthz, and return its port. null when the doc has no pyramid. */
async function ensureImageServer(): Promise<number | null> {
  if (imgProc) return IMG_PORT;
  if (imgReady) return imgReady;
  const docAbs = docWithPyramid();
  if (!docAbs) return null;
  imgReady = (async () => {
    const env: Record<string, string> = { ...process.env as any };
    env.PYTHONPATH = [src ? resolve(src) : join(REPO_ROOT, "src"), env.PYTHONPATH]
      .filter(Boolean).join(":");
    imgProc = Bun.spawn({
      cmd: [PDFDRILL_BIN, "imageserve", docAbs, "--port", String(IMG_PORT)],
      env, stdout: "ignore", stderr: "ignore",
    });
    imgProc.exited.then(() => { imgProc = null; imgReady = null; });  // allow respawn
    for (let i = 0; i < 60; i++) {                    // up to ~6s for the server to bind
      try { if ((await fetch(`http://127.0.0.1:${IMG_PORT}/healthz`)).ok) return IMG_PORT; }
      catch { /* not up yet */ }
      await new Promise((r) => setTimeout(r, 100));
    }
    return IMG_PORT;                                  // best effort (proxy will 502 if dead)
  })();
  return imgReady;
}

// The deep-zoom VIEWER only needs static files (viewer.html / manifest.json /
// tiles/*) — exactly what `python3 -m http.server` serves. Only /cropped/* (the
// cdn.mathpix.com replacement for TiddlyWiki) needs the Python sidecar. So bun
// serves the static viewer DIRECTLY (no sidecar to spawn = the viewer always
// works), and we proxy only /cropped to the lazily-spawned imageserve.
const IMG_STATIC = (p: string) =>
  p.startsWith("/tiles/") || p === "/viewer.html" || p === "/manifest.json" ||
  p === "/viewer_offline.html" || p === "/openseadragon.min.js";  // the offline bundle
                                                                  // + its local OSD

/** The launch doc's <doc>.drill/viewer/ dir, if a pyramid was built. */
function viewerDir(): string | null {
  const docAbs = docWithPyramid();   // already verifies <doc>.drill/viewer/manifest.json
  return docAbs ? join(dirname(docAbs), basename(docAbs) + ".drill", "viewer") : null;
}

/** Serve a static viewer file (viewer.html/manifest.json/tiles/*) straight from
 *  the pyramid dir — bun IS the http.server, so the viewer needs no sidecar. */
const PKG_VIEWER_HTML = join(REPO_ROOT, "tools", "imageserver", "viewer.html");

async function serveViewerStatic(url: URL): Promise<Response> {
  const vd = viewerDir();
  if (!vd) {
    // /viewer.html without a pyramid: START THE BUILD (state machine) and
    // serve the live progress page — never a dead JSON end. Other static
    // routes keep 404ing until the manifest lands (the page polls status).
    if (url.pathname === "/viewer.html" || url.pathname === "/viewer_offline.html") {
      ensurePyramidBuild();
      const name = activeDoc ? basename(activeDoc) : (doc || "no document");
      return new Response(WAIT_HTML(name), { headers: {
        "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
      } });
    }
    return Response.json(
      { error: `no local pyramid for ${activeDoc || doc || "the doc"} — run ` +
               `\`pdfdrill pyramid\` (or type \`pyramid\` in the terminal) first` },
      { status: 404 });
  }
  // Always serve the CURRENT package viewer.html (the per-doc copy can be stale
  // from an older `pyramid` build); manifest.json + tiles/* come from the pyramid.
  if (url.pathname === "/viewer.html" && existsSync(PKG_VIEWER_HTML)) {
    return new Response(Bun.file(PKG_VIEWER_HTML), { headers: {
      "content-type": "text/html; charset=utf-8",
      "access-control-allow-origin": "*", "cache-control": "no-cache",
    } });
  }
  const rel = decodeURIComponent(url.pathname.replace(/^\/+/, ""));
  const abs = resolve(vd, normalize(rel));
  if (abs !== vd && !abs.startsWith(vd + sep))            // no traversal out of viewer/
    return new Response("forbidden", { status: 403 });
  const f = Bun.file(abs);
  if (!(await f.exists())) return new Response("not found", { status: 404 });
  const ext = extname(abs).toLowerCase();
  const ct = ext === ".dzi" ? "application/xml"
                            : (MIME[ext] ?? "application/octet-stream");
  return new Response(f, { headers: {
    "content-type": ct,
    "access-control-allow-origin": "*",
    "cache-control": url.pathname.startsWith("/tiles/")
      ? "public, max-age=86400" : "no-cache",   // tiles immutable; viewer/manifest revalidate
  } });
}

/** Proxy a /cropped/* request to the local sidecar, spawning it on first use. */
async function proxyImage(req: Request, url: URL): Promise<Response> {
  const imgPort = await ensureImageServer();
  if (imgPort == null)
    return Response.json(
      { error: `no local pyramid for ${activeDoc || doc || "the doc"} — run ` +
               `\`pdfdrill pyramid\` first` },
      { status: 404 });
  const target = `http://127.0.0.1:${imgPort}${url.pathname}${url.search}`;
  try {
    const r = await fetch(target, {
      method: req.method,
      headers: req.headers,
      body: (req.method === "GET" || req.method === "HEAD") ? undefined : await req.arrayBuffer(),
    });
    return new Response(r.body, { status: r.status, headers: r.headers });
  } catch (e) {
    return new Response("image server unreachable: " + String(e), { status: 502 });
  }
}

// Kill the image-server sidecar when the bridge goes away — incl. SIGHUP (the
// terminal was closed). (The server also self-exits via --die-with-parent if it
// is ever orphaned, covering an uncatchable SIGKILL of the bridge.)
//
// IMPORTANT: registering a SIGINT/SIGTERM handler OVERRIDES the runtime's default
// "exit on Ctrl-C" — so the handler MUST call process.exit() itself, otherwise
// Ctrl-C only runs cleanup and the bridge keeps serving (the "can't stop it with
// Ctrl-C, processes pile up" bug). The "exit" event is cleanup-only (no exit call).
const killSidecar = () => { try { imgProc?.kill(); } catch {} };
process.on("exit", killSidecar);
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"] as const)
  process.on(sig as any, () => { killSidecar(); process.exit(0); });

// Host opener: explicit --opener wins; else auto-detect by platform. "" disables.
function resolveOpener(): string[] | null {
  if (opener === "") return null;
  if (opener) return opener.split(" ");
  const plat = process.platform;
  if (plat === "darwin") return ["open"];
  if (plat === "win32") return ["cmd", "/c", "start", ""];
  return ["xdg-open"];   // Linux (respects the user's default browser, e.g. Firefox)
}
const OPENER = resolveOpener();

// ---- per-connection session ------------------------------------------------
type Session = {
  proc: ReturnType<typeof Bun.spawn>;
  out: string;            // accumulator until the REPL prompt appears
  closed: boolean;
  lastInput: string;      // last line forwarded to the REPL (to detect `pyramid`)
  viewerAnnounced: boolean; // sent the client a `viewer` message yet?
};

const PROMPT_TAIL = "\n? ";   // exactly what drillui_chat's input("\n? ") emits

function send(ws: any, obj: unknown) {
  try { ws.send(JSON.stringify(obj)); } catch { /* socket gone */ }
}

function spawnSession(ws: any): Session {
  const proc = Bun.spawn({
    cmd: buildCmd(),
    cwd: ART_ROOT,                  // pdfdrill writes report.html etc. here → served at /artifact
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env, PYTHONUNBUFFERED: "1", TERM: "dumb" },
  });
  const sess: Session = { proc, out: "", closed: false, lastInput: "", viewerAnnounced: false };

  // stdout: accumulate until drillui's "\n? " prompt, then flush the turn body
  // (prompt stripped) and signal "ready". A short debounce guards the rare case
  // where an ANSWER itself contains "\n? ": the real prompt is the last write
  // before the process blocks on stdin, so nothing follows it and the quiet
  // window confirms it; any answer-internal "\n? " is cancelled by more output.
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  const QUIET_MS = 20;
  const flush = () => {
    flushTimer = null;
    if (!sess.out.endsWith(PROMPT_TAIL)) return;
    const body = sess.out.slice(0, -PROMPT_TAIL.length);  // drop exactly "\n? "
    sess.out = "";
    if (body.length) send(ws, { type: "output", data: body });
    // A `pyramid` run just built the doc's local tiles → the deep-zoom viewer is
    // now available. Announce it once (auto-open when the user actually ran
    // pyramid), and pre-spawn the image-server sidecar so the page loads instantly.
    if (!sess.viewerAnnounced && docWithPyramid()) {
      sess.viewerAnnounced = true;
      const open = /^\s*pyramid\b/.test(sess.lastInput);
      send(ws, { type: "viewer", url: "/viewer.html", open });  // sidecar spawns lazily on page load
    }
    send(ws, { type: "ready" });
  };
  (async () => {
    const dec = new TextDecoder();
    for await (const chunk of proc.stdout as ReadableStream<Uint8Array>) {
      sess.out += dec.decode(chunk, { stream: true });
      if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }  // new output cancels pending flush
      if (sess.out.endsWith(PROMPT_TAIL)) flushTimer = setTimeout(flush, QUIET_MS);
    }
  })().catch(() => {});

  // stderr: surface immediately (drillui prints "error: …" here)
  (async () => {
    const dec = new TextDecoder();
    for await (const chunk of proc.stderr as ReadableStream<Uint8Array>) {
      const s = dec.decode(chunk, { stream: true });
      if (s) send(ws, { type: "output", stream: "stderr", data: "\x1b[38;2;251;73;52m" + s + "\x1b[0m" });
    }
  })().catch(() => {});

  // exit
  proc.exited.then((code) => {
    sess.closed = true;
    send(ws, { type: "exit", code });
  });

  return sess;
}

// ---- server ----------------------------------------------------------------
const server = Bun.serve<{ sess: Session | null }>({
  port,
  async fetch(req, server) {
    const url = new URL(req.url);
    if (url.pathname === "/ws") {
      if (server.upgrade(req, { data: { sess: null } })) return;
      return new Response("expected websocket", { status: 426 });
    }

    // local deep-zoom viewer: bun serves the static tiles/manifest/viewer.html
    // directly (no sidecar needed — this is what makes the viewer just work), and
    // only /cropped/* (the cdn.mathpix.com replacement) goes to the Python sidecar.
    if (url.pathname === "/pyramid-status") return pyramidStatus();
    if (url.pathname.startsWith("/cropped/")) return proxyImage(req, url);
    if (IMG_STATIC(url.pathname)) return serveViewerStatic(url);

    // serve a pdfdrill output file (under ART_ROOT only)
    if (url.pathname === "/artifact") {
      const abs = safeResolve(url.searchParams.get("path") || "");
      if (!abs) return new Response("forbidden path", { status: 403 });
      const f = Bun.file(abs);
      if (!(await f.exists())) return new Response("not found", { status: 404 });
      const ct = MIME[extname(abs).toLowerCase()] ?? "application/octet-stream";
      // filename for save-as: the REAL basename (e.g. 2110.13883.tiddlers.json),
      // not "artifact" (the route). `inline` keeps the in-tab viewer; the browser's
      // own Save uses this name, as does the Outputs `save ⤓` link.
      const fname = (abs.split("/").pop() || "artifact").replace(/["\\\r\n]/g, "");
      return new Response(f, { headers: {
        "content-type": ct,
        "content-disposition": `inline; filename="${fname}"`,
      } });
    }

    // open a file in the user's own browser on the host machine
    if (url.pathname === "/open" && req.method === "POST") {
      if (!OPENER) return new Response("host-open disabled", { status: 403 });
      let body: any; try { body = await req.json(); } catch { return new Response("bad json", { status: 400 }); }
      // Open a URL in the host's browser (xdg-open/open/…). This is the reliable
      // path for `open <url>` typed in the terminal: no popup blocker, no lost
      // user-activation (which silently kills an async window.open / a.click).
      const rawUrl = String(body?.url || "");
      if (rawUrl) {
        if (!/^https?:\/\//i.test(rawUrl))
          return new Response("only http(s) urls", { status: 400 });
        try {
          Bun.spawn({ cmd: [...OPENER, rawUrl], stdout: "ignore", stderr: "ignore" });
          return Response.json({ ok: true });
        } catch (e) { return new Response("open failed: " + String(e), { status: 500 }); }
      }
      // else open a FILE the bridge serves (must exist under an allowed root)
      const abs = safeResolve(String(body?.path || ""));
      if (!abs) return new Response("forbidden path", { status: 403 });
      if (!(await Bun.file(abs).exists())) return new Response("not found", { status: 404 });
      try {
        Bun.spawn({ cmd: [...OPENER, abs], stdout: "ignore", stderr: "ignore" });
        return Response.json({ ok: true });
      } catch (e) {
        return new Response("open failed: " + String(e), { status: 500 });
      }
    }

    // serve the terminal page (default route). no-store: we iterate on this file
    // a lot — a stale cached copy is a real source of "it doesn't work" (old JS).
    const file = Bun.file(HTML_PATH);
    if (await file.exists()) {
      return new Response(file, { headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store, must-revalidate",
      } });
    }
    return new Response("drillui_term.html not found next to the bridge", { status: 404 });
  },
  websocket: {
    open(ws) {
      const sess = spawnSession(ws);
      ws.data.sess = sess;
      send(ws, {
        type: "hello",
        doc: doc || "(none — use add)",
        model: model ?? "default",
        k,
        store,
        hostOpen: OPENER !== null,
        viewer: docWithPyramid() ? "/viewer.html" : null,  // local deep-zoom image source
      });
      // if the doc already had a pyramid, the hello above carried the link — don't
      // re-announce (or auto-open) it on the first turn. Only a fresh `pyramid`
      // run (the not-yet-available → available transition) auto-opens the viewer.
      sess.viewerAnnounced = docWithPyramid() !== null;
    },
    message(ws, raw) {
      const sess = ws.data.sess;
      if (!sess || sess.closed) return;
      let msg: any;
      try { msg = JSON.parse(String(raw)); } catch { return; }
      if (msg.type === "input" && typeof msg.data === "string") {
        // `add <doc>` from an arbitrary dir → register that dir so its PDF +
        // .drill artifacts are servable (mirrors the ~ expansion drillui_chat does).
        // `add` paths may contain BLANKS/parens ("The Everything Kids … (z-lib
        // .org).pdf"): take the REST OF THE LINE, strip shell-style quotes, and
        // prefer the whole rest when it names an existing file; otherwise fall
        // back to the first token (the multi-doc `add a.pdf b.pdf` form).
        const m = msg.data.match(/^\s*add\s+(.+?)\s*$/);
        if (m) {
          let target = m[1].replace(/^(["'])(.*)\1$/, "$2");   // unquote
          const whole = resolve(target.replace(/^~(?=$|\/)/, homedir()));
          if (!existsSync(whole)) {
            const first = m[1].match(/^(["'])(.+?)\1|^(\S+)/);
            target = first ? (first[2] ?? first[3] ?? target) : target;
          }
          registerDocDir(target);                        // its .drill artifacts servable
          setActiveDoc(target);                          // viewer routes follow the add
          // announce the viewer for the NEW doc: an existing pyramid gets its
          // Outputs-panel link right away (open:false — no surprise tab); a
          // missing one re-arms so the next `pyramid` run announces + opens.
          const has = docWithPyramid() !== null;
          sess.viewerAnnounced = has;
          if (has) send(ws, { type: "viewer", url: "/viewer.html", open: false });
        }
        sess.lastInput = msg.data;                       // remember the verb (detect `pyramid`)
        // feed one line to the REPL; the trailing newline makes input() return
        sess.proc.stdin.write(msg.data + "\n");
        sess.proc.stdin.flush();
      }
    },
    close(ws) {
      const sess = ws.data.sess;
      if (sess && !sess.closed) { try { sess.proc.kill(); } catch {} }
    },
  },
});

console.error(`drillui bridge → http://localhost:${server.port}/`);
console.error(`  chat: ${pythonBin} ${CHAT_SCRIPT}`);
console.error(`  doc=${doc}  model=${model ?? "default"}  k=${k}  store=${store}`);
console.error(`  cwd / artifacts root: ${ART_ROOT}`);
console.error(`  host-open: ${OPENER ? OPENER.join(" ") : "disabled"}`);
console.error(`  image server: ${docWithPyramid()
  ? `lazy /cropped,/tiles,/viewer.html → pdfdrill imageserve :${IMG_PORT}`
  : "no local pyramid (run `pdfdrill pyramid <doc>` to enable /viewer.html)"}`);
console.error(`  cmd: ${buildCmd().join(" ")}`);
