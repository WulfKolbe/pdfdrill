"""equations - equation entries for the evidence apparatus.

pdfdrill builds an evidence table per document, one row per equation:

    Identifier | Page | Conf. | LaTeX source | Rendered | Image

`Rendered` is the LaTeX compiled; `Image` is the crop from the original PDF.
inkdrill compares the two as INK, and every deviation becomes a residual the
user acts on. That comparison is only as good as the row it is given, so
this module's job is to produce rows that are honest about what they are:

    IDENTIFIER   stable across runs. Content-addressed like the docpack
                 anchors, not sequential, so re-reading a document does not
                 renumber everything and turn a diff into noise. The
                 human-readable `EQnnnn` is kept alongside for the table.

    CONFIDENCE   the fraction of the equation's maths that PROJECTED. An
                 equation with a deferred span is not wrong, it is partly
                 unread, and the number says which. The evidence table's
                 first row shows 0.672 against 1.000 elsewhere; that is
                 exactly this quantity and it points at the `cases`
                 construct 695 measured and did not reconstruct.

    REGION       in the same 250-dpi pixel space as lines.json and the crop
                 URLs, so the Image column needs no rescaling.

    KIND         "display" or "inline". They are scored differently: a
                 display equation is a whole line and its crop is
                 unambiguous, while an inline one shares its line with prose
                 and the crop carries neighbours.

CONTRACT
    equations(pages, bibkey) -> list[Equation]
    Equation.latex           None when nothing projected -- the row still
                             exists, because an equation that produced no
                             LaTeX is the most important row in the table.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import docmodel_six as docmodel
import project_mmd as mmd


@dataclass
class Equation:
    ident: str                      # content-addressed
    label: str                      # EQnnnn, for the table
    page: int
    kind: str                       # "display" | "inline"
    latex: str | None
    confidence: float
    region: dict                    # pixels, 250 dpi, y down
    spans: int
    projected: int
    structural_ok: bool = True
    line_id: str = ""
    deferred: list = field(default_factory=list)

    def as_row(self) -> dict:
        """The evidence table's row."""
        return {
            "identifier": self.label,
            "ident": self.ident,
            "page": self.page,
            "kind": self.kind,
            "confidence": round(self.confidence, 3),
            "structural_ok": self.structural_ok,
            "latex": self.latex,
            "region": self.region,
            "spans": self.spans,
            "projected": self.projected,
            "deferred": self.deferred,
        }


def _ident(bibkey: str, page: int, region: dict, latex: str | None) -> str:
    blob = f"{bibkey}|{page}|{region['top_left_x']},{region['top_left_y']}," \
           f"{region['width']},{region['height']}|{latex or ''}"
    return "eq_" + hashlib.blake2b(blob.encode("utf-8"),
                                   digest_size=6).hexdigest()


def equations(pages: list, bibkey: str = "pdfdrill",
              px_per_pt: float = docmodel.PX_PER_PT) -> list[Equation]:
    """Every equation in the document, display and inline."""
    out: list[Equation] = []
    for page in pages:
        left = mmd._left_margin(page)
        run: list = []

        def flush_display():
            if run:
                out.append(_build_multi(page, run, bibkey, px_per_pt))
                run.clear()

        for line in page.lines:
            maths = [sp for sp in line.spans if sp.kind == "math"]
            if not maths:
                flush_display()
                continue
            if mmd.is_display(line, left):
                # CONSECUTIVE display lines are ONE equation. A `cases`
                # construct reaches the page as a fence line, a left-hand
                # side and one line per branch; scored separately each came
                # out at 1.000 while the construct as a whole was not
                # reconstructed at all. The reference evidence table shows
                # that same equation at 0.672, as one row.
                if run and _far_below(run[-1][0], line):
                    flush_display()
                run.append((line, maths))
            else:
                flush_display()
                for sp in maths:
                    out.append(_build(page, line, [sp], "inline", bibkey,
                                      px_per_pt))
        flush_display()
    for i, eq in enumerate(out, 1):
        eq.label = f"EQ{i:04d}"
    return out


def _far_below(prev, line) -> bool:
    """Is this display line a new equation rather than the next line of one?"""
    size = max((g.size for g in line.glyphs), default=10.0)
    return (prev.rect[1] - line.rect[3]) > 1.2 * size


def _build_multi(page, run, bibkey, px_per_pt) -> Equation:
    lines = [ln for ln, _ in run]
    spans = [sp for _, ms in run for sp in ms]
    eq = _build(page, lines[0], spans, "display", bibkey, px_per_pt)
    rect = (min(ln.rect[0] for ln in lines), min(ln.rect[1] for ln in lines),
            max(ln.rect[2] for ln in lines), max(ln.rect[3] for ln in lines))
    eq.region = docmodel._px_region(rect, page, px_per_pt)
    eq.ident = _ident(bibkey, page.page, eq.region, eq.latex)
    eq.line_id = ",".join(ln.id for ln in lines)
    return eq


# Delimiters that OPEN something. A construct carrying one with nothing to
# close it was not reconstructed, however well its pieces projected.
_UNBALANCED = ("\\Biggl", "\\Bigl", "\\biggl", "\\bigl", "\\left")


def _structural_penalty(latex: str | None) -> float:
    """How much of the STRUCTURE is missing, 0.0 to 1.0.

    Span projection alone says 1.000 for four fragments of a torn `cases`.
    An opener with no closer is the plainest evidence that the pieces were
    never assembled, and it is the case 695 measured and could not fix.
    """
    if not latex:
        return 0.0
    opens = sum(latex.count(c) for c in _UNBALANCED)
    closes = (latex.count("\\Biggr") + latex.count("\\Bigr")
              + latex.count("\\biggr") + latex.count("\\bigr")
              + latex.count("\\right"))
    if opens <= closes:
        return 0.0
    return min(1.0, (opens - closes) / max(opens, 1))


def _build(page, line, spans, kind, bibkey, px_per_pt) -> Equation:
    parts, projected, deferred = [], 0, []
    for sp in spans:
        tex = docmodel.span_latex(sp)
        if tex is None:
            deferred.append({"span": sp.id,
                             "reason": docmodel.span_reason(sp)})
        else:
            projected += 1
            parts.append(tex)
    rect = (min(sp.rect[0] for sp in spans), min(sp.rect[1] for sp in spans),
            max(sp.rect[2] for sp in spans), max(sp.rect[3] for sp in spans))
    region = docmodel._px_region(rect, page, px_per_pt)
    latex = " ".join(parts) if parts else None
    # Same gate as the markdown: an "equation" holding only delimiters or
    # nothing at all is not one. It is recorded with latex=None so the row
    # still exists in the evidence table -- an equation that produced
    # nothing is the most important row in it -- but it never claims to
    # have read something.
    if latex is not None and not mmd.has_content(latex):
        latex = None
        projected = 0
        deferred.append({"span": line.id, "reason": "no-content"})
    # Confidence is the PROJECTION fraction and nothing else. A structural
    # defect is reported SEPARATELY rather than folded into the number:
    # collapsing two different facts into one score is what makes a
    # benchmark unable to see its own errors, and the reference table's own
    # weighting is not known here. A consumer that wants one number can
    # combine them; one that wants to know WHY can read both.
    conf = projected / len(spans) if spans else 0.0
    structural = _structural_penalty(latex) == 0.0
    if not structural:
        deferred.append({"span": line.id, "reason": "unbalanced-delimiter"})
    return Equation(
        ident=_ident(bibkey, page.page, region, latex),
        label="", page=page.page, kind=kind, latex=latex,
        confidence=conf, structural_ok=structural,
        region=region, spans=len(spans), projected=projected,
        line_id=line.id, deferred=deferred)


def to_json(pages: list, bibkey: str = "pdfdrill") -> dict:
    """The evidence table as data, ready for the HTML report."""
    eqs = equations(pages, bibkey)
    return {
        "bibkey": bibkey,
        "counts": {
            "total": len(eqs),
            "display": sum(1 for e in eqs if e.kind == "display"),
            "inline": sum(1 for e in eqs if e.kind == "inline"),
            "complete": sum(1 for e in eqs
                            if e.confidence >= 0.999 and e.structural_ok),
            "unbalanced": sum(1 for e in eqs if not e.structural_ok),
            "partial": sum(1 for e in eqs if 0 < e.confidence < 0.999),
            "empty": sum(1 for e in eqs if e.confidence == 0),
        },
        "equations": [e.as_row() for e in eqs],
    }
