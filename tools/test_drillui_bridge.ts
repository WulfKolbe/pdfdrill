#!/usr/bin/env bun
/**
 * Integration test for drillui_bridge.ts — spawns the real bridge against a
 * drilled doc and exercises the HTTP routes + the WebSocket REPL round-trip.
 *
 *   bun tools/test_drillui_bridge.ts <drilled.pdf>
 *
 * Asserts: GET / serves the terminal HTML; the WS handshake sends `hello`; a
 * pdfdrill COMMAND typed in the terminal (e.g. `status`) runs on the doc and
 * its output comes back (NOT routed to an LLM); GET /artifact serves a file
 * under the root; POST /open is refused when host-open is disabled.
 */
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const doc = process.argv[2] ?? "data/1906.02691.pdf";
const PORT = 8799;
const HERE = dirname(fileURLToPath(import.meta.url));
const BRIDGE = join(HERE, "drillui_bridge.ts");

let fails = 0;
const ok = (name: string, cond: boolean, extra = "") => {
  console.log(`  [${cond ? "ok" : "FAIL"}] ${name}${extra ? "  — " + extra : ""}`);
  if (!cond) fails++;
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// --- spawn the bridge (host-open disabled so POST /open must 403) ------------
const proc = Bun.spawn({
  cmd: ["bun", BRIDGE, doc, "--port", String(PORT), "--no-open"],
  cwd: resolve(HERE, ".."),
  stdout: "pipe", stderr: "pipe",
  env: { ...process.env },
});

// wait for the server to answer GET /
const base = `http://localhost:${PORT}`;
let up = false;
for (let i = 0; i < 60; i++) {
  try { const r = await fetch(base + "/"); if (r.ok) { up = true; break; } } catch {}
  await sleep(250);
}
ok("server is up (GET /)", up);

if (up) {
  // 1) HTML page + the `open`-is-local contract (regression guard for
  //    "open url called the LLM"): promptLoop must call handleLocal and bail
  //    out BEFORE it forwards the line to the Python REPL via ws.send.
  const html = await (await fetch(base + "/")).text();
  ok("GET / serves the terminal HTML", html.includes("drillui") && html.includes("xterm"));
  const idxHandle = html.indexOf("if (this.handleLocal(q)) continue;");
  const idxSend = html.indexOf('this.ws.send(JSON.stringify({ type:"input"');
  ok("promptLoop intercepts local commands before forwarding",
     idxHandle > -1 && idxSend > -1 && idxHandle < idxSend);
  ok("handleLocal treats `open` as a local command",
     /cmd === "open"/.test(html) && /localOpen\(arg\)/.test(html));

  // 2) artifact serving (serve this test file itself, which is under the root)
  const ar = await fetch(base + "/artifact?path=" + encodeURIComponent("tools/drillui_bridge.ts"));
  ok("GET /artifact serves a file under root", ar.ok);
  const bad = await fetch(base + "/artifact?path=" + encodeURIComponent("../../etc/passwd"));
  ok("GET /artifact refuses path traversal", bad.status === 403);

  // 2b) DOC-RELATIVE artifact: pdfdrill prints paths relative to the DOC's
  //     folder (e.g. "1906.02691.pdf.drill/model.docmodel.json" for a doc in
  //     data/), not the bridge cwd. This must still resolve (the report-404 bug).
  const stem = (doc.split("/").pop() || doc);
  const docRel = `${stem}.drill/model.docmodel.json`;
  const dr = await fetch(base + "/artifact?path=" + encodeURIComponent(docRel));
  ok("GET /artifact resolves a DOC-relative path (report-404 fix)", dr.ok, docRel);

  // 2c) local image-server proxy: with no built pyramid for the doc, an image
  //     route (/cropped, /tiles, /viewer.html, /manifest.json) degrades to a
  //     clear 404 JSON ("run `pdfdrill pyramid`") and never spawns a server.
  const cr = await fetch(base + "/cropped/anything.jpg?top_left_x=0&top_left_y=0&width=10&height=10");
  let crJson: any = null; try { crJson = await cr.json(); } catch {}
  ok("image route 404s without a pyramid (graceful)",
     cr.status === 404 && !!crJson && /pdfdrill pyramid/.test(crJson.error || ""));

  // 3) host-open disabled -> POST /open is 403
  const op = await fetch(base + "/open", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ path: "x.html" }),
  });
  ok("POST /open refused when host-open disabled", op.status === 403);

  // 4) WS round-trip: hello, then run a pdfdrill COMMAND on the doc
  const ws = new WebSocket(`ws://localhost:${PORT}/ws`);
  const got: any[] = [];
  let helloSeen = false, readyCount = 0;
  let outputAfterCmd = "";
  let sentCmd = false;

  await new Promise<void>((done) => {
    const finish = () => { try { ws.close(); } catch {} done(); };
    const timer = setTimeout(finish, 30000);
    ws.onmessage = (ev) => {
      const m = JSON.parse(String(ev.data));
      got.push(m);
      if (m.type === "hello") helloSeen = true;
      if (m.type === "output" && sentCmd) outputAfterCmd += m.data;
      if (m.type === "ready") {
        readyCount++;
        if (readyCount === 1) {                 // startup prompt -> now send a command
          sentCmd = true;
          ws.send(JSON.stringify({ type: "input", data: "status" }));
        } else if (readyCount >= 2) {           // command produced output + a new prompt
          clearTimeout(timer); finish();
        }
      }
    };
    ws.onerror = () => { clearTimeout(timer); finish(); };
  });

  ok("WS handshake sends hello", helloSeen);
  ok("WS: a command yields a second ready", readyCount >= 2);
  ok("WS: `status` ran on the doc (output came back)",
     /I have:|pages|model|transitions/i.test(outputAfterCmd),
     outputAfterCmd.slice(0, 80).replace(/\s+/g, " "));
}

try { proc.kill(); } catch {}

// --- viewer auto-open: a `pyramid` run that makes <doc>.drill/viewer/manifest.json
//     appear must push a `viewer` message with open:true (the drillui terminal then
//     opens the deep-zoom page). A DEDICATED bridge (fresh process, fresh session)
//     so there's no prior-session interaction. We simulate the build by creating the
//     manifest on the first prompt, then send `pyramid` — flush detects the
//     not-available→available transition. -----------------------------------------
const PORT3 = 8801;
const proc3 = Bun.spawn({
  cmd: ["bun", BRIDGE, doc, "--port", String(PORT3), "--no-open"],
  cwd: resolve(HERE, ".."),
  stdout: "ignore", stderr: "ignore",
  env: { ...process.env },
});
const base3 = `http://localhost:${PORT3}`;
let up3 = false;
for (let i = 0; i < 60; i++) {
  try { if ((await fetch(base3 + "/")).ok) { up3 = true; break; } } catch {}
  await sleep(250);
}
if (up3) {
  const { mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { basename } = await import("node:path");
  const viewerDir = join(dirname(resolve(doc)), basename(resolve(doc)) + ".drill", "viewer");
  let viewerMsg: any = null;
  const ws3 = new WebSocket(`ws://localhost:${PORT3}/ws`);
  await new Promise<void>((done) => {
    const finish = () => { try { ws3.close(); } catch {} done(); };
    const timer = setTimeout(finish, 40000);
    let r3 = 0, sent = false;
    ws3.onmessage = (ev) => {
      const m = JSON.parse(String(ev.data));
      if (m.type === "viewer") viewerMsg = m;
      if (m.type === "ready") {
        r3++;
        if (r3 === 1 && !sent) {                  // startup prompt passed with NO pyramid;
          sent = true;                            // simulate the build happening THIS turn
          mkdirSync(viewerDir, { recursive: true });
          writeFileSync(join(viewerDir, "manifest.json"), "[]");
          ws3.send(JSON.stringify({ type: "input", data: "pyramid" }));
        } else if (r3 >= 2) { clearTimeout(timer); finish(); }
      }
    };
    ws3.onerror = () => { clearTimeout(timer); finish(); };
  });
  try { rmSync(viewerDir, { recursive: true, force: true }); } catch {}   // cleanup
  ok("WS: `pyramid` run announces the viewer with open:true",
     !!viewerMsg && viewerMsg.open === true && /viewer\.html$/.test(viewerMsg.url || ""));
}
try { proc3.kill(); } catch {}

// --- viewer is served STATICALLY by bun (no Python sidecar needed) -------------
// The deep-zoom viewer only needs viewer.html / manifest.json / tiles/*, which bun
// serves straight from <doc>.drill/viewer/. Only /cropped/* needs the sidecar. This
// is the fix for "the viewer shows no data through the bridge (but http.server in
// the folder works)". We lay down a FAKE pyramid (no gs needed — this tests bun's
// static serving, not the tiles' validity) and fetch every viewer route.
const PORT4 = 8802;
{
  const { mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { basename, dirname } = await import("node:path");
  const vd = join(dirname(resolve(doc)), basename(resolve(doc)) + ".drill", "viewer");
  mkdirSync(join(vd, "tiles", "page01_files", "0"), { recursive: true });
  writeFileSync(join(vd, "manifest.json"),
    JSON.stringify([{ page: 1, dzi: "tiles/page01.dzi", width: 10, height: 10, levels: 1 }]));
  writeFileSync(join(vd, "viewer.html"), "<!doctype html><title>v</title>manifest.json");
  writeFileSync(join(vd, "tiles", "page01.dzi"), '<?xml version="1.0"?><Image/>');
  writeFileSync(join(vd, "tiles", "page01_files", "0", "0_0.jpg"), Buffer.from([0xff, 0xd8, 0xff, 0xd9]));
  const proc4 = Bun.spawn({
    cmd: ["bun", BRIDGE, doc, "--port", String(PORT4), "--no-open"],
    cwd: resolve(HERE, ".."), stdout: "ignore", stderr: "ignore", env: { ...process.env },
  });
  const b4 = `http://localhost:${PORT4}`;
  let up4 = false;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(b4 + "/")).ok) { up4 = true; break; } } catch {}
    await sleep(250);
  }
  if (up4) {
    const vh = await fetch(b4 + "/viewer.html");
    const vhBody = await vh.text();
    ok("bun serves /viewer.html (static, no sidecar)",
       vh.status === 200 && (vh.headers.get("content-type") || "").includes("text/html"));
    // it must be the CURRENT package viewer.html (with absolute-URL resolution),
    // NOT the per-doc fake we wrote — so an old pyramid's stale viewer never wins.
    ok("serves the current package viewer.html (abs-URL, not the stale doc copy)",
       /new URL\(rel, location\.href\)/.test(vhBody) && !vhBody.includes(">v</title>"));
    const mf = await fetch(b4 + "/manifest.json");
    ok("bun serves /manifest.json", mf.status === 200 && (await mf.json()).length === 1);
    const dz = await fetch(b4 + "/tiles/page01.dzi");
    ok("bun serves /tiles/*.dzi as XML",
       dz.status === 200 && (dz.headers.get("content-type") || "").includes("xml"));
    const tl = await fetch(b4 + "/tiles/page01_files/0/0_0.jpg");
    ok("bun serves a tile (max-age)", tl.status === 200 &&
       (tl.headers.get("cache-control") || "").includes("max-age"));
    // traversal: bun's URL normalizes ../ to /etc/passwd before we see it (so it
    // doesn't match /tiles/ and never reaches the file layer) — assert the SECURITY
    // property: /etc/passwd is never served, whatever the status.
    const trav = await fetch(b4 + "/tiles/%2e%2e/%2e%2e/%2e%2e/etc/passwd");
    const travBody = await trav.text();
    ok("static viewer never leaks /etc/passwd", !/root:.*:0:0:/.test(travBody));
    // the sidecar must NOT have been spawned just to view (only /cropped needs it)
    const psout = Bun.spawnSync({ cmd: ["bash", "-c", "ps -e -o args | grep mathpix_server.py | grep -v grep || true"] }).stdout.toString();
    ok("no Python sidecar spawned for the viewer", !psout.includes("mathpix_server.py"));
  } else {
    ok("bun serves /viewer.html (static, no sidecar)", false, "bridge4 did not come up");
  }
  try { proc4.kill(); } catch {}
  try { rmSync(vd, { recursive: true, force: true }); } catch {}
}

// --- host-open URL path: a second bridge with a HARMLESS opener (/bin/true) ---
// so we exercise POST /open {url} without actually launching a browser.
const PORT2 = 8800;
const proc2 = Bun.spawn({
  cmd: ["bun", BRIDGE, doc, "--port", String(PORT2), "--opener", "/bin/true"],
  cwd: resolve(HERE, ".."), stdout: "pipe", stderr: "pipe", env: { ...process.env },
});
const base2 = `http://localhost:${PORT2}`;
let up2 = false;
for (let i = 0; i < 60; i++) {
  try { if ((await fetch(base2 + "/")).ok) { up2 = true; break; } } catch {}
  await sleep(250);
}
ok("second bridge (with opener) is up", up2);
if (up2) {
  const okUrl = await fetch(base2 + "/open", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ url: "https://arxiv.org/pdf/1802.08153" }),
  });
  ok("POST /open {url} accepted (host opener)", okUrl.ok);
  const badUrl = await fetch(base2 + "/open", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ url: "javascript:alert(1)" }),
  });
  ok("POST /open refuses a non-http(s) url", badUrl.status === 400);
}
try { proc2.kill(); } catch {}

// --- SIGINT (Ctrl-C) MUST stop the bridge -------------------------------------
// Regression for "the bun program can't be stopped by Ctrl-C, so processes pile
// up": registering a SIGINT handler overrides the runtime's default exit, so the
// handler has to call process.exit() itself. Spawn a bridge, SIGINT it, and it
// must actually terminate.
{
  const PORT5 = 8803;
  const proc5 = Bun.spawn({
    cmd: ["bun", BRIDGE, doc, "--port", String(PORT5), "--no-open"],
    cwd: resolve(HERE, ".."), stdout: "ignore", stderr: "ignore", env: { ...process.env },
  });
  let up5 = false;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(`http://localhost:${PORT5}/`)).ok) { up5 = true; break; } } catch {}
    await sleep(250);
  }
  if (up5) {
    proc5.kill("SIGINT");                       // the Ctrl-C signal
    const exited = await Promise.race([
      proc5.exited.then(() => true),
      sleep(6000).then(() => false),            // must exit well within 6s
    ]);
    ok("SIGINT (Ctrl-C) stops the bridge", exited);
    if (!exited) { try { proc5.kill("SIGKILL"); } catch {} }
  } else {
    ok("SIGINT (Ctrl-C) stops the bridge", false, "bridge5 did not come up");
  }
}

// --- viewer routes FOLLOW `add` (the "add + pyramid -> file not found" fix) ----
// A bridge launched with doc A; the user `add`s doc B (which has a pyramid);
// /viewer.html, /manifest.json AND the offline bundle must then serve from B.
const PORT6 = 8804;
{
  const { mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { basename, dirname } = await import("node:path");
  const os = await import("node:os");
  const tmp = await import("node:fs/promises").then(f => f.mkdtemp(join(os.tmpdir(), "adddoc-")));
  const NASTY = "The Everything Kids Giant Book of Jokes, Riddles and " +
    "Brain Teasers (Dahl, Wagner and Weintraub.) (z-lib.org).pdf";
  const docB = join(tmp, NASTY);
  writeFileSync(docB, "%PDF-1.4");
  const vd = join(tmp, NASTY + ".drill", "viewer");
  mkdirSync(join(vd, "tiles"), { recursive: true });
  writeFileSync(join(vd, "manifest.json"),
    JSON.stringify([{ page: 1, dzi: "tiles/page01.dzi", width: 10, height: 10, levels: 1 }]));
  writeFileSync(join(vd, "tiles", "page01.dzi"), '<?xml version="1.0"?><Image/>');
  writeFileSync(join(vd, "viewer_offline.html"), "<!doctype html>OFFLINE-B");
  writeFileSync(join(vd, "openseadragon.min.js"), "//osd");

  const proc6 = Bun.spawn({
    cmd: ["bun", BRIDGE, doc, "--port", String(PORT6), "--no-open"],   // launch doc = A
    cwd: resolve(HERE, ".."), stdout: "ignore", stderr: "ignore", env: { ...process.env },
  });
  const b6 = `http://localhost:${PORT6}`;
  let up6 = false;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(b6 + "/")).ok) { up6 = true; break; } } catch {}
    await sleep(250);
  }
  if (up6) {
    // before the add: launch doc A has no pyramid -> 404
    const pre = await fetch(b6 + "/manifest.json");
    ok("before add: viewer routes 404 (launch doc has no pyramid)", pre.status === 404);

    // `add` doc B over the WS, wait for the prompt round-trip
    const ws6 = new WebSocket(`ws://localhost:${PORT6}/ws`);
    await new Promise<void>((done) => {
      const timer = setTimeout(done, 30000);
      let r6 = 0, sent = false;
      ws6.onmessage = (ev) => {
        const m = JSON.parse(String(ev.data));
        if (m.type === "ready") {
          r6++;
          if (r6 === 1 && !sent) { sent = true; ws6.send(JSON.stringify({ type: "input", data: `add "${docB}"` })); }
          else if (r6 >= 2) { clearTimeout(timer); try { ws6.close(); } catch {} done(); }
        }
      };
      ws6.onerror = () => { clearTimeout(timer); done(); };
    });

    const mf = await fetch(b6 + "/manifest.json");
    ok("after add: /manifest.json serves the ADDED doc's pyramid",
       mf.status === 200 && (await mf.json())[0].dzi === "tiles/page01.dzi");
    const off = await fetch(b6 + "/viewer_offline.html");
    ok("after add: the offline bundle serves through the bridge",
       off.status === 200 && (await off.text()).includes("OFFLINE-B"));
    const osd = await fetch(b6 + "/openseadragon.min.js");
    ok("after add: the vendored OSD serves through the bridge", osd.status === 200);
  } else {
    ok("before add: viewer routes 404 (launch doc has no pyramid)", false, "bridge6 did not come up");
  }
  try { proc6.kill(); } catch {}
  try { rmSync(tmp, { recursive: true, force: true }); } catch {}
}

// --- no-pyramid /viewer.html: progress page + auto-build, never a dead JSON ----
// The Axe-manual case: opening the viewer before/while the pyramid exists must
// serve a live progress page (200 text/html polling /pyramid-status), and flip
// to the real viewer once manifest.json lands.
const PORT7 = 8805;
{
  const { mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { basename, dirname } = await import("node:path");
  const os = await import("node:os");
  const tmp7 = await import("node:fs/promises").then(f => f.mkdtemp(join(os.tmpdir(), "waitpg-")));
  const docC = join(tmp7, "c.pdf");
  writeFileSync(docC, "%PDF-1.4");                  // a stub: the auto-build fails fast, harmless
  const proc7 = Bun.spawn({
    cmd: ["bun", BRIDGE, docC, "--port", String(PORT7), "--no-open"],
    cwd: resolve(HERE, ".."), stdout: "ignore", stderr: "ignore", env: { ...process.env },
  });
  const b7 = `http://localhost:${PORT7}`;
  let up7 = false;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(b7 + "/")).ok) { up7 = true; break; } } catch {}
    await sleep(250);
  }
  if (up7) {
    const wait = await fetch(b7 + "/viewer.html");
    const waitBody = await wait.text();
    ok("no pyramid: /viewer.html serves the PROGRESS page (200 html, not JSON)",
       wait.status === 200 && (wait.headers.get("content-type") || "").includes("text/html")
       && waitBody.includes("/pyramid-status"));
    const st = await fetch(b7 + "/pyramid-status");
    const stJson = await st.json();
    ok("/pyramid-status reports not-ready", st.status === 200 && stJson.ready === false);

    // the manifest lands (simulating the build finishing) -> real viewer serves
    const vd7 = join(tmp7, "c.pdf.drill", "viewer");
    mkdirSync(join(vd7, "tiles"), { recursive: true });
    writeFileSync(join(vd7, "manifest.json"),
      JSON.stringify([{ page: 1, dzi: "tiles/page01.dzi", width: 10, height: 10, levels: 1 }]));
    const st2 = await fetch(b7 + "/pyramid-status");
    ok("/pyramid-status flips to ready", (await st2.json()).ready === true);
    const real = await fetch(b7 + "/viewer.html");
    const realBody = await real.text();
    ok("after the build: /viewer.html serves the REAL viewer",
       real.status === 200 && realBody.includes("manifest.json")
       && !realBody.includes("/pyramid-status"));
  } else {
    ok("no pyramid: /viewer.html serves the PROGRESS page (200 html, not JSON)",
       false, "bridge7 did not come up");
  }
  try { proc7.kill(); } catch {}
  try { rmSync(tmp7, { recursive: true, force: true }); } catch {}
}

console.log(fails ? `\n${fails} FAILURE(S)` : "\nAll bridge checks passed.");


process.exit(fails ? 1 : 0);
