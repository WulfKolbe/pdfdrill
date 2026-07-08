#!/usr/bin/env bun
/**
 * Unit test for drillui's PATH-AWARE URL derivation (drillui_term.html).
 *
 *   bun tools/test_drillui_urls.ts
 *
 * drillui is reached directly on localhost (page path "/") OR through CoCalc's
 * reverse proxy (page path "/<project>/server/8787/"). The WebSocket URL and the
 * HTTP artifact base must resolve through the SAME path, so both are derived from
 * the page's directory — not the host alone (which dropped the proxy prefix and
 * caused "Bridge not reachable" + artifact 404s on CoCalc).
 *
 * This asserts the two transforms as behaviour specs AND that drillui_term.html
 * still contains them (so a revert to host-only fails here).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
let fails = 0;
const ok = (name: string, cond: boolean, extra = "") => {
  console.log(`  [${cond ? "ok" : "FAIL"}] ${name}${extra ? "  — " + extra : ""}`);
  if (!cond) fails++;
};

// The exact transforms as they appear in drillui_term.html (kept in sync by the
// source-guard assertions below).
const wsUrl = (protocol: string, host: string, pathname: string): string => {
  if (protocol === "file:") return "ws://localhost:8787/ws";
  const proto = protocol === "https:" ? "wss" : "ws";
  const base = pathname.replace(/[^/]*$/, "");
  return `${proto}://${host}${base}ws`;
};
const httpBase = (url: string): string => {
  const u = new URL(url);
  u.protocol = u.protocol === "wss:" ? "https:" : "http:";
  u.pathname = u.pathname.replace(/\/ws$/, ""); u.search = ""; u.hash = "";
  return u.toString().replace(/\/$/, "");
};

// --- WS URL: localhost, localhost-with-filename, CoCalc proxy, file ------------
ok("ws localhost root",
   wsUrl("http:", "localhost:8787", "/") === "ws://localhost:8787/ws");
ok("ws localhost https root",
   wsUrl("https:", "h:8787", "/") === "wss://h:8787/ws");
ok("ws localhost with page filename",
   wsUrl("http:", "localhost:8787", "/drillui_term.html") === "ws://localhost:8787/ws");
ok("ws CoCalc proxy prefix kept",
   wsUrl("https:", "host.cocalc.ai", "/PROJ/server/8787/")
     === "wss://host.cocalc.ai/PROJ/server/8787/ws");
ok("ws CoCalc proxy with index.html",
   wsUrl("https:", "host.cocalc.ai", "/PROJ/server/8787/index.html")
     === "wss://host.cocalc.ai/PROJ/server/8787/ws");
ok("ws file:// stays localhost",
   wsUrl("file:", "", "/whatever") === "ws://localhost:8787/ws");

// --- httpBase: strip only the trailing /ws, keep the proxy prefix -------------
ok("httpBase localhost", httpBase("ws://localhost:8787/ws") === "http://localhost:8787");
ok("httpBase localhost wss", httpBase("wss://h:8787/ws") === "https://h:8787");
ok("httpBase CoCalc keeps prefix",
   httpBase("wss://host.cocalc.ai/PROJ/server/8787/ws")
     === "https://host.cocalc.ai/PROJ/server/8787");
ok("artifact URL resolves through the proxy",
   `${httpBase("wss://host.cocalc.ai/PROJ/server/8787/ws")}/artifact?path=x.md`
     === "https://host.cocalc.ai/PROJ/server/8787/artifact?path=x.md");

// --- source guard: the HTML still uses the path-aware forms --------------------
const html = readFileSync(join(HERE, "drillui_term.html"), "utf8");
ok("html: ws derives from location.pathname",
   html.includes("location.pathname.replace(/[^/]*$/") &&
   html.includes("${proto}://${location.host}${base}ws"));
ok("html: httpBase strips only /ws (keeps prefix)",
   html.includes("u.pathname.replace(/\\/ws$/") &&
   !html.includes('u.pathname = ""'));

console.log(fails ? `\n${fails} FAILED` : "\nAll passed.");
process.exit(fails ? 1 : 0);
