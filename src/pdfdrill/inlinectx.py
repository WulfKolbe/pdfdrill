r"""529/535 — what an inline formula inherits from the line it was printed in.

An `FO` row is the poorest row in the projection: no page, no confidence, no
region, no crop. 527 measured the cost — 91.6% of the corpus's maths items
are inline. The line the formula was printed in has all three, and its
confidence is the only confidence such a formula will ever have.

535 — THE JOIN IS BY EXACT VALUE ON THE FIRST OCCURRENCE, NOT BY SEARCH.

The first version matched by CONTAINMENT: the first line whose text contained
the formula. That cannot work for a one-character formula and it did not.
`P` matched a line reading "the past (Andersen, 2013...)", which contains a
`P` in "past" and no formula at all, while the document's real `$P$` is in
"a sample from the joint distribution P of the observed variables". A
tie-break on the smallest region only chose a different wrong line.

A positional walk — the kth inline span is the kth Formula — does not work
either, and the reason is a fact about the projection worth writing down:

    inline spans in 2010.14265's lines     1,008
    Formula objects in the model             369
    DISTINCT formula values                  369

**The model holds one Formula per DISTINCT VALUE, not per occurrence.** So
the two sequences are not parallel; paired positionally they agree on 1 of
369 and diverge at index 1.

What IS exact is the value itself. A span is the formula, character for
character, so the formula's context is that of its FIRST span in document
order — page order, then line order, then span order within the line. That
lookup is an equality test with no threshold and no tie-break, it lands
`P` on the joint-distribution line, and it resolves 368 of 369 values on
2010.14265. The one miss is `\square`, a QED symbol MathPix emits as its own
line with no delimiters around it — reported, never defaulted.

A line is NOT a formula. The confidence is the line's, and any report showing
it must say so (147).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: `$...$` or `\( ... \)`. A `\$` is an escaped dollar and never a delimiter.
INLINE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$|\\\((.+?)\\\)", re.S)


def load_spans(lines_path: "Path | str") -> list:
    """Every inline span in document order, each with its host line's data.

    Lines of type `math` are display maths and are skipped: they are the
    document's equations, which reach a report on their own terms.
    """
    j = json.loads(Path(lines_path).read_text(encoding="utf-8",
                                              errors="replace"))
    out = []
    for page, pg in enumerate(j.get("pages") or [], 1):
        for line_index, ln in enumerate(pg.get("lines") or []):
            if ln.get("type") == "math":
                continue
            text = ln.get("text") or ""
            for m in INLINE.finditer(text):
                body = (m.group(1) or m.group(2) or "").strip()
                if not body:
                    continue
                out.append({"latex": body, "page": page,
                            "line_index": line_index,
                            "line_type": ln.get("type"),
                            "confidence": ln.get("confidence"),
                            "confidence_rate": ln.get("confidence_rate"),
                            "region": ln.get("region") or {}})
    return out


def first_occurrences(spans: list) -> dict:
    """{latex: the first span carrying it on a line that can HOST a formula}.

    Document order decides, but not alone. A table cell, a section heading,
    a title, a TOC entry and a figure label are not prose, so a formula
    printed there is not an inline formula and its line is not a context an
    inline formula may inherit (docmodel/line_types.py).

    Order alone got this wrong wherever the same reading appears in both,
    and the model holds ONE Formula per distinct value (see this module's
    header), so the wrong pick is the only pick the row ever gets.
    Measured on kohlhase-omdoc: the reading `\\overline{\\mathcal{C}}` occurs
    four times on page 150 --- three inside the `Fig. 15.12` tabular, once in
    the sentence that introduces it. Document order chose the tabular, so
    the published FO row carried the table's confidence and the table's
    region, and its crop was a picture of the table.

    A reading that occurs ONLY on forbidden lines gets no entry at all,
    and that is the point: there is no line it may inherit from, so every
    caller reports the absence (`context_of(None)` is `{}`, an FO row shows
    "---") instead of one of them showing a table's confidence. A fallback
    to "the first span, forbidden or not" was written first and removed:
    it left 27 published rows across the 20 documents still hosted on a
    figure label or a TOC entry --- the same defect, now reachable only
    where the model and this span scan disagree about a line's text.
    """
    from docmodel.line_types import hosts_transclusion
    first = {}
    for s in spans:
        if hosts_transclusion(s.get("line_type")):
            first.setdefault(s["latex"], s)
    return first


def context_of(span: "dict | None") -> dict:
    """{page, line_type, confidence, confidence_rate, region fields} or {}."""
    if not span:
        return {}
    out = {"page": span["page"], "line_type": span.get("line_type"),
           "confidence": span.get("confidence"),
           "confidence_rate": span.get("confidence_rate")}
    r = span.get("region") or {}
    for k in ("top_left_x", "top_left_y", "width", "height"):
        if r.get(k) is not None:
            out[k] = r[k]
    return out


def attach(formulas: list, lines_path) -> dict:
    """{latex: context} for each formula value, by exact first occurrence."""
    first = first_occurrences(load_spans(lines_path))
    return {lx: context_of(first.get((lx or "").strip()))
            for lx in formulas if lx}
