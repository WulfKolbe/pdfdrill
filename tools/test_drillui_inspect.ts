#!/usr/bin/env bun
/**
 * 544 — drillui's scanner reads INSPECT.txt LINE BY LINE.
 *
 *   bun tools/test_drillui_inspect.ts
 *
 * 543 writes <library>/out/NNN/INSPECT.txt as one absolute path per line and
 * prints the same list. The scanner's token regex cannot span a space, and
 * about half this library's folders are named "Geometric, Algebraic and
 * Topological Methods for Quantum Field Theory (…) (Z-Library)". On 542's six
 * paths the old rule captured three, every one of them TRUNCATED to
 * `library/…` — so nothing it produced would open, and the two spaced paths
 * were not seen at all.
 *
 * A line is unambiguous: there is nothing to split on. This test holds the
 * line rule to that, and holds `.log` in the extension list because 543 puts
 * the compile log of a failed build in the list and a person opens it.
 */
const EXT = "(html|svg|pdf|md|json|txt|tex|log)";
const lineRe = new RegExp("^(\\/(?:[^\\n]*\\/)?[^\\n\\/]+\\." + EXT + ")$", "i");
const tokenRe = new RegExp(
  "(?<![\\w/])((?:[\\w.+~@%-]+\\/)+[\\w.+~@%-]+\\." + EXT + ")\\b(?!\\.[a-z])", "gi");

const SPACED = "/home/wkolbe/pdfdrill-library/Geometric, Algebraic and " +
  "Topological Methods for Quantum Field Theory (Alexander Cardona (ed.) etc.)" +
  " (Z-Library)/B.pdf";
const LIST = [
  "/home/wkolbe/pdfdrill-library/BradleyGastaldiTerilla2023/report.pdf",
  "/home/wkolbe/pdfdrill-library/BradleyGastaldiTerilla2023/B.pdf",
  "/home/wkolbe/pdfdrill-library/BradleyGastaldiTerilla2023/B.tex",
  "/home/wkolbe/pdfdrill-library/BradleyGastaldiTerilla2023/B.log",
  SPACED,
];

let failed = 0;
const check = (name: string, ok: boolean, detail = "") => {
  console.log(`${ok ? "  ok  " : "FAIL  "}${name}${detail ? "  — " + detail : ""}`);
  if (!ok) failed++;
};

// 1. every line of a real list matches, WHOLE, spaces included
for (const p of LIST) {
  const m = lineRe.exec(p);
  check(`line matches whole: …${p.slice(-28)}`, !!m && m[1] === p,
        m ? "" : "no match");
}

// 2. the printed block is indented — trimming is part of the rule
for (const p of LIST) {
  const m = lineRe.exec(("      " + p).trim());
  check(`indented line still matches: …${p.slice(-20)}`, !!m && m[1] === p);
}

// 3. the OLD rule is why this exists: it truncates and it misses spaces
const tokens: string[] = [];
let m: RegExpExecArray | null;
const blob = LIST.join("\n");
while ((m = tokenRe.exec(blob)) !== null) tokens.push(m[1]);
check("old token rule truncates the paths it does find",
      tokens.length > 0 && tokens.every((t) => !t.startsWith("/")),
      tokens[0] ?? "none");
check("old token rule cannot see a spaced path",
      !tokens.includes(SPACED));

// 4. a .log is in the list, because 543 puts a failed compile log there
check("`.log` is a recognised extension", !!lineRe.exec(LIST[3]));

// 5. a prose line that merely CONTAINS a path is not a whole-line path
check("prose is not swallowed",
      !lineRe.exec("wrote /home/x/report.pdf in 3s"));

console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
process.exit(failed ? 1 : 0);
