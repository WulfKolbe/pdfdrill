r"""529/530 — what an inline formula inherits from the line it was printed in.

An `FO` row is the poorest row in the projection: no page, no confidence,
no region, no crop. 527 measured the cost — 91.6% of the corpus's maths
items are inline, so the richest signal in the document describes the
smallest part of it.

The model already knows the page (369 of 369 Formula objects carry one).
What it does not carry is the confidence and the region, and both belong to
the LINE the formula was printed in. A MathPix line has `confidence`,
`confidence_rate` and a `region`; an inline formula sits inside one. That
line's confidence is the only confidence the formula will ever have, and
that line's region is the only picture of it there is.

THE JOIN IS BY CONTAINMENT, and it is checked rather than assumed: the
formula's latex must appear inside the line's `text`. On 2010.14265 that
matches 368 of 369 formulas; the miss is `\square`, a QED symbol that MathPix
emits as its own line with no `$` around it.

A line is NOT a formula. The confidence is the line's, and a report showing
it must say so — 147's rule that two instruments in adjacent cells must each
be named.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_lines(lines_path: "Path | str") -> list:
    """[(page_number, line_dict)] in document order, 1-based pages."""
    j = json.loads(Path(lines_path).read_text(encoding="utf-8",
                                              errors="replace"))
    out = []
    for i, pg in enumerate(j.get("pages") or [], 1):
        for ln in pg.get("lines") or []:
            out.append((i, ln))
    return out


def _area(ln) -> float:
    r = ln.get("region") or {}
    try:
        return float(r.get("width") or 0) * float(r.get("height") or 0)
    except (TypeError, ValueError):
        return 0.0


def host_of(latex: str, lines: list) -> "tuple | None":
    r"""The line this formula was printed in, or None.

    FIRST CONTAINMENT IS NOT GOOD ENOUGH, and the failure is visible rather
    than theoretical: the formula `X` matched the arXiv margin stamp
    (`arXiv:2010.14265v2 [stat.ML] 4 Aug 2021`, set vertically) because that
    line contains an X and comes first. B then drew a 500pt-tall sidebar as
    the picture of a one-letter formula and reported the stamp's confidence
    as the formula's.

    So: prefer a DELIMITED match (`$x$`, `\(x\)`) over bare containment —
    that is the formula as the page actually set it — and among equally good
    candidates take the SMALLEST region, which is the tightest line that
    still contains it. A one-character formula inside a full paragraph is a
    true containment and a useless picture.
    """
    if not latex:
        return None
    delimited, plain = [], []
    for page, ln in lines:
        t = ln.get("text") or ""
        if latex not in t:
            continue
        if ("$%s$" % latex) in t or ("\\(%s\\)" % latex) in t:
            delimited.append((page, ln))
        else:
            plain.append((page, ln))
    for bucket in (delimited, plain):
        if bucket:
            return min(bucket, key=lambda pl: _area(pl[1]) or float("inf"))
    return None


def context_for(latex: str, lines: list) -> dict:
    """{page, confidence, confidence_rate, line_type, region} or {} if unmatched.

    `region` is in MathPix page-image pixels, the same frame
    `report_tex.render_crops` scales from — so a row built with this can be
    cropped from the PDF exactly as a table row is.
    """
    hit = host_of(latex, lines)
    if not hit:
        return {}
    page, ln = hit
    r = ln.get("region") or {}
    out = {"page": page, "line_type": ln.get("type"),
           "confidence": ln.get("confidence"),
           "confidence_rate": ln.get("confidence_rate")}
    for k in ("top_left_x", "top_left_y", "width", "height"):
        if r.get(k) is not None:
            out[k] = r[k]
    return out


def attach(formulas: list, lines_path) -> dict:
    """{latex: context}. One pass over the lines per distinct latex value."""
    lines = load_lines(lines_path)
    seen = {}
    for lx in formulas:
        if lx and lx not in seen:
            seen[lx] = context_for(lx, lines)
    return seen
