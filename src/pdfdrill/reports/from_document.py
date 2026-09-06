"""Rows from the Document. The ONLY model-aware module in the package.

Identity comes from the TiddlyWiki projector — `math_titles` for EQ/FO and
`region_titles` for TAB/DIA/PIC — because it is the naming authority every
other consumer imports (its docstring: a second implementation would
silently drift). The projector is a peer this module depends on for
identity, not an upstream stage whose output it reads.
"""
from __future__ import annotations

from pathlib import Path

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
    """{kind: [rows]} in flow order, named by the projector's authority."""
    ink = ink or {}
    names = dict(math_titles(doc, bibkey))
    names.update(region_titles(doc, bibkey))
    if lines_path is None:
        sp = str((doc.meta or {}).get("source_path") or "")
        lines_path = sp if sp.endswith(".lines.json") else None
    formulas = _flow(doc.objects_of_type("Formula"))
    hosts = _host_lines(formulas, lines_path)

    out = {"equation": [], "formula": [], "table": [], "image": []}
    for e in _flow(doc.objects_of_type("Equation")):
        p = e.props
        eqn = p.get("equation_number") or (
            "(%s)" % p["refnum"] if p.get("refnum") else "")
        reg = _region(p)
        out["equation"].append(EquationRow(
            identifier=names[e.id], latex=p.get("latex") or "",
            page=_page(p.get("page")), trailing_punct=p.get("trailing_punct") or "",
            confidence=_float(p.get("confidence")), cdn_url=p.get("cdn_url") or "",
            region=reg, eqnum=eqn, px_width=str(reg.get("width", "")),
            ink=ink.get(names[e.id])))
    for f in formulas:
        p = f.props
        lx = p.get("latex") or ""
        out["formula"].append(FormulaRow(
            identifier=names[f.id], latex=lx, page=_page(p.get("page")),
            trailing_punct=p.get("trailing_punct") or "",
            host_line=hosts.get(lx.strip())))
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
