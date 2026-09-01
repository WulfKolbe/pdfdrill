#!/usr/bin/env python3
r"""481 — a corpus census of the five defect classes, and whose each one is.

Each was found one document at a time. This counts them over every projection
in the library, so a repair is sized before it is written.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")

#: 1 — a float environment inside a maths value. MathPix's segmentation: the
#:     display belongs to the object, the figure wrapper around it does not.
FIGURE = re.compile(r"\\begin\{(figure|table|wrapfigure|subfigure)\*?\}")

#: 2 — TeX source being DISCUSSED, typeset as mathematics. `\backslash` prints
#:     a literal backslash; real mathematics writes set difference `\setminus`,
#:     so a value carrying `\backslash` is almost always transcribed source.
CODE = re.compile(r"\\backslash|\\begin\{(lstlisting|verbatim|alltt)\}|\\verb")

#: 3 — an unescaped `_` inside \text/\mathrm/\mbox. In text mode `_` is
#:     illegal and the row dies with "Missing $ inserted".
TEXTY = re.compile(r"\\(?:text|mathrm|mbox|textrm|textit)\s*\{([^{}]*)\}")

#: 4 — \overparen, which neither amsmath nor amssymb defines (stix2 does).
OVERPAREN = re.compile(r"\\overparen\b")

#: 5 — a display delimiter inside a value the report re-wraps in $...$.
DISPLAY = re.compile(r"\\\[|\\\]")


def classify(lx: str) -> set:
    out = set()
    if FIGURE.search(lx):
        out.add("figure_wrapper")
    if CODE.search(lx):
        out.add("code_as_maths")
    if any("_" in m.group(1) for m in TEXTY.finditer(lx)):
        out.add("underscore_in_text")
    if OVERPAREN.search(lx):
        out.add("overparen")
    if DISPLAY.search(lx):
        out.add("display_delimiter")
    return out


CLASSES = ["figure_wrapper", "code_as_maths", "underscore_in_text",
           "overparen", "display_delimiter"]


def scan(tp: Path) -> dict:
    try:
        t = json.loads(tp.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    t = t.get("tiddlers", t) if isinstance(t, dict) else t
    hits: dict = {c: [] for c in CLASSES}
    for x in t:
        title = x.get("title", "")
        lx = x.get("latex") or ""
        if not lx or not TYPED.search(title):
            continue
        for c in classify(lx):
            hits[c].append({"id": title, "page": x.get("page"),
                            "conf": x.get("confidence"),
                            "latex": lx[:300]})
    return {c: v for c, v in hits.items() if v}


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    out, n = {}, 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        tp = list(d.glob("*.tiddlers.json"))
        if not tp:
            continue
        n += 1
        h = scan(tp[0])
        if h:
            out[d.name] = h
        print("\r%d scanned, %d with a hit" % (n, len(out)), end="",
              file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents_scanned": n, "documents": out}, sys.stdout,
              indent=1, ensure_ascii=False)
