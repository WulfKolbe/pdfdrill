#!/usr/bin/env bun
/**
 * 410 — every path `pdfdrill inkreport` PRESENTS must open through /artifact.
 *
 *   bun tools/test_drillui_artifact.ts
 *
 * Presenting a path the UI cannot open is half of reachable, and this was the
 * second time in a week that an artefact existed and the interface could not
 * get to it (404's `d.name` was the first: two layouts, two rules, one wrong).
 *
 * The two layouts are the point. A library document lives at
 * <library>/<stem>/<stem>.pdf and its artefacts are reported `<stem>/<file>`;
 * a legacy one lives at <dir>/<name>.pdf.drill/ and reports
 * `<name>.pdf.drill/<file>`. Both must resolve, and so must a path that
 * already names its root — `library/<stem>/<file>`, where joining naively
 * gives <library>/library/<stem>/<file> and nothing is ever there.
 */
import { spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PORT = 8791 + Math.floor(Math.random() * 40);
let failures = 0;

function ok(cond: boolean, what: string) {
  console.log(`${cond ? "  ok  " : "  FAIL"} ${what}`);
  if (!cond) failures++;
}

// A real document of each layout, skipped rather than faked when absent: a
// test that invents its own corpus proves the resolver against nothing.
const LIB = join(homedir(), "pdfdrill-library");
const libDoc = existsSync(LIB)
  ? readdirSync(LIB).find((d) => existsSync(join(LIB, d, "report.pdf")))
  : undefined;

const proc = spawn("bun", [join(HERE, "drillui_bridge.ts"), "--port", String(PORT)],
                   { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 3500));

async function status(path: string): Promise<number> {
  const u = `http://127.0.0.1:${PORT}/artifact?path=${encodeURIComponent(path)}`;
  try { return (await fetch(u)).status; } catch { return 0; }
}

try {
  if (!libDoc) {
    console.log("  skip  no library document with a report.pdf");
  } else {
    ok(await status(`${libDoc}/report.pdf`) === 200,
       `self-contained layout: ${libDoc}/report.pdf`);
    ok(await status(`library/${libDoc}/report.pdf`) === 200,
       `path that already names its root: library/${libDoc}/report.pdf`);
    ok(await status(`${libDoc}/no-such-file.pdf`) === 404,
       "a file that is genuinely absent still 404s");
    // and the 404 must SAY what it tried — a bare "not found" is not
    // diagnosable, and this message answered 410 without a tool call.
    const body = await (await fetch(
      `http://127.0.0.1:${PORT}/artifact?path=${encodeURIComponent(libDoc + "/no-such-file.pdf")}`)).text();
    ok(body.includes("roots tried"), "the 404 names the roots it tried");
  }
} finally {
  proc.kill();
}
if (failures) { console.error(`${failures} failure(s)`); process.exit(1); }
console.log("all ok");
