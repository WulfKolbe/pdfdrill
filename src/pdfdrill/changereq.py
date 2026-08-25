"""105 — the change-request loader, and a validator for numeric tables.

A proposal is an outside party's claim about what a row SHOULD say. It arrives
as JSON, is loaded here, and must survive validation before anything renders or
applies it. The point of validating structure before rendering is that a
malformed table still compiles: LaTeX will happily set a row with four entries
next to one with six, and the result looks like a table.

Row-width uniformity is the cheapest structural claim a numeric table makes
about itself. A discrete table of coefficients has one width; a row that does
not have it is a transcription that lost or gained an entry, and no amount of
rendering will show that to a reader who does not already know the width.

Two table forms appear in practice and both are checked:

    a & b & c \\\\        array cells, & separated
    = 1\\ 0\\ 1\\ 0        a numeric run after a relation, space separated
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: a numeric run following a relation: "= 1\ 0\ 1\ 0 0"
_RUN = re.compile(r"[=<>]\s*((?:[-+]?\d+(?:\\[ ,;]|~|\s)+)*[-+]?\d+)")
_NUM = re.compile(r"[-+]?\d+")
#: a cell that is nothing but a number
_CELL_NUM = re.compile(r"^\s*(?:\$)?\s*[-+]?\d+\s*(?:\$)?\s*$")
_ROWSEP = re.compile(r"\\\\")


@dataclass
class Proposal:
    target: str
    field_name: str
    proposed: str
    basis: str = ""
    author: str = ""
    at: str = ""
    rationale: str = ""
    status: str = "proposed"
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


#: environments whose body is a table of cells separated by & and rows by \\
_TABLE_ENVS = ("array", "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix",
               "Vmatrix", "smallmatrix", "cases", "tabular")
_BEGIN_TABLE = re.compile(
    r"\\begin\{(" + "|".join(_TABLE_ENVS) + r")\}\s*(?:\{[^}]*\}|\[[^]]*\])*")


def _table_bodies(latex: str) -> list:
    """The BODY of each top-level table environment, in order.

    Scanned with a depth counter rather than a regex, so an array nested
    inside another array is taken as part of its parent's cell and not as a
    second table with a torn-off body.
    """
    out, i, n = [], 0, len(latex or "")
    while i < n:
        m = _BEGIN_TABLE.search(latex, i)
        if not m:
            break
        env = m.group(1)
        depth, j = 1, m.end()
        open_re = re.compile(r"\\begin\{" + env + r"\}")
        close_re = re.compile(r"\\end\{" + env + r"\}")
        while j < n and depth:
            o, c = open_re.search(latex, j), close_re.search(latex, j)
            if not c:
                break
            if o and o.start() < c.start():
                depth += 1
                j = o.end()
            else:
                depth -= 1
                j = c.end()
                if not depth:
                    out.append(latex[m.end():c.start()])
        i = max(j, m.end())
    return out


_NESTED = re.compile(
    r"\\begin\{(" + "|".join(_TABLE_ENVS) + r")\}.*?\\end\{\1\}", re.S)


def _flatten_nested(body: str) -> str:
    """Replace any nested table with a single placeholder cell.

    A nested array's own `\\\\` row separators otherwise split the PARENT's
    rows, so an outer {c} column holding an inner {ccc} matrix reported widths
    {3: 6, 1: 2}. The inner table is measured on its own pass; to the outer it
    is one cell.
    """
    prev = None
    while prev != body:
        prev = body
        body = _NESTED.sub("N", body)
    return body


def _row_widths(body: str) -> list:
    """Cell counts per row of ONE table body, or [] if it is not numeric.

    Counts CELLS, not "cells that look like bare numbers". The old rule
    required every counted cell to be a bare number, so the first row of an
    array embedded in a larger expression — whose first cell carried the
    surrounding LaTeX — came up one short and a plain 4x4 matrix reported
    [[3],[4],[4],[3]]. Working on the extracted BODY removes that entirely:
    there is no surrounding LaTeX left to leak in.
    """
    rows = [r for r in _ROWSEP.split(_flatten_nested(body)) if r.strip()]
    if len(rows) < 2:
        return []
    widths, numeric_cells, total_cells = [], 0, 0
    for r in rows:
        cells = r.split("&")
        widths.append(len(cells))
        total_cells += len(cells)
        numeric_cells += sum(1 for c in cells if _CELL_NUM.match(c))
    # a table of numbers, not prose that happens to contain an alignment tab
    if total_cells and numeric_cells >= max(2, 0.6 * total_cells):
        return widths
    return []


def numeric_tables(latex: str) -> list:
    """One entry per numeric TABLE; each entry is that table's row widths.

    A value holding two matrices is TWO tables. `A=(3x3) B=(1x4)` is not a
    ragged table, and reporting it as one was the second defect here: the
    check assumed one width per value, which is false for any value that
    contains more than one array.
    """
    out = [w for w in (_row_widths(b) for b in _table_bodies(latex or "")) if w]
    if out:
        return out
    # No table environment: the relation form, "= 1\ 0\ 1\ 0", which the
    # root-coefficient tables use and which has no \begin{array} at all.
    runs = []
    for raw in _ROWSEP.split(latex or ""):
        row = raw.strip()
        if not row:
            continue
        r = [len(_NUM.findall(g)) for g in _RUN.findall(row)]
        if r:
            runs.append(r[0] if len(r) == 1 else max(r))
    return [runs] if len(runs) >= 2 else []


def numeric_rows(latex: str) -> list:
    """Flat per-row widths, kept for callers that want the old shape."""
    return [[w] for t in numeric_tables(latex) for w in t]


#: Single characters an OCR confuses with a digit. Deliberately NOT a general
#: "non-numeric cell" test: a matrix of \lambda or x_{1} entries is ordinary
#: mathematics, and flagging those would trade one false-positive class for
#: another. These are the shapes that mean a DIGIT was misread.
#: ONLY `l`. The first version also listed i, I, O, o, S, s, Z, z, B, g — and
#: reading its own output killed most of them: `i` is the imaginary unit and
#: `I` the identity matrix, so it fired on
#:     G^{-1} = 1/2 [ 0 & 1 & 1 & 0 \\ 0 & -i & i & 0 \\ ... ]
#: which is a complex matrix, not a misread digit. Every other letter in that
#: set is an ordinary mathematical symbol somewhere. `l` alone survives: a
#: standalone `l` cell is never mathematics, because that symbol is \ell.
_CONFUSABLE = {"l": "1"}
_BARE_CHAR = re.compile(r"^\s*(?:\$)?\s*([A-Za-z])\s*(?:\$)?\s*$")


def confusable_cells(latex: str) -> list:
    """Cells that are a lone letter inside an otherwise-numeric table.

    This is the defect the OLD width check caught BY ACCIDENT: an incidence
    matrix reading `0 & 0 & 1 & l & 0 & 0` came up one numeric cell short, so
    the row looked narrow. Parsing the table properly fixes the width count
    and would have LOST that detection — the row is six cells wide and
    perfectly uniform. So the real signal is named and kept, instead of being
    a side effect of a miscount.

    Requires >= 80% of the table's cells to be bare numbers, so a symbolic
    matrix never trips it.
    """
    found = []
    for ti, body in enumerate(_table_bodies(latex or ""), 1):
        rows = [r for r in _ROWSEP.split(body) if r.strip()]
        cells = [c for r in rows for c in r.split("&")]
        if len(cells) < 4:
            continue
        nums = sum(1 for c in cells if _CELL_NUM.match(c))
        if nums < 0.8 * len(cells):
            continue
        for ri, r in enumerate(rows, 1):
            for ci, c in enumerate(r.split("&"), 1):
                m = _BARE_CHAR.match(c)
                if m and m.group(1) in _CONFUSABLE:
                    found.append({"table": ti, "row": ri, "col": ci,
                                  "cell": m.group(1),
                                  "likely": _CONFUSABLE[m.group(1)]})
    return found


def check_uniform_widths(latex: str):
    """(ok, detail). Uniformity is checked WITHIN each table, not across the
    value — two matrices of different widths are two tables, both uniform."""
    tables = numeric_tables(latex)
    if not tables:
        return True, "no numeric table"
    bad = []
    for ti, widths in enumerate(tables, 1):
        if len(set(widths)) == 1:
            continue
        counts = {}
        for w in widths:
            counts[w] = counts.get(w, 0) + 1
        mode = max(counts, key=counts.get)
        rows = [i + 1 for i, w in enumerate(widths) if w != mode]
        bad.append(f"table {ti}: {len(widths)} rows, widths {counts} "
                   f"(modal {mode}), non-uniform at row(s) {rows}")
    if not bad:
        shape = ", ".join(f"{len(t)}x{t[0]}" for t in tables)
        return True, f"{len(tables)} table(s): {shape}"
    return False, "; ".join(bad)


def load(path: Path, validate: bool = True) -> list:
    """Proposals from a change-request file, each carrying its problems."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("proposals") or data.get("changes") or [data]
    out = []
    for i, raw in enumerate(data):
        missing = [k for k in ("target", "field", "proposed") if not raw.get(k)]
        p = Proposal(target=raw.get("target", f"<entry {i}>"),
                     field_name=raw.get("field", ""), proposed=raw.get("proposed", ""),
                     basis=raw.get("basis", ""), author=raw.get("author", ""),
                     at=raw.get("at", ""), rationale=raw.get("rationale", ""),
                     status=raw.get("status", "proposed"))
        if missing:
            p.problems.append(f"missing required field(s): {', '.join(missing)}")
        elif validate:
            ok, detail = check_uniform_widths(p.proposed)
            if not ok:
                p.problems.append(f"non-uniform numeric table row widths - {detail}")
        out.append(p)
    return out
