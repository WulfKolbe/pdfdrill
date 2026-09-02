#!/usr/bin/env python3
r"""486 — the values whose display delimiter is still MID-STRING.

483 established the population: of 1,168 rows carrying a `\[` or `\]`, 821
already render and 347 do not, and of those 167 are refused because a
delimiter remains in the middle of the value after every strip the gate
applies.

The hypothesis to test is that these are TWO DISPLAYS GLUED INTO ONE VALUE —
a segmentation error, and the mirror of 465's kohlhase p215 case where one
formula was split into four objects. This counts how many actually are that,
and what the rest are instead.

The classification runs on the value AS THE GATE LEAVES IT, not on the raw
string, so "mid-string" means what the gate means by it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import report_tex as rt          # noqa: E402

TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")


def after_the_gate(latex: str) -> str:
    """The value at the point the delimiter check sees it."""
    lx = re.sub(r"\s+", " ", latex).strip()
    lx = rt.alphabet_safe(lx)
    while True:
        m = re.search(r"\\end\{(\w+\*?)\}\s*$", lx)
        if not m:
            break
        env = re.escape(m.group(1))
        if len(re.findall(r"\\begin\{%s\}" % env, lx)) >= \
           len(re.findall(r"\\end\{%s\}" % env, lx)):
            break
        lx = lx[:m.start()].rstrip()
    while True:
        m = re.match(r"\\begin\{(\w+\*?)\}\s*", lx)
        if not m:
            break
        env = re.escape(m.group(1))
        if len(re.findall(r"\\end\{%s\}" % env, lx)) >= \
           len(re.findall(r"\\begin\{%s\}" % env, lx)):
            break
        lx = lx[m.end():].lstrip()
    lx = rt._drop_leading_furniture(lx)
    lx = rt._drop_stray_closers(lx)
    lx = re.sub(r"^\\\[\s*", "", lx)
    lx = re.sub(r"\s*\\\]$", "", lx)
    return lx


def classify(raw: str) -> "tuple[str, int] | None":
    """(class, number of complete displays) or None when not mid-string."""
    lx = after_the_gate(raw)
    if not re.search(r"\\\[|\\\]", lx):
        return None
    # count on the RAW value: how many complete \[ … \] pairs it holds
    n_open = len(re.findall(r"\\\[", raw))
    n_close = len(re.findall(r"\\\]", raw))
    if n_open != n_close:
        return ("unbalanced delimiters", min(n_open, n_close))
    if n_open >= 2:
        # are they SEQUENTIAL (…\] …\[…) rather than nested?
        order = [m.group(0) for m in re.finditer(r"\\\[|\\\]", raw)]
        alternating = all(order[i] == ("\\[" if i % 2 == 0 else "\\]")
                          for i in range(len(order)))
        return (("two or more complete displays" if alternating
                 else "nested or interleaved delimiters"), n_open)
    return ("one display with content outside it", n_open)


def scan(tp: Path):
    try:
        t = json.loads(tp.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    t = t.get("tiddlers", t) if isinstance(t, dict) else t
    out = []
    for x in t:
        title = x.get("title", "")
        lx = x.get("latex") or ""
        if not lx or not TYPED.search(title):
            continue
        if not re.search(r"\\\[|\\\]", lx):
            continue
        if rt.renderable(lx):
            continue
        c = classify(lx)
        if c:
            out.append({"id": title, "page": x.get("page"),
                        "conf": x.get("confidence"),
                        "uri": x.get("canonical_uri") or "",
                        "klass": c[0], "displays": c[1], "latex": lx})
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    docs, n = {}, 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        tp = list(d.glob("*.tiddlers.json"))
        if not tp:
            continue
        n += 1
        h = scan(tp[0])
        if h:
            docs[d.name] = h
        print("\r%d scanned, %d documents" % (n, len(docs)), end="",
              file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents_scanned": n, "documents": docs}, sys.stdout,
              indent=1, ensure_ascii=False)
