"""inventory — what glyph identities actually occur in born-digital PDFs.

Before writing any glyphname -> LaTeX table, measure what the table would
have to cover. A table written from knowledge of TeX conventions rather than
from the corpus would be guesswork with a plausible shape.

CONTRACT
  inventory(paths) -> (pairs, families, unnamed)
    pairs     Counter[(font_family, glyphname)] over every LTChar
    families  Counter[font_family]
    unnamed   Counter[(font_family, cid)] where no glyph name is stated
  Scanned documents must NOT be passed here: a glyph name from an OCR layer
  reports the OCR's guess, not the page. `--skip-invisible` drops Tr 3/7
  glyphs so that an accidentally-included scan contributes nothing.

Font-family classification is by NAME ONLY and is a hint for grouping the
report, never an identity claim.
"""
from __future__ import annotations

import collections
import re
import sys

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar

# Font-family classification lives in `texmap`: it is part of mapping an
# identity to an alphabet, not part of this analysis tool. Re-exported here so
# the tool reads the same way it always did.
from texmap import FAMILY_RULES, family_of  # noqa: F401

def inventory(paths, skip_invisible: bool = True):
    pairs: collections.Counter = collections.Counter()
    families: collections.Counter = collections.Counter()
    unnamed: collections.Counter = collections.Counter()

    for path in paths:
        def visit(o):
            if isinstance(o, LTChar):
                if skip_invisible and o.invisible:
                    return
                base = o.fontname.split("+")[-1]
                fam = family_of(o.fontname)
                families[fam] += 1
                if o.glyphname:
                    pairs[(fam, base, o.glyphname)] += 1
                else:
                    unnamed[(fam, base, o.cid)] += 1
            elif hasattr(o, "__iter__"):
                for c in o:
                    visit(c)

        for layout in extract_pages(path):
            for e in layout:
                visit(e)

    return pairs, families, unnamed


if __name__ == "__main__":
    paths = sys.argv[1:]
    pairs, families, unnamed = inventory(paths)
    total = sum(families.values())
    print(f"glyphs (visible only): {total}")
    print("\nby font family:")
    for k, v in families.most_common():
        print(f"  {v:9d}  {100.0 * v / max(total, 1):5.1f}%  {k}")

    mathfams = {"math-italic", "math-symbol", "math-extension", "ams-symbol",
                "fraktur", "script"}
    mathpairs = {k: v for k, v in pairs.items() if k[0] in mathfams}
    print(f"\ndistinct (family, glyphname) in MATHS fonts: "
          f"{len({(k[0], k[2]) for k in mathpairs})}")
    print(f"maths glyph instances: {sum(mathpairs.values())}")

    byfam: dict = collections.defaultdict(collections.Counter)
    for (fam, _base, name), v in mathpairs.items():
        byfam[fam][name] += v
    for fam in sorted(byfam):
        names = byfam[fam]
        print(f"\n--- {fam}: {len(names)} distinct names, {sum(names.values())} glyphs")
        print("   ", ", ".join(n for n, _ in names.most_common(30)))

    if unnamed:
        print(f"\nUNNAMED (no identity stated): {sum(unnamed.values())} glyphs, "
              f"{len(unnamed)} distinct")
        for (fam, base, cid), v in unnamed.most_common(10):
            print(f"   {v:7d}  {base:<24} cid:{cid}  [{fam}]")
