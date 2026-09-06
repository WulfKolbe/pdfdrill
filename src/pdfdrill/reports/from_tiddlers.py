"""Rows from the tiddler projection. The ONLY tiddler-aware code in the
package; approach 3 replaces this module with a docmodel-fed one.

Reuses report_tex.rows_for so the row selection cannot drift from the
report the 21 documents were built with.
"""
from __future__ import annotations

from pathlib import Path

from ..report_tex import rows_for
from .rows import (EquationRow, FormulaRow, TableRow, ImageRow, HostLine)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _host_line(ctx: dict) -> "HostLine | None":
    if not ctx:
        return None
    region = {k: ctx[k] for k in ("top_left_x", "top_left_y", "width",
                                  "height") if k in ctx}
    return HostLine(page=ctx.get("page"), line_type=ctx.get("line_type"),
                    confidence=_float(ctx.get("confidence")), region=region)


def build_rows(tiddlers: list, bibkey: str, *, lines_path=None,
               ink: "dict | None" = None, refined=None) -> dict:
    """{kind: [rows]} in the order rows_for yields them."""
    fo, eq, tab, dia = rows_for(tiddlers, bibkey, refined)
    ink = ink or {}

    ctx: dict = {}
    if lines_path and Path(lines_path).is_file():
        from .. import inlinectx
        ctx = inlinectx.attach([r[1] for r in fo], lines_path)

    out = {"equation": [], "formula": [], "table": [], "image": []}
    for title, latex, page, num, wpx, punct, conf in eq:
        out["equation"].append(EquationRow(
            identifier=title, latex=latex, page=page or None,
            trailing_punct=punct or "", confidence=_float(conf),
            eqnum=num or "", px_width=str(wpx or ""),
            ink=ink.get(title)))
    for title, latex, page, punct in fo:
        out["formula"].append(FormulaRow(
            identifier=title, latex=latex, page=page or None,
            trailing_punct=punct or "",
            host_line=_host_line(ctx.get(latex or ""))))
    for title, latex, page, dims, region, conf in tab:
        out["table"].append(TableRow(
            identifier=title, latex=latex, page=page or None,
            confidence=_float(conf), dims=tuple(dims), region=tuple(region)))
    for title, latex, page, dims, region in dia:
        out["image"].append(ImageRow(
            identifier=title, latex=latex, page=page or None,
            dims=tuple(dims), region=tuple(region)))
    return out
