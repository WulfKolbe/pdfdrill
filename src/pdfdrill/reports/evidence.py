"""Evidence = every object of one kind, unbounded, six columns. Lookup, not
reading matter. No ink, no legend, no findings, no cell-rect marks."""
from __future__ import annotations

from pathlib import Path

from .. import report_tex as rt
from . import KINDS
from . import budget as _budget
from . import html as H
from . import tex as T
from .from_document import refined_rows_map as _refined_rows_map

OUTPUT = "evidence-%s.%s"
FORMATS = ("html", "pdf")


def ordered(rows: list, kind: str) -> list:
    if kind != "equation":
        return list(rows)
    return sorted(rows, key=lambda r: (r.confidence if r.confidence is not None
                                       else 2.0))


def _refined_summary(refined: dict) -> str:
    """The evidence-report top note (669): the plain-text (no LaTeX
    markup) form of `report_tex.refined_summary_text` -- this reaches
    `H.page_shell`'s plain `meta_lines`, which escapes it itself, not a
    `\\quote`.

    669, fix round 1 (review, minor finding): this used to inline its own
    near-verbatim copy of `refined_note`'s sentence-building; now both
    read the one shared builder so there is a single place that sentence
    is written.
    """
    return rt.refined_summary_text(refined)


def build(rows_by_kind: dict, kind: str, fmt: str, *, doc_dir, pdf, bibkey,
          history, px2mm, paper, landscape, compile_pdf,
          budget_mb: "float | None" = None, rung=None) -> dict:
    if kind not in KINDS:
        raise ValueError("kind must be one of %s, not %r" % (", ".join(KINDS), kind))
    if fmt not in FORMATS:
        raise ValueError("format must be html or pdf, not %r" % fmt)
    doc_dir = Path(doc_dir)
    rows = ordered(rows_by_kind.get(kind, []), kind)
    title = "%s: %s evidence" % (bibkey, kind)
    # 669 — {identifier: evidence} for the rows THIS kind's table actually
    # shows, from `from_document.refined_rows_map`; empty for table/image kinds,
    # which never carry `refined_info` (refine.MATH_TYPES is Equation and
    # Formula only).
    refined = _refined_rows_map({kind: rows}) if kind in ("equation", "formula") else {}
    if fmt == "html":
        out = doc_dir / (OUTPUT % (kind, "html"))
        meta = ["%d rows" % len(rows)]
        summary = _refined_summary(refined)
        if summary:
            meta.append(summary)
        out.write_text(H.render_page(rows, kind, title=title, doc_dir=doc_dir,
                                     meta_lines=tuple(meta)),
                       encoding="utf-8")
        return {"out": out, "rows": len(rows), "pages": None, "errors": 0,
                "demoted": 0}
    widths = T.widths_for(paper, landscape, with_image=True)
    body = T.render_table(rows, kind, widths=widths, out_dir=doc_dir,
                          px2mm=px2mm, bibkey=bibkey, history=history)
    if refined:
        # 233's own note, unchanged: this is the retired path's mechanism
        # for saying "these rows are refinements," reused rather than
        # rebuilt — see rt.refined_note's own docstring.
        body = rt.refined_note(refined) + body
    tex_path = doc_dir / (OUTPUT % (kind, "tex"))
    tex_path.write_text(T.document(body, paper=paper, landscape=landscape,
                                   pages=None, title=title), encoding="utf-8")
    res = {"out": tex_path.with_suffix(".pdf"), "rows": len(rows),
           "pages": None, "errors": 0, "demoted": 0}
    if compile_pdf:
        c = rt.compile_fixpoint(tex_path)
        if c is not None:
            res["pages"], res["errors"], res["demoted"] = c
    # 655 review round 1, finding 3 -- the SELECTION of a rung is a
    # prediction against crop bytes (`reports.budget.choose_rung`, run
    # earlier in `ensure_crops`); this is the VERDICT, checked against the
    # artefact `compile_fixpoint` just produced, which is the only "OVER
    # BUDGET" a caller should ever act on or print.
    if budget_mb is not None:
        res["bytes"], res["over_budget"] = _budget.check_artifact(
            res["out"], budget_mb=budget_mb)
        res["budget_mb"] = budget_mb
        # 655 review round 2 -- `rung` is the REAL `(scale, quality)` (or
        # None) `ensure_crops` chose for THIS kind, passed in by the
        # caller (it, not this function, ran `choose_rung`). Carried here
        # so `_evidence_line` can describe the actual state instead of
        # assuming every over-budget document sits at the floor.
        res["rung"] = rung
    return res
