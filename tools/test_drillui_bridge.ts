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

console.log(fails ? `\n${fails} FAILURE(S)` : "\nAll bridge checks passed.");
process.exit(fails ? 1 : 0);
