"""Rows from the Document. The ONLY model-aware module in the package.

Identity comes from the TiddlyWiki projector — `math_titles` for EQ/FO and
`region_titles` for TAB/DIA/PIC — because it is the naming authority every
other consumer imports (its docstring: a second implementation would
silently drift). The projector is a peer this module depends on for
identity, not an upstream stage whose output it reads.
"""
from __future__ import annotations

from pathlib import Path

from docmodel import line_types
from docops.projectors.tiddlywiki import math_titles, region_titles
from .rows import (EquationRow, FormulaRow, TableRow, ImageRow, HostLine)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flow(objs):
    return sorted(objs, key=lambda o: o.props.get("flow_index", 10**9))


def _region(props: dict) -> dict:
    r = props.get("region") or {}
    return {k: r[k] for k in ("top_left_x", "top_left_y", "width", "height")
            if r.get(k) is not None}


def _dims(region: dict) -> tuple:
    return (str(region.get("width", "")), str(region.get("height", "")))


def _page(v):
    return None if v in (None, "") else str(v)


def _chosen_reading(obj) -> "tuple[str, dict | None]":
    """(the latex a PUBLISHED report should show, its refined evidence or None).

    669 -- PROPS.md's `latex_refined` row states the defect plainly: "a
    VERIFIED refinement in a twin prop; `latex` is never overwritten (232).
    Reading `latex` alone ignores every accepted repair (233)." This
    module's `build_rows` used to do exactly that.

    `refine.chosen_latex` is the EXISTING read-time choice (233) and is
    reused as-is -- it already refuses to prefer a CONTRADICTED, UNVERIFIED
    or ORPHANED refinement via `refine.refinement_state`, which is the
    whole reason that function exists (its own docstring: a caller that
    treats those as NONE "is making the same mistake this function was
    split to end"). What it does not check is whether the VERIFIED value it
    prefers can be typeset at all. Measured across the 20 published
    documents (2026-09-11, counted by `doc.objects_of_type` over BOTH
    types this function handles -- not assumed from the two-EQ/one-FO
    sample below, which is the mistake fix round 1 caught in this file's
    own out/669.txt): 31 objects carry a VERIFIED `latex_refined` --
    30 Equation, 1 Formula (0707.4470_FO0175, obj_0c9487434929, live in
    production, both readings render). 28 have both readings render
    (including that one Formula), 2 have the raw REFUSED and the refined
    render (the clear win: 0902.0431_EQ1032/EQ1187), and exactly 1
    (lyche-numerical-linear-algebra_EQ0579, a misattributed span) has the
    raw render and the refined REFUSED -- `chosen_latex` alone would
    replace that one rendering row with a blank one. So the raw is kept
    whenever the refined does not survive `report_tex.display_safe`, and
    only then; that is 30 of 31 refined instead of "always" (31, breaks the
    1) or "only when the raw is refused" (2, leaves 28 accepted repairs
    unread -- the defect PROPS.md names).

    Returns the ORIGINAL evidence dict verbatim (not a bespoke shape) so
    `report_tex.refined_flag`/`refined_note` -- the retired path's own
    mechanism for saying "this row is a refinement," 233 -- can mark these
    rows and explain them without being rebuilt.
    """
    from .. import refine as _rf
    from .. import report_tex as _rt
    value, ev = _rf.chosen_latex(obj)
    if ev and "refinement_state" not in ev and _rt.display_safe(value):
        return value, ev
    return (getattr(obj, "props", None) or {}).get("latex") or "", None


def _host_lines(formulas, lines_path) -> dict:
    """{latex: HostLine} by exact first occurrence, or {} without lines.json."""
    if not lines_path or not Path(lines_path).is_file():
        return {}
    from pdfdrill import inlinectx
    first = inlinectx.first_occurrences(inlinectx.load_spans(lines_path))
    out = {}
    for f in formulas:
        lx = (f.props.get("latex") or "").strip()
        ctx = inlinectx.context_of(first.get(lx)) if lx else {}
        if ctx:
            out[lx] = HostLine(
                page=ctx.get("page"), line_type=ctx.get("line_type"),
                confidence=_float(ctx.get("confidence")),
                region={k: ctx[k] for k in ("top_left_x", "top_left_y",
                                            "width", "height") if k in ctx})
    return out


def build_rows(doc, bibkey: str, *, ink: "dict | None" = None,
               lines_path=None) -> dict:
    """{kind: [rows]} in flow order, named by the projector's authority.

    669 -- each Equation/Formula row's `.refined_info` is set (non-None)
    exactly when `.latex` is a VERIFIED, renderable refinement rather than
    the raw MathPix reading (see `_chosen_reading`). The return shape is
    otherwise UNCHANGED -- callers that walk `rows.values()` as lists of
    row objects (`ensure_crops`/`crops.records`, both do) must keep seeing
    exactly that; a `"refined"` map lived here as a fifth key for one
    iteration and broke both, since `dataclasses.replace` was handed a dict
    key string instead of a row. `refined_rows_map` below reads it back
    out.
    """
    ink = ink or {}
    names = dict(math_titles(doc, bibkey))
    names.update(region_titles(doc, bibkey))
    if lines_path is None:
        sp = str((doc.meta or {}).get("source_path") or "")
        lines_path = sp if sp.endswith(".lines.json") else None
    # A formula whose EVERY occurrence sits on a table cell, a section
    # heading, a title, a TOC entry, a figure label or inside a CAPTION is
    # not an inline formula --- docmodel/line_types.py. `FormulaProcessor`
    # no longer creates the type-based ones, but every model on disk
    # predates that gate and this is the PUBLISHED surface, so the refusal
    # is applied at read time too. The caption half has no creation-time
    # gate at all and can only be applied here and in the projector: a
    # caption's SPAN is a Paragraph property (`kind: "caption"`) and
    # `FormulaProcessor` runs at procOrder 12, before ParagraphProcessor's
    # 13 (676, review B1).
    # `math_titles` is left alone deliberately: the surviving rows keep the
    # identifiers they were published under, which is what `crop_sha256`
    # and the ink measurements are keyed on (667).
    _captions = line_types.caption_anchors(doc)
    formulas = [f for f in _flow(doc.objects_of_type("Formula"))
                if not line_types.no_transclusion_site(
                    f, doc, captions=_captions)]
    hosts = _host_lines(formulas, lines_path)

    out = {"equation": [], "formula": [], "table": [], "image": []}
    for e in _flow(doc.objects_of_type("Equation")):
        p = e.props
        eqn = p.get("equation_number") or (
            "(%s)" % p["refnum"] if p.get("refnum") else "")
        reg = _region(p)
        latex, refined_ev = _chosen_reading(e)
        out["equation"].append(EquationRow(
            identifier=names[e.id], latex=latex,
            page=_page(p.get("page")), trailing_punct=p.get("trailing_punct") or "",
            confidence=_float(p.get("confidence")), cdn_url=p.get("cdn_url") or "",
            region=reg, eqnum=eqn, px_width=str(reg.get("width", "")),
            ink=ink.get(names[e.id]), refined_info=refined_ev))
    for f in formulas:
        p = f.props
        # host-line lookup keys on MathPix's OWN reading -- the text a
        # `first_occurrences` span was recorded against never changes, so
        # this must stay the raw prop even when `latex` below is refined.
        raw_lx = p.get("latex") or ""
        latex, refined_ev = _chosen_reading(f)
        out["formula"].append(FormulaRow(
            identifier=names[f.id], latex=latex, page=_page(p.get("page")),
            trailing_punct=p.get("trailing_punct") or "",
            host_line=hosts.get(raw_lx.strip()), refined_info=refined_ev))
    for t in _flow(doc.objects_of_type("Table")):
        p = t.props
        reg = _region(p)
        out["table"].append(TableRow(
            identifier=names[t.id],
            latex=p.get("latex_code") or p.get("mathpix_text") or "",
            page=_page(p.get("page")), confidence=_float(p.get("confidence")),
            cdn_url=p.get("cdn_url") or "", region=reg, dims=_dims(reg)))
    for kind in ("Diagram", "Picture"):
        for o in _flow(doc.objects_of_type(kind)):
            p = o.props
            reg = _region(p)
            out["image"].append(ImageRow(
                identifier=names[o.id], latex=p.get("latex_code") or "",
                page=_page(p.get("page")),
                cdn_url=p.get("cdn_url") or p.get("url") or "",
                region=reg, dims=_dims(reg)))
    return out


def refined_rows_map(rows_by_kind: dict) -> dict:
    """{identifier: refined-evidence dict} for the rows that published one.

    669 -- reads `.refined_info` back off the rows `build_rows` already
    stamped, rather than a second key on that dict (see its docstring for
    why one was tried and reverted). Shaped for `report_tex.refined_note`
    (which shares this dict's SHAPE, not this function).

    669, fix round 1 (review, minor finding): named `refined_map` through
    fix round 0, which collided in NAME (not behaviour -- nothing ever
    called both, and nothing does today) with `report_tex.refined_map`
    (128), a same-named, unrelated function on the RETIRED reading path:
    {tiddler title: info} from a tiddler ARRAY's `latex_refined`/
    `refined_verified_by` fields, not {identifier: info} from `build_rows`'
    ROW OBJECTS. Renamed here rather than there -- `report_tex.refined_map`
    is the older name, has its own tests (`test_prefer_refined.py`) and its
    own internal caller (`findings_rows`'s `prefer_refined` chain), and
    touching it would be touching the retired path this task was told not
    to rebuild for a cosmetic reason.
    """
    out = {}
    for kind in ("equation", "formula"):
        for r in rows_by_kind.get(kind) or ():
            if getattr(r, "refined_info", None):
                out[r.identifier] = r.refined_info
    return out
