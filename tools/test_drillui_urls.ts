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
  // THREE cases, as the page has them: a directory ("…/8787/"), a page FILE
  // ("…/8787/index.html" → strip it), and a directory served WITHOUT its
  // trailing slash ("…/8787" → append one). The last is the CoCalc default,
  // and the single `replace(/[^/]*$/, "")` this mirror used to carry deleted
  // the PORT segment there, yielding "/p/server/ws".
  let base;
  if (pathname.endsWith("/")) base = pathname;
  else if (/\.[a-z0-9]+$/i.test(pathname.split("/").pop() || ""))
    base = pathname.replace(/[^/]*$/, "");
  else base = pathname + "/";
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
ok("ws CoCalc proxy WITHOUT the trailing slash keeps the port",
   wsUrl("https:", "host.cocalc.ai", "/PROJ/server/8787")
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
   html.includes("const p = location.pathname;") &&
   html.includes('if (p.endsWith("/")) base = p;') &&
   html.includes("${proto}://${location.host}${base}ws"));
ok("html: httpBase strips only /ws (keeps prefix)",
   html.includes("u.pathname.replace(/\\/ws$/") &&
   !html.includes('u.pathname = ""'));

// --- scanArtifacts: capture a SPACED artifact path + dedup the truncated tail ---
// Mirrors drillui_term.html::scanArtifacts (kept in sync by the source guard below).
function scanArtifacts(text: string): string[] {
  const EXT = "(html|svg|pdf|md|json|txt|tex)";
  const set = new Map<string, boolean>();
  const add = (path: string) => {
    if (/^https?:/i.test(path)) return;
    if (set.has(path)) return;
    for (const have of set.keys())
      if (have.endsWith("/" + path) || have.endsWith(" " + path)) return;
    set.set(path, true);
  };
  let m: RegExpExecArray | null;
  const bracket = new RegExp("\\bOpen\\s+(.+?\\." + EXT + ")\\s+in\\b", "gi");
  while ((m = bracket.exec(text)) !== null) add(m[1]);
  const drill = new RegExp(
    "(?:->|→|to|wrote(?:\\s+to)?|stored(?:\\s+(?:at|in))?)\\s+" +
    "([^\\n]*?\\.drill\\/[^\\n]*?\\." + EXT + ")(?=[\\s.,;)]|$)", "gi");
  while ((m = drill.exec(text)) !== null) add(m[1]);
  const re = new RegExp("(?<![\\w/])((?:[\\w.+~@%-]+\\/)*[\\w.+~@%-]+\\." + EXT + ")\\b", "gi");
  while ((m = re.exec(text)) !== null) add(m[1]);
  return [...set.keys()];
}

const spaced = "Distill reading view: 1378 blocks. Open Verbalizable Representations " +
  "Form a Global Workspace in Language Models.pdf.drill/" +
  "Verbalizable_Representations_Form_a_Global_Workspace_in_Language_Models.distill.html in a browser.";
const got = scanArtifacts(spaced);
ok("spaced artifact path captured whole",
   got.includes("Verbalizable Representations Form a Global Workspace in Language Models.pdf.drill/" +
     "Verbalizable_Representations_Form_a_Global_Workspace_in_Language_Models.distill.html"));
ok("truncated tail NOT added as a second artifact",
   !got.some(p => p.startsWith("Models.pdf.drill/")));
ok("normal no-space path still captured",
   scanArtifacts("Open data/x.pdf.drill/report.html in a browser.")
     .includes("data/x.pdf.drill/report.html"));
// `→ <spaced path>.` (llmtext-style, no "Open … in") — captured whole via .drill/
const arrow = scanArtifacts(
  "LLM text dump: 262 units, delimiter %%%%. -> Burkhard Heim 2-compressed.pdf.drill/" +
  "Burkhard Heim 2-compressed.llm.txt.");
ok("arrow-reported spaced .drill/ path captured whole",
   arrow.includes("Burkhard Heim 2-compressed.pdf.drill/Burkhard Heim 2-compressed.llm.txt"));
ok("no truncated tail from the arrow path",
   !arrow.some(p => p.startsWith("2-compressed.pdf.drill/")));
// the ".md" in a .md.drill dir must NOT truncate a .json artifact
ok("`.md` in the drill dir does not truncate",
   scanArtifacts("wrote to my summary.md.drill/my summary.tables.json")
     .includes("my summary.md.drill/my summary.tables.json"));

const htmlSrc = readFileSync(join(HERE, "drillui_term.html"), "utf8");
ok("html: scanArtifacts uses the Open…in bracket capture",
   htmlSrc.includes('"\\\\bOpen\\\\s+(.+?\\\\." + EXT'));

// --- a lead-in EARLIER on the line must not swallow the words before the path ---
// "Wrote 216 TiddlyWiki tiddlers to Clutter.pdf.drill/…" anchored on "Wrote" and
// linked "216 TiddlyWiki tiddlers to Clutter.pdf.drill/…" (a bridge 404). The
// helper is taken FROM the page, not mirrored, so the two cannot drift.
const helperSrc = /_leadInCandidates\(path\)\{([\s\S]*?)\n  \},/.exec(htmlSrc);
ok("html: _leadInCandidates present", !!helperSrc);
const leadInCandidates = new Function("path", helperSrc ? helperSrc[1] : "return [path];") as
  (p: string) => string[];
const drillRe = () => new RegExp(
  "(?:->|→|\\bto|\\bwrote(?:\\s+to)?|\\bstored(?:\\s+(?:at|in))?)\\s+" +
  "([^\\n:→]*?\\.drill\\/[^\\n:→]*?\\.(html|svg|pdf|md|json|txt|tex|log))(?!\\.[a-z])(?=[\\s.,;)]|$)", "gi");
ok("html: rule 1b lead-ins are whole words",
   htmlSrc.includes('"(?:->|→|\\\\bto|\\\\bwrote(?:\\\\s+to)?|\\\\bstored'));
const pick = (line: string, exists: (p: string) => boolean) => {
  const m = drillRe().exec(line)!;
  const c = leadInCandidates(m[1]);
  return c.find(exists) ?? c[c.length - 1];
};
const clutter = "Wrote 216 TiddlyWiki tiddlers to Clutter.pdf.drill/Clutter.tiddlers.json. Import into TiddlyWiki;";
ok("Clutter: the path after the LAST lead-in is a candidate",
   leadInCandidates(drillRe().exec(clutter)![1]).includes("Clutter.pdf.drill/Clutter.tiddlers.json"));
ok("Clutter: resolves to the file that exists",
   pick(clutter, p => p === "Clutter.pdf.drill/Clutter.tiddlers.json")
     === "Clutter.pdf.drill/Clutter.tiddlers.json");
ok("Clutter: with no bridge answer, falls back to the shortest cut",
   pick(clutter, () => false) === "Clutter.pdf.drill/Clutter.tiddlers.json");
const book = "Wrote 12 tiddlers to Introduction to Algebra.pdf.drill/x.tiddlers.json.";
ok("a title containing ' to ' resolves whole when that file exists",
   pick(book, p => p === "Introduction to Algebra.pdf.drill/x.tiddlers.json")
     === "Introduction to Algebra.pdf.drill/x.tiddlers.json");
ok("no inner lead-in → a single candidate (no probing)",
   leadInCandidates("my summary.md.drill/my summary.tables.json").length === 1);
ok("'to' inside a word is not a lead-in",
   drillRe().exec("see photo x.pdf.drill/a.md") === null);

// --- bridge: recover an UNQUOTED doc path the shell split on spaces/umlauts ----
import { existsSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
function reassemble(doc: string, passthrough: string[]) {
  if (doc && !doc.startsWith("http") && !existsSync(doc) && passthrough.length) {
    const words = [doc, ...passthrough];
    for (let n = words.length; n >= 2; n--) {
      const j = words.slice(0, n).join(" ");
      if (existsSync(j)) return { doc: j, rest: passthrough.slice(n - 1) };
    }
  }
  return { doc, rest: passthrough };
}
const _d = mkdtempSync(join(tmpdir(), "du-"));
const _f = join(_d, "Burkhard Heim Einführung.pdf");   // spaces + umlaut
writeFileSync(_f, "%PDF");
const _split = _f.split(" ");
const _r = reassemble(_split[0], _split.slice(1));
ok("bridge recovers an unquoted spaced+umlaut doc", _r.doc === _f && _r.rest.length === 0);
ok("bridge no-op on a quoted (existing) doc", reassemble(_f, ["--port", "9000"]).doc === _f);
rmSync(_d, { recursive: true });
ok("bridge.ts contains the reassembly",
   readFileSync(join(HERE, "drillui_bridge.ts"), "utf8").includes("passthrough.splice(0, n - 1)"));

// --- 557 — A URL IN THE PROSE IS NOT A LOCAL ARTIFACT PATH -------------------
// `add https://www.inftyproject.org/articles/2001_Grec_Kanahori.pdf` is echoed
// into the terminal. Rule 2's lookbehind `(?<![\w/])` refuses a match that
// starts after a word character or a slash — but `.` is in the path class and
// NOT in the lookbehind, so the engine started at the dot inside the HOST and
// captured `inftyproject.org/articles/2001_Grec_Kanahori.pdf`: a scheme-less
// fragment `add`'s `/^https?:/` guard can no longer recognise. It was listed as
// an artifact and linked as `/artifact?path=inftyproject.org%2Farticles%2F…`,
// which is under no root, so the bridge 404s — while the real file sits at
// `<library>/2001_Grec_Kanahori/2001_Grec_Kanahori.pdf`. Without `www.` it is
// worse: the capture starts after the FIRST dot (`org/articles/x.pdf`).
// The mask is taken FROM the page, not mirrored, so the two cannot drift.
const maskSrc = /_maskUrls\(text\)\{([\s\S]*?)\n  \},/.exec(htmlSrc);
ok("html: _maskUrls present", !!maskSrc);
const maskUrls = new Function("text", maskSrc ? maskSrc[1] : "return text;") as
  (t: string) => string;
const scan2 = (text: string): string[] => {
  const EXT = "(html|svg|pdf|md|json|txt|tex|log)";
  const re = new RegExp(
    "(?<![\\w/])((?:[\\w.+~@%-]+\\/)+[\\w.+~@%-]+\\." + EXT + ")\\b(?!\\.[a-z])", "gi");
  const out: string[] = [];
  let m: RegExpExecArray | null;
  const masked = maskUrls(text);
  while ((m = re.exec(masked)) !== null) if (!/^https?:/i.test(m[1])) out.push(m[1]);
  return out;
};
ok("a www URL yields no artifact",
   scan2("? add https://www.inftyproject.org/articles/2001_Grec_Kanahori.pdf").length === 0,
   JSON.stringify(scan2("? add https://www.inftyproject.org/articles/2001_Grec_Kanahori.pdf")));
ok("a bare-host URL yields no artifact",
   scan2("  adding https://inftyproject.org/articles/x.pdf … (reuses an existing drill)").length === 0,
   JSON.stringify(scan2("  adding https://inftyproject.org/articles/x.pdf …")));
ok("masking preserves offsets (same length)",
   maskUrls("a https://x.org/y.pdf b").length === "a https://x.org/y.pdf b".length);
ok("a real path on the same line as a URL survives",
   scan2("got https://www.inftyproject.org/articles/2001_Grec_Kanahori.pdf → " +
         "2001_Grec_Kanahori/2001_Grec_Kanahori.md")
     .join(",") === "2001_Grec_Kanahori/2001_Grec_Kanahori.md");
ok("a local path is untouched by the mask",
   scan2("→ Markdown file: TPAMI_Math/TPAMI_Math.md  (open it directly)")
     .join(",") === "TPAMI_Math/TPAMI_Math.md");
ok("html: scanArtifacts applies the mask",
   /scanArtifacts\(text\)\{[\s\S]{0,400}?_maskUrls\(/.test(htmlSrc));

// --- 557b — the `status` / `artifacts` FILE LIST, spaces and all -------------
// pdfdrill prints one `  <path>  (<n> KB)` line per file under a header that
// promises "click in the Outputs panel". 784 of this library's 3164 doc folders
// have a space in the name, and rule 2's token class cannot span a space — so a
// quarter of the library listed its PDF as unclickable text. The size suffix
// anchored at end-of-line delimits the path exactly, which is what no prose
// rule can do.
const KB_RE = new RegExp(
  "^[ \\t]+(.+?\\.(html|svg|pdf|md|json|txt|tex|log))[ \\t]+\\(\\d+ KB\\)[ \\t]*$", "gim");
const kbPaths = (text: string): string[] => {
  const out: string[] = []; let m: RegExpExecArray | null;
  KB_RE.lastIndex = 0;
  while ((m = KB_RE.exec(text)) !== null) out.push(m[1]);
  return out;
};
const listing = "Files (open in a tab / click in the Outputs panel):\n" +
  "  0111016 (1)/0111016 (1).pdf  (288 KB)\n" +
  "  2001_Grec_Kanahori/2001_Grec_Kanahori.md  (26 KB)\n" +
  "  Kana/svg/EQ1.svg  (0 KB)\n" +
  "  (the raw model JSON is hidden — `pdfdrill artifacts x.pdf --all` to include it)\n";
ok("spaced doc folder captured whole",
   kbPaths(listing).includes("0111016 (1)/0111016 (1).pdf"),
   JSON.stringify(kbPaths(listing)));
ok("all three listed files captured", kbPaths(listing).length === 3,
   JSON.stringify(kbPaths(listing)));
ok("the hidden-JSON note is not a path",
   !kbPaths(listing).some(p => p.includes("raw model JSON")));
ok("html: the KB-line rule is in the page",
   /\\\(\\\\d\+ KB\\\)/.test(htmlSrc) || htmlSrc.includes("KB\\\\)"));

// --- 557c — the listing rule runs BEFORE the token rule ---------------------
// Rule 2 captures the tail of a spaced path after the last space
// ("… Eu-Sc-Fe Garnets/probe-page-text.json" → "Garnets/probe-page-text.json",
// a 404). `add`'s truncated-tail guard drops such a fragment only when the FULL
// path was captured first — it asks "am I a tail of something already listed?",
// never the reverse. So the listing rule has to run before the token rule, the
// same ordering rule 0 states for absolute-path lines. Verified on the REAL
// page object, not a mirror: scanArtifacts and its helpers are lifted out of
// drillui_term.html and run over the real `status` output.
const lift = (name: string, args: string) => {
  const re = new RegExp("\\n  (?:async )?" + name + "\\(" + args + "\\)\\{([\\s\\S]*?)\\n  \\},");
  const m = re.exec(htmlSrc);
  if (!m) throw new Error("not found in drillui_term.html: " + name);
  return m[1];
};
const page: any = {
  artifacts: new Map<string, any>(),
  artifactUrl: (p: string) => "http://x/artifact?path=" + encodeURIComponent(p),
  renderArtifacts: () => {},
};
for (const [n, a] of [["_maskUrls", "text"], ["_isInternalArtifact", "path"],
                      ["_leadInCandidates", "path"]] as [string, string][])
  page[n] = new Function(a, lift(n, a)).bind(page);
page._addFirstExisting = new Function("cands", "ext",
  "return (async () => {" + lift("_addFirstExisting", "cands, ext") + "})()").bind(page);
page.readInspectList = new Function("path",
  "return (async () => {" + lift("readInspectList", "path") + "})()").bind(page);
page.scanArtifacts = new Function("text", lift("scanArtifacts", "text")).bind(page);

const DOC = "020-Cation Distribution in Eu-Sc-Fe Garnets";
page.scanArtifacts(
  "Files (open in a tab / click in the Outputs panel):\n" +
  `  ${DOC}/${DOC}.md  (31 KB)\n` +
  `  ${DOC}/${DOC}.pdf  (632 KB)\n` +
  `  ${DOC}/probe-page-text.json  (24 KB)\n`);
const listed = [...page.artifacts.keys()] as string[];
ok("the spaced doc's PDF is listed whole", listed.includes(`${DOC}/${DOC}.pdf`),
   JSON.stringify(listed));
ok("no truncated 'Garnets/…' fragment is listed",
   !listed.some(p => p.startsWith("Garnets/")), JSON.stringify(listed));
ok("exactly the three listed files", listed.length === 3, JSON.stringify(listed));
ok("html: the listing rule precedes the token rule",
   htmlSrc.indexOf("// 0c. 557 —") < htmlSrc.indexOf("// 2. path-like tokens"));

console.log(fails ? `\n${fails} FAILED` : "\nAll passed.");
process.exit(fails ? 1 : 0);
