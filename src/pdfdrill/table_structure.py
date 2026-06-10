"""
Span-aware table structure — the ONE place that knows the cell model.

A table is NOT a naive matrix: a header like "BiomedicalData" lives once in its
top-left (anchor) slot and COVERS a range of columns; a row-group label covers a
range of rows. So a cell is

    {"row": r, "col": c, "row_span": rs, "col_span": cs, "text": …, "region"?: …}

and covered slots are not stored at all (HTML's table model — which is why
`to_html` is the natural QA projection: rowspan/colspan render it directly).

Two producers fill this shape:
  * cells_from_mathpix(children)  — MathPix lines.json cells already carry
    cell_row/cell_column/cell_row_span/cell_col_span (incl. table_spanning_cell).
  * cells_from_plumber(table)     — a pdfplumber `find_tables()` Table: the grid
    is derived from the unique cell-rect edges; a rect covering k grid columns
    has col_span k. Text comes from the table's own extract() matrix (the value
    sits at the anchor slot; covered slots are None).

Helpers: column_headers (one clean, linefeed-free name per column — so a column
can later be FOUND by name), grid (back to the naive matrix for compatibility),
to_html (QA projection), check (overlap/overflow validation). Pure module: no
I/O, no pdfplumber import.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any, Optional

_CELL_KEYS = ("row", "col", "row_span", "col_span")
_WS = re.compile(r"\s+")
_SOFT_BREAK = re.compile(r"-\s*\n\s*")


def _clean(text: str) -> str:
    """Header text without formatting linefeeds: join soft line-break hyphens
    (Repre-\\nsentation -> Repre-sentation), collapse whitespace runs."""
    s = _SOFT_BREAK.sub("-", str(text or ""))
    return _WS.sub(" ", s).strip()


# --------------------------------------------------------------- producers
def cells_from_mathpix(children: list[dict[str, Any]]) -> tuple[list[dict], int, int]:
    """MathPix cell payloads (simple_cell/complex_cell/table_spanning_cell)
    -> (cells, n_rows, n_cols). Non-cell children (table_row) are skipped."""
    cells: list[dict] = []
    for ch in children:
        if "cell_row" not in ch or "cell_column" not in ch:
            continue
        cell = {
            "row": int(ch["cell_row"]),
            "col": int(ch["cell_column"]),
            "row_span": int(ch.get("cell_row_span") or 1),
            "col_span": int(ch.get("cell_col_span") or 1),
            "text": ch.get("text") or "",
        }
        if ch.get("region"):
            cell["region"] = ch["region"]
        cells.append(cell)
    n_rows = max((c["row"] + c["row_span"] for c in cells), default=0)
    n_cols = max((c["col"] + c["col_span"] for c in cells), default=0)
    return cells, n_rows, n_cols


def _edges(values: list[float], tol: float = 1.0) -> list[float]:
    """Sorted unique edge coordinates, merging edges closer than tol."""
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _edge_index(edges: list[float], v: float, tol: float = 1.0) -> int:
    for i, e in enumerate(edges):
        if abs(e - v) <= tol:
            return i
    return -1


def cells_from_plumber(table: Any) -> tuple[list[dict], int, int]:
    """A pdfplumber Table (duck-typed: .cells rects + .extract() matrix)
    -> (cells, n_rows, n_cols) with spans reconstructed from the rect grid."""
    rects = [r for r in (table.cells or []) if r]
    if not rects:
        return [], 0, 0
    xs = _edges([r[0] for r in rects] + [r[2] for r in rects])
    ys = _edges([r[1] for r in rects] + [r[3] for r in rects])
    matrix = table.extract() or []
    cells: list[dict] = []
    for (x0, top, x1, bottom) in rects:
        col, row = _edge_index(xs, x0), _edge_index(ys, top)
        col2, row2 = _edge_index(xs, x1), _edge_index(ys, bottom)
        if min(col, row, col2, row2) < 0:
            continue
        text = ""
        if row < len(matrix) and col < len(matrix[row]):
            text = matrix[row][col] or ""
        cells.append({
            "row": row, "col": col,
            "row_span": max(1, row2 - row), "col_span": max(1, col2 - col),
            "text": text,
            "region": {"top_left_x": x0, "top_left_y": top,
                       "width": x1 - x0, "height": bottom - top},
        })
    n_rows, n_cols = len(ys) - 1, len(xs) - 1
    return cells, n_rows, n_cols


# --------------------------------------------------------------- queries
def _covering(cells: list[dict], row: int, col: int) -> Optional[dict]:
    for c in cells:
        if (c["row"] <= row < c["row"] + c["row_span"]
                and c["col"] <= col < c["col"] + c["col_span"]):
            return c
    return None


def column_headers(cells: list[dict], n_cols: int) -> tuple[list[str], int]:
    """One clean name per column + the header-row count.

    Header rows run from row 0 through the first ALL-LEAF row (every cell
    anchored there has col_span == 1) after the span-bearing rows; a table with
    no column spans has just row 0 as header. Per column the covering header
    cells' texts are joined top->bottom, a rowspan'd cell appearing once, each
    cleaned of linefeeds — so "BiomedicalData" + "Acronym" + "P" becomes the
    findable column name "BiomedicalData Acronym P".
    """
    n_rows = max((c["row"] + c["row_span"] for c in cells), default=0)
    header_rows = 1
    for r in range(n_rows - 1):           # need at least one data row
        anchored = [c for c in cells if c["row"] == r]
        if any(c["col_span"] > 1 for c in anchored):
            header_rows = r + 2           # spans here -> the NEXT row is leaf
        else:
            break
    header_rows = min(header_rows, max(1, n_rows - 1))
    columns: list[str] = []
    for col in range(n_cols):
        seen: list[int] = []
        parts: list[str] = []
        for r in range(header_rows):
            cell = _covering(cells, r, col)
            if cell is None or id(cell) in seen:
                continue
            seen.append(id(cell))
            t = _clean(cell["text"])
            if t:
                parts.append(t)
        columns.append(" ".join(parts))
    return columns, header_rows


def grid(cells: list[dict], n_rows: int, n_cols: int) -> list[list[str]]:
    """Back to the naive matrix: value at the anchor slot, '' in covered slots."""
    g = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        if c["row"] < n_rows and c["col"] < n_cols:
            g[c["row"]][c["col"]] = c["text"] or ""
    return g


# --------------------------------------------------------------- projections
def to_html(cells: list[dict], n_rows: int, n_cols: int, caption: str = "",
            columns: Optional[list[str]] = None, header_rows: int = 1) -> str:
    """The QA projection: a real <table> with rowspan/colspan (covered slots
    skipped), header rows as <th> in <thead>, each th carrying its flattened
    column name(s) as a title tooltip."""
    by_row: dict[int, list[dict]] = {}
    for c in cells:
        by_row.setdefault(c["row"], []).append(c)
    out = ["<table>"]
    if caption:
        out.append(f"  <caption>{_html.escape(caption)}</caption>")

    def _tr(r: int, tag: str) -> str:
        tds = []
        for c in sorted(by_row.get(r, []), key=lambda c: c["col"]):
            attrs = ""
            if c["row_span"] > 1:
                attrs += f' rowspan="{c["row_span"]}"'
            if c["col_span"] > 1:
                attrs += f' colspan="{c["col_span"]}"'
            if tag == "th" and columns:
                names = "; ".join(
                    n for n in columns[c["col"]:c["col"] + c["col_span"]] if n)
                if names:
                    attrs += f' title="{_html.escape(names, quote=True)}"'
            tds.append(f"<{tag}{attrs}>{_html.escape(_clean(c['text']))}</{tag}>")
        return "    <tr>" + "".join(tds) + "</tr>"

    hr = min(header_rows, n_rows)
    if hr:
        out.append("  <thead>")
        out.extend(_tr(r, "th") for r in range(hr))
        out.append("  </thead>")
    out.append("  <tbody>")
    out.extend(_tr(r, "td") for r in range(hr, n_rows))
    out.append("  </tbody>")
    out.append("</table>")
    return "\n".join(out)


# --------------------------------------------------------------- validation
def check(cells: list[dict], n_rows: int, n_cols: int) -> list[str]:
    """Overlaps and out-of-grid spans as warning strings (never raises)."""
    warnings: list[str] = []
    owner: dict[tuple[int, int], dict] = {}
    for c in cells:
        if c["row"] + c["row_span"] > n_rows or c["col"] + c["col_span"] > n_cols:
            warnings.append(
                f"cell at ({c['row']},{c['col']}) exceeds the {n_rows}x{n_cols} grid")
            continue
        for r in range(c["row"], c["row"] + c["row_span"]):
            for k in range(c["col"], c["col"] + c["col_span"]):
                if (r, k) in owner:
                    warnings.append(f"overlap at ({r},{k})")
                else:
                    owner[(r, k)] = c
    return warnings
