r"""Phase 3 — table structure from ink, cross-checked against MathPix.

Two producers draw tables two ways, and pdfdrill has only ever seen one.

CONNECTED GRID (Word, InDesign). The ruled table is ONE component and its
HOLES are its cells. Infineon p19: 52 holes = 13 rows x 4 columns, recovered
with column widths 45.0 / 42.7 / 99.5 / 278.3 pt and row heights alternating
37.8 / 23.8 — the alternation IS the rows whose text wraps to two lines, which
a cell-text extractor discards and a LaTeX round trip needs.

DISJOINT RULES (LaTeX booktabs). No frame, no holes, so the hole lattice finds
nothing; recovering those cells needs collinear rule grouping instead. Both
cases occur in the corpus and THE DISCRIMINATOR IS ONE NUMBER — does the
largest component in the region have holes. 52 versus 0 is not a marginal call,
so the hole count travels into the report rather than being recomputed by a
reader.

This module is GLUE and deliberately thin:

* inkdrill's `simple_cell` lines carry `cell_row`/`cell_column`/spans on
  purpose, so they go through the EXISTING `table_structure.cells_from_mathpix`
  **unchanged**. There is no second cell reader here, and a test asserts the
  reuse — two readers would make a scoring difference indistinguishable from a
  format difference.
* the verdicts come from the EXISTING `ink_crosscheck.crosscheck_tables`, and
  the warnings from the EXISTING `table_structure.check`, which is what makes
  it an independent second opinion rather than a second implementation.

The one thing this module must get right on its own is the COORDINATE SPACE:
the docmodel holds MathPix pixels and inkdrill declares points. Comparing them
raw yields an IoU of zero for a table both tools found, which reads as "only in
the model" — a units bug wearing the costume of a finding.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from .ink_crosscheck import GRID_DISAGREE, ONLY_IN_MODEL, crosscheck_tables
from .ink_rules import rank_rules
from .table_structure import cells_from_mathpix

_CELL_TYPES = ("simple_cell", "complex_cell", "table_spanning_cell")


def _rect(region: dict) -> tuple[float, float, float, float]:
    x = float(region["top_left_x"])
    y = float(region["top_left_y"])
    return (x, y, x + float(region["width"]), y + float(region["height"]))


def _inside(outer: dict, inner: dict, pad: float = 1.0) -> bool:
    ox0, oy0, ox1, oy1 = _rect(outer)
    ix0, iy0, ix1, iy1 = _rect(inner)
    return (ix0 >= ox0 - pad and iy0 >= oy0 - pad
            and ix1 <= ox1 + pad and iy1 <= oy1 + pad)


def tables_of(ink_lines: dict, page: int) -> list[dict]:
    """inkdrill's tables on one page, cells read by the MathPix reader.

    A cell belongs to the table that CONTAINS it. Without that, two tables on
    one page merge into a single grid whose row count is the sum of theirs.
    """
    out: list[dict] = []
    for rec in ink_lines.get("pages", []):
        if rec.get("page") != page:
            continue
        lines = rec.get("lines", [])
        tables = [ln for ln in lines if ln.get("type") == "table" and ln.get("region")]
        cells = [ln for ln in lines
                 if ln.get("type") in _CELL_TYPES and ln.get("region")]
        for t in tables:
            mine = [c for c in cells if _inside(t["region"], c["region"])]
            cs, nr, nc = cells_from_mathpix(mine)
            ink = t.get("ink") or {}
            out.append({
                "region": t["region"],
                "cells": cs,
                "n_rows": nr,
                "n_cols": nc,
                # the discriminator, carried not recomputed
                "holes": ink.get("holes"),
                "ink_rows": ink.get("rows"),
                "ink_columns": ink.get("columns"),
                # Phase 4: rank the rules of THIS table. Scoping matters — the
                # same ranking over a diagram's rules names UI bars inside a
                # screenshot `toprule`, which is mechanically consistent and
                # about a thing that is not a table.
                "rules": rank_rules(ink.get("rules") or []),
            })
    return out


def grid_metrics(cells: Sequence[dict]) -> dict:
    """Column widths and row heights, in points, from the cell rectangles.

    This is the part a cell-text extractor discards and a LaTeX round trip
    needs: on Infineon p19 the row heights alternate 37.8 / 23.8 and the
    alternation IS the rows whose text wraps to two lines.

    One representative cell per column and per row — a spanning cell would
    report the span's width as a column's, so cells with a span > 1 are not
    used as representatives.
    """
    cols: dict[int, float] = {}
    rows: dict[int, float] = {}
    for c in cells:
        reg = c.get("region") or {}
        if not reg:
            continue
        if int(c.get("col_span") or 1) == 1:
            cols.setdefault(int(c["col"]), round(float(reg["width"]), 1))
        if int(c.get("row_span") or 1) == 1:
            rows.setdefault(int(c["row"]), round(float(reg["height"]), 1))
    return {"col_widths": [cols[k] for k in sorted(cols)],
            "row_heights": [rows[k] for k in sorted(rows)]}


def page_has_lattice(ink_lines: dict, page: int) -> bool:
    """Did the hole lattice apply on this page at all?

    False means inkdrill SAID NOTHING about tables here — the disjoint-rule
    case — which is a different statement from inkdrill contradicting MathPix.
    """
    return bool(tables_of(ink_lines, page))


def model_tables_pt(tables: Sequence[dict], page_px: tuple[float, float],
                    page_pt: tuple[float, float]) -> list[dict]:
    """Model tables with their regions moved from MathPix pixels into points."""
    px_w, px_h = page_px
    sx, sy = float(page_pt[0]) / float(px_w), float(page_pt[1]) / float(px_h)
    out = []
    for t in tables:
        reg = t.get("region") or {}
        conv = dict(t)
        if reg:
            conv["region"] = {
                "top_left_x": float(reg["top_left_x"]) * sx,
                "top_left_y": float(reg["top_left_y"]) * sy,
                "width": float(reg["width"]) * sx,
                "height": float(reg["height"]) * sy,
            }
        out.append(conv)
    return out


def slot_diff(model_cells: Sequence[dict], ink_cells: Sequence[dict]) -> dict:
    """Which (row, col) slots each side covers that the other does not.

    Measured on Infineon p19: both tools report 13x4, MathPix emits 44 cells
    and the ink 52, and the 8 MathPix omits are exactly the EMPTY slots — it
    emits a cell when there is text, while a hole is a hole either way. The two
    are therefore COMPLEMENTARY, not contradictory: MathPix supplies the text
    for 44 and the ink supplies the 8 empties, and a LaTeX round trip needs all
    52 because an empty cell is still an `&`.

    Calling that "disagreement" would read as a defect in one tool, so the
    slots are NAMED. A cell-count difference alone is a different event from a
    row/column difference and must not print the same.

    A cell carrying no `row`/`col` has no slot and cannot participate. It is
    COUNTED rather than dropped: raising would abort the whole cross-check over
    one malformed cell, and skipping in silence would shrink the denominator
    and make the two sides look more alike than they are.
    """
    def slots(cells):
        placed, unplaced = set(), 0
        for c in cells:
            try:
                placed.add((int(c["row"]), int(c["col"])))
            except (KeyError, TypeError, ValueError):
                unplaced += 1
        return placed, unplaced

    m, m_un = slots(model_cells)
    k, k_un = slots(ink_cells)
    model_missing = sorted(k - m)
    ink_missing = sorted(m - k)
    return {"model_missing": model_missing, "ink_missing": ink_missing,
            "model_unplaced": m_un, "ink_unplaced": k_un,
            "same_grid_population_differs": bool(model_missing or ink_missing)}


def crosscheck(model_tables: Sequence[dict], ink_tbls: Sequence[dict]) -> list[dict]:
    """Verdicts from the existing cross-checker, with the lattice case named.

    An `only_in_model` finding on a page where inkdrill emitted NO table is the
    booktabs case, not a contradiction — flagged `no_lattice` so a reader is
    not told that ink disagrees when ink was silent.
    """
    model_list, ink_list = list(model_tables), list(ink_tbls)
    findings = crosscheck_tables(model_list, ink_list)
    no_lattice = not ink_list
    for f in findings:
        if f["verdict"] == ONLY_IN_MODEL:
            f["no_lattice"] = no_lattice
        elif f["verdict"] == GRID_DISAGREE:
            # attach the slot difference so a same-grid/different-population
            # case can be told apart from a real grid disagreement
            m = _match_by_grid(model_list, f.get("model"))
            k = _match_by_grid(ink_list, f.get("ink"))
            if m is not None and k is not None:
                f["slots"] = slot_diff(m.get("cells") or [], k.get("cells") or [])
    return findings


def _match_by_grid(tables: Sequence[dict], summary: Optional[dict]):
    """The table a `_grid` summary came from. The cross-checker reports the
    summary, and the slot diff needs the cells behind it."""
    if not summary:
        return None
    for t in tables:
        if (t.get("n_rows") == summary.get("n_rows")
                and t.get("n_cols") == summary.get("n_cols")
                and len(t.get("cells") or []) == summary.get("cells")):
            return t
    return None
