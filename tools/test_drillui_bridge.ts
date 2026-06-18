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
console.log(fails ? `\n${fails} FAILURE(S)` : "\nAll bridge checks passed.");
process.exit(fails ? 1 : 0);
