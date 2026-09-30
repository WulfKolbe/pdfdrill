#!/usr/bin/env python3
r"""sweep — which gold equations this reader does not reproduce, and why.

    python3 sweep.py                 every document
    python3 sweep.py --doc 024       one document, equation by equation
    python3 sweep.py --worst 15      the documents missing most

A gold equation counts as reproduced when its DIALECT-NORMALISED form appears
among the reader's `$$` blocks -- `\mid` for `|`, `{1\over2}` for `\frac12`,
`\varepsilon` for `\epsilon` and the rest of `canon.py`'s table. A reading
that is right and spelled differently is right.

The refusal counts come from the crop links in the markdown, which carry the
reason the span was withheld. They do not map one-to-one onto missed
equations -- one crop can cost a whole display, and an equation can be
missed while every span projected -- so both are reported, separately.

WHERE THE DATA IS
    $PDF2MMD_LIBRARY   default ~/pdfdrill-library
    $PDFDRILL_SRC      default ~/MX/PDFDRILL/src   (for report_tex)

The corpus is NOT in this repository and must not be put in it.
"""
import argparse
import importlib.util
import os
import re
import sys
from collections import Counter
from pathlib import Path

_here = Path(__file__).resolve().parent
LIB = Path(os.environ.get("PDF2MMD_LIBRARY", Path.home() / "pdfdrill-library"))

_s = importlib.util.spec_from_file_location("eq", _here / "eqtable_716.py")
eq = importlib.util.module_from_spec(_s)
_s.loader.exec_module(eq)

_c = importlib.util.spec_from_file_location("canon", _here / "canon.py")


def _canon():
    """`canon.canon` without running that file's report."""
    src = (_here / "canon.py").read_text(encoding="utf-8").split("cls=Counter()")[0]
    ns = {"__file__": str(_here / "canon.py"), "__name__": "canon"}
    exec(compile(src, str(_here / "canon.py"), "exec"), ns)
    return ns["canon"]


REASON = re.compile(r"!\[\S+ ([a-z-]+)(?::[^\]]*)?\]")
REASON_FULL = re.compile(r"!\[\S+ ([a-z-]+(?::[^\]]*)?)\]")


def documents():
    for d in sorted(x for x in LIB.glob("wzlxjtu-*") if x.is_dir()):
        gt = next(iter(d.glob("golden/*_gt.tex")), None)
        if gt is None:
            continue
        gold = eq.gold_equations(gt)
        if not gold:
            continue
        yield d, gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="one document, e.g. 024 or wzlxjtu-024")
    ap.add_argument("--worst", type=int, default=12)
    A = ap.parse_args()
    canon = _canon()

    if A.doc:
        slug = A.doc if A.doc.startswith("wzlxjtu-") else "wzlxjtu-" + A.doc
        d = LIB / slug
        gold = eq.gold_equations(next(iter(d.glob("golden/*_gt.tex"))))
        md = d / "pdf2mmd" / "page.md"
        ours = eq.md_blocks(md)
        cg = [canon(b) for b in ours]
        print("%s — gold %d, pdf2mmd %d blocks\n" % (slug, len(gold), len(ours)))
        for i, (env, g) in enumerate(gold, 1):
            hit = canon(g) in cg
            print("  %2d %-3s %s" % (i, "ok" if hit else "MISS",
                                     re.sub(r"\s+", " ", g)[:96]))
        r = Counter(REASON_FULL.findall(md.read_text(errors="replace")))
        if r:
            print("\n  refusals in this document:")
            for k, v in r.most_common():
                print("     %3d  %s" % (v, k))
        return

    tot = mp = mm = 0
    reasons, rows, with_miss = Counter(), [], 0
    for d, gold in documents():
        md = d / "pdf2mmd" / "page.md"
        cg = [canon(b) for b in eq.md_blocks(md)]
        cm = [canon(b) for b in eq.md_blocks(d / (d.name + ".md"))]
        a = sum(1 for _, g in gold if canon(g) not in cg)
        b = sum(1 for _, g in gold if canon(g) not in cm)
        tot += len(gold); mp += a; mm += b
        with_miss += 1 if a else 0
        reasons.update(REASON.findall(md.read_text(errors="replace")))
        rows.append((a, a - b, len(gold), d.name))

    n = sum(1 for _ in documents())
    print("=== gold equations this reader does not reproduce ===")
    print("  gold display equations   %4d" % tot)
    print("  missed by pdf2mmd        %4d  (%.1f%%)  in %d of %d documents"
          % (mp, 100.0 * mp / tot, with_miss, n))
    print("  missed by MathPix        %4d  (%.1f%%)" % (mm, 100.0 * mm / tot))
    print("\n=== refusals, all documents ===")
    for k, v in reasons.most_common():
        print("   %5d  %s" % (v, k))
    print("   %5d  TOTAL" % sum(reasons.values()))
    rows.sort(reverse=True)
    print("\n=== missing most (gap = ours minus MathPix's) ===")
    print("   %-14s %5s %5s %5s" % ("doc", "miss", "gold", "gap"))
    for a, gap, ng, name in rows[:A.worst]:
        print("   %-14s %5d %5d %+5d" % (name, a, ng, gap))


if __name__ == "__main__":
    main()
