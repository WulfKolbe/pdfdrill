#!/usr/bin/env python3
r"""482 — every control sequence the corpus uses that our preamble does not define.

Four package gaps were found one document at a time: \longdiv (441/442),
mathrsfs and stmaryrd (out/056, 60 rows), mathtools (479, 83 occurrences),
\overparen (481). The preamble is loaded by every build in the corpus, so it
should change once against a census rather than five times against anecdotes.

THE INSTRUMENT IS AN EXISTENCE TEST, NOT A TYPESET PROBE.

    \expandafter\ifx\csname NAME\endcsname\relax ... \fi

Typesetting `$\cmd$` to see whether it errors confuses three different things:
undefined, defined-but-missing-its-argument, and defined-but-illegal-here. The
csname test asks only the question being asked, needs no arguments, and runs
every name in ONE xelatex pass.

Caveat recorded rather than hidden: `\csname NAME\endcsname` makes an
undefined NAME equal to \relax as a side effect, so each name is tested once
and the order of the tests does not matter.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import report_tex as rt          # noqa: E402

CMD = re.compile(r"\\([a-zA-Z]+)")
#: TeX primitives and environment machinery that are never "missing"
SKIP = {"begin", "end", "left", "right", "text", "mathrm", "frac", "sqrt"}


def harvest(root: Path) -> tuple:
    """{command: occurrences}, {command: documents}, documents scanned."""
    occ = collections.Counter()
    docs = collections.Counter()
    n = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        tp = list(d.glob("*.tiddlers.json"))
        if not tp:
            continue
        n += 1
        try:
            t = json.loads(tp[0].read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        t = t.get("tiddlers", t) if isinstance(t, dict) else t
        here = set()
        for x in t:
            if not re.search(r"_(EQ|FOX?|TAB)\d", x.get("title", "")):
                continue
            for m in CMD.finditer(x.get("latex") or ""):
                occ[m.group(1)] += 1
                here.add(m.group(1))
        for c in here:
            docs[c] += 1
        print("\r%d scanned, %d distinct commands" % (n, len(occ)),
              end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return occ, docs, n


def undefined(names, extra_packages=()) -> set:
    """Which of `names` our report preamble does not define. One xelatex run."""
    pre = rt.PREAMBLE.replace("%(geom)s", "a3paper,landscape") \
                     .replace("%(bbdigits)s", rt.MATHBB_DIGITS)
    for p in extra_packages:
        pre += "\\usepackage{%s}\n" % p
    body = ["\\begin{document}"]
    for nm in sorted(names):
        body.append("\\expandafter\\ifx\\csname %s\\endcsname\\relax"
                    "\\immediate\\write16{PDFDRILLMISSING:%s}\\fi" % (nm, nm))
    body.append("\\mbox{}\\end{document}")
    W = Path(tempfile.mkdtemp())
    (W / "t.tex").write_text(pre + "\n".join(body) + "\n", encoding="utf-8")
    r = subprocess.run(["xelatex", "-interaction=nonstopmode", "t.tex"],
                       cwd=W, capture_output=True, text=True, timeout=900)
    return set(re.findall(r"PDFDRILLMISSING:([a-zA-Z]+)", r.stdout))


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    occ, docs, n = harvest(root)
    names = [c for c in occ if c not in SKIP]
    miss = undefined(names)
    # what a package would buy: re-test with the candidates loaded
    fixed = {}
    for pkg in ("mathtools", "stix2", "amsfonts", "mathabx", "esvect",
                "wasysym", "textcomp", "mathdots", "extarrows", "yhmath",
                "cancel", "centernot", "bm", "esint", "upgreek", "tipa"):
        try:
            still = undefined(sorted(miss), extra_packages=(pkg,))
        except Exception:
            continue
        gained = sorted(miss - still)
        if gained:
            fixed[pkg] = gained
    json.dump({"documents_scanned": n,
               "distinct_commands": len(occ),
               "missing": {c: {"occurrences": occ[c], "documents": docs[c]}
                           for c in sorted(miss)},
               "packages_that_would_define_them": fixed},
              sys.stdout, indent=1, ensure_ascii=False)
