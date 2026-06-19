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

import { dirname, join, resolve, normalize, sep, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

// ---- arg parsing -----------------------------------------------------------
const argv = process.argv.slice(2);
let doc = "";
let src: string | null = null;
let model: string | null = null;
let k = 8;
let store = true;
let port = 8787;
let artifactsRoot = process.cwd();   // where pdfdrill writes its files (its CWD)
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
const ART_ROOTS = [...new Set([ART_ROOT, DOC_DIR].filter(Boolean) as string[])];

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
  const sess: Session = { proc, out: "", closed: false };

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

    // serve a pdfdrill output file (under ART_ROOT only)
    if (url.pathname === "/artifact") {
      const abs = safeResolve(url.searchParams.get("path") || "");
      if (!abs) return new Response("forbidden path", { status: 403 });
      const f = Bun.file(abs);
      if (!(await f.exists())) return new Response("not found", { status: 404 });
      const ct = MIME[extname(abs).toLowerCase()] ?? "application/octet-stream";
      return new Response(f, { headers: { "content-type": ct } });
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
      });
    },
    message(ws, raw) {
      const sess = ws.data.sess;
      if (!sess || sess.closed) return;
      let msg: any;
      try { msg = JSON.parse(String(raw)); } catch { return; }
      if (msg.type === "input" && typeof msg.data === "string") {
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
console.error(`  cmd: ${buildCmd().join(" ")}`);
