#!/usr/bin/env python3
r"""474 — structurally parallel terms in one expression that disagree on a symbol.

THE REFERENCE CASE, cardona-qft-methods_EQ0654 p261 (confidence 0.167):

    ...\left(\frac{\overleftarrow{\delta}}{\partial x^{\mu}}
            +\frac{\overleftarrow{口}}{\partial y^{\mu}}\right)...

Two terms joined by `+`, the same shape, and the page prints \partial in both
numerators. MathPix produced `\delta` in one and the CJK ideograph 口 in the
other: two different wrong answers to the same glyph, inside one expression.

THE DEFINITION, and why it is not "differs in one leaf".

The reference terms differ in TWO positions: `\delta` vs `口` AND `x` vs `y`.
The second is an index alternation and is exactly what parallel terms are
SUPPOSED to differ in — an expression summing over x and y is not a defect.
So the rule separates the two kinds of difference:

  index difference   both tokens are single ASCII letters  -> expected
  symbol difference  anything else                         -> the signal

A pair is reported when it has exactly ONE symbol difference. That is what
makes the parallelism evidence: the shape says the two terms are the same
construction, and one leaf says they are not.

No model, no rebuild, no measurement — this reads `latex` off the projections.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

#: \command | {…} braces | any single character (CJK included)
TOKEN = re.compile(r"\\[a-zA-Z]+|\\.|[{}]|\s+|.", re.S)
MIN_TOKENS = 5          # `a+b` is not a parallel construction
MAX_DIFFS = 4           # beyond this the two terms are not the same shape


def tokens(latex: str) -> list:
    return [t for t in TOKEN.findall(latex or "") if not t.isspace()]


#: differences that parallel terms are SUPPOSED to have. The first cut of 474
#: exempted only single ASCII letters and returned 50,837 pairs, of which
#: 7,242 were `1 vs 2` and 5,117 `1 vs 3` — `x_{1}+x_{2}` is not a defect, it
#: is a sum. A digit varies for exactly the same reason a subscript letter
#: does; so does the sign between two terms, and so does a table separator.
#: Excluding them is not tuning a threshold, it is saying what parallelism
#: means: the terms differ in their INDEX and agree on their SYMBOLS.
SIGNS = {"+", "-"}
SEPARATORS = {"&", "\\\\"}


def is_index(tok: str) -> bool:
    """A single ASCII alphanumeric — what parallel terms legitimately vary."""
    return len(tok) == 1 and tok.isascii() and tok.isalnum()


def expected_pair(x: str, y: str) -> bool:
    """A difference that carries no claim about which symbol was printed."""
    return ((is_index(x) and is_index(y))
            or (x in SIGNS and y in SIGNS)
            or (x in SEPARATORS and y in SEPARATORS))


def is_cjk(tok: str) -> bool:
    if len(tok) != 1:
        return False
    o = ord(tok)
    return (0x2E80 <= o <= 0x9FFF or 0x20000 <= o <= 0x2FFFF
            or 0x2E00 <= o <= 0x2EFF or 0xF900 <= o <= 0xFAFF)


def _balanced(toks: list) -> bool:
    d = 0
    for x in toks:
        if x == "{":
            d += 1
        elif x == "}":
            d -= 1
            if d < 0:
                return False
    return d == 0


def _compare(a: list, b: list):
    """(symbol diffs, index diffs) between two equal-length token runs."""
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    sym = [(x, y) for x, y in diffs if not expected_pair(x, y)]
    return sym, len(diffs) - len(sym)


MAX_K = 60          # the longest parallel term worth looking for


def _balanced(toks: list) -> bool:
    d = 0
    for x in toks:
        if x == "{":
            d += 1
        elif x == "}":
            d -= 1
            if d < 0:
                return False
    return d == 0


def disagreements(latex: str) -> list:
    r"""Every `+`/`-` whose two sides are the same shape but one symbol apart.

    Splitting the expression on `+` does not work: in the reference case the
    `+` sits inside `e^{\frac{1}{2}\left( … \right)\theta^{\mu\nu}P_{\nu}}`,
    so the left side carries a `\frac{1}{2}\left(` prefix and the right side a
    `\right)\theta…` suffix, and the two "terms" have different lengths. So
    the window GROWS OUT from the operator: for a `+` at position i, compare
    toks[i-k:i] against toks[i+1:i+1+k] for k = 1 … MAX_K, and keep the
    largest k whose two windows are brace-balanced and one symbol apart.

    THE COMPARISON CANNOT BE MADE INCREMENTAL. Growing k by one moves the
    left window's START, so every position re-aligns; an "expand outward
    comparing toks[i-k] with toks[i+k]" version compares the left term's END
    against the right term's BEGINNING and finds nothing. It is written the
    slow way on purpose, and bounded by MAX_K instead — terms this long are
    the ones worth reporting, and the bound is what makes a corpus scan
    minutes rather than hours.
    """
    hits, seen = [], set()
    toks = tokens(latex)
    n = len(toks)
    for i, t in enumerate(toks):
        if t not in ("+", "-"):
            continue
        best = None
        for k in range(MIN_TOKENS, min(i, n - i - 1, MAX_K) + 1):
            a, b = toks[i - k:i], toks[i + 1:i + 1 + k]
            diffs = [(x, y) for x, y in zip(a, b) if x != y]
            if len(diffs) > MAX_DIFFS:
                continue
            sym = [(x, y) for x, y in diffs if not expected_pair(x, y)]
            if len(sym) != 1:
                continue
            if not _balanced(a) or not _balanced(b):
                continue
            best = (a, b, sym[0], len(diffs) - 1)
        if not best:
            continue
        a, b, (x, y), nidx = best
        key = ("".join(a), "".join(b))
        if key in seen:
            continue
        seen.add(key)
        hits.append({
            "term_a": "".join(a)[:160], "term_b": "".join(b)[:160],
            "symbol_a": x, "symbol_b": y, "index_diffs": nidx,
            "cjk": bool(is_cjk(x) or is_cjk(y)),
            "names": [unicodedata.name(c, "?")
                      for c in (x + y) if not c.isascii()],
        })
    return hits


def scan(tiddlers_path: Path) -> list:
    try:
        t = json.loads(Path(tiddlers_path).read_text(encoding="utf-8",
                                                     errors="replace"))
    except (OSError, ValueError):
        return []
    t = t.get("tiddlers", t) if isinstance(t, dict) else t
    out = []
    for x in t:
        title = x.get("title", "")
        if not re.search(r"_(EQ|FOX?)\d", title):
            continue
        lx = x.get("latex") or ""
        if "+" not in lx and "-" not in lx:
            continue
        for h in disagreements(lx):
            h["id"] = title
            h["page"] = x.get("page")
            h["conf"] = x.get("confidence")
            h["uri"] = x.get("canonical_uri") or ""
            out.append(h)
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    allhits, ndocs, nscanned = [], 0, 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        tp = list(d.glob("*.tiddlers.json"))
        if not tp:
            continue
        nscanned += 1
        h = scan(tp[0])
        if h:
            ndocs += 1
            for x in h:
                x["doc"] = d.name
            allhits.extend(h)
        print("\r%d docs scanned, %d hits" % (nscanned, len(allhits)),
              end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents_scanned": nscanned, "documents_with_hits": ndocs,
               "hits": allhits}, sys.stdout, indent=1, ensure_ascii=False)
