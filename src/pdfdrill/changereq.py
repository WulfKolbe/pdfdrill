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


def numeric_rows(latex: str) -> list:
    """Per row, the widths of every numeric group it contains.

    Returns [] for a proposal with no numeric table, which is NOT a failure —
    most proposals are not tables and must pass untouched.
    """
    out = []
    for raw in _ROWSEP.split(latex or ""):
        row = raw.strip()
        if not row:
            continue
        runs = [len(_NUM.findall(g)) for g in _RUN.findall(row)]
        if runs:
            out.append(runs)
            continue
        # array form: count cells that are purely numeric, but only when the
        # row is mostly numeric — a single "& 2 &" inside prose is not a table
        cells = row.split("&")
        nums = sum(1 for c in cells if _CELL_NUM.match(c))
        if nums >= 2 and nums >= len(cells) - 2:
            out.append([nums])
    return out


def check_uniform_widths(latex: str):
    """(ok, detail). detail names the widths seen and the offending rows."""
    rows = numeric_rows(latex)
    if not rows:
        return True, "no numeric table"
    widths = sorted({w for r in rows for w in r})
    if len(widths) == 1:
        return True, f"{len(rows)} rows, width {widths[0]}"
    counts = {}
    for r in rows:
        for w in r:
            counts[w] = counts.get(w, 0) + 1
    mode = max(counts, key=counts.get)
    bad = [i + 1 for i, r in enumerate(rows) if any(w != mode for w in r)]
    return False, (f"{len(rows)} rows; widths {counts} (modal {mode}); "
                   f"non-uniform at row(s) {bad}")


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
