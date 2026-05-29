"""
Equation-number fusion.

Display-equation numbers like "(1)" sit at the left/right page margin on the
same line as the equation — a layout signal MathPix often drops but pdftotext
captures cleanly. After geometry fusion the `pdf_lines` stream holds those
margin tokens with normalized coordinates, so we can attach the number to the
equation it belongs to (matching by page + vertical position).

Each equation ends up with:
  - `refnum`         the bare number, e.g. "1"
  - `equation_number` the displayed form, e.g. "(1)"
so a TiddlyWiki template can transclude both the equation (`||FO`) and its
reference (`||FREF`). Where MathPix already supplied the number we just
normalize the parenthesized form; where it didn't, we recover it from geometry
and record an `Alignment(kind="equation_number")`.
"""
from __future__ import annotations

import re

# A margin token that is just an equation number: 1, 1.2, (3), (3a), ...
_EQNUM_RE = re.compile(r"^\(?(\d+(?:\.\d+)?[a-z]?)\)?$")


def _as_display(raw_text: str, number: str) -> str:
    raw = raw_text.strip()
    return raw if raw.startswith("(") and raw.endswith(")") else f"({number})"


def fuse_equation_numbers(doc, tol: float = 0.03) -> dict:
    """Attach equation_number to each Equation. Returns counts."""
    from docmodel.core import Range, Alignment

    pl = doc.streams.get("pdf_lines")
    numbers_by_page: dict = {}
    if pl is not None:
        for a in pl.anchors:
            p = pl.payload[a]
            t = (p.get("text") or "").strip()
            m = _EQNUM_RE.match(t)
            x0 = p.get("x0_norm")
            # Equation numbers hug a margin (right common, left for some styles).
            if m and x0 is not None and (x0 > 0.7 or x0 < 0.18):
                numbers_by_page.setdefault(p.get("page"), []).append(
                    (a, p.get("y_norm"), m.group(1), t))

    pages = {p["page"]: p for p in doc.meta.get("pages", [])}
    from_mathpix = recovered = 0
    for o in doc.objects.values():
        if o.type != "Equation":
            continue
        rn = (o.props.get("refnum") or "").strip()
        if rn:
            o.props["equation_number"] = rn if rn.startswith("(") else f"({rn})"
            from_mathpix += 1
            continue

        region = o.props.get("region")
        page = o.props.get("page")
        pm = pages.get(page)
        if not region or not pm or not pm.get("page_height"):
            continue
        h = region.get("height") or 0
        eq_yc = ((region.get("top_left_y") or 0) + h / 2) / pm["page_height"]

        best = None
        best_d = tol + 1.0
        for (a, yn, num, t) in numbers_by_page.get(page, []):
            if yn is None:
                continue
            d = abs(yn - eq_yc)
            if d < best_d:
                best_d, best = d, (a, num, t)
        if best and best_d <= tol:
            a, num, t = best
            o.props["refnum"] = num
            o.props["equation_number"] = _as_display(t, num)
            recovered += 1
            sr = next((r for r in o.realizations
                       if r.stream == "mathpix_lines" and r.start is not None), None)
            if sr is not None:
                doc.add_alignment(Alignment(
                    kind="equation_number",
                    left=Range("mathpix_lines", sr.start, sr.end),
                    right=Range("pdf_lines", a, a),
                    props={"number": num}))
    return {"from_mathpix": from_mathpix, "recovered": recovered}
