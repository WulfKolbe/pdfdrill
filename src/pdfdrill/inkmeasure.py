r"""311 — produce inkdrill's report.compare.tsv ourselves.

`inkconvert` reads a TSV that, until now, only the peer inkdrill session
produced ("the inkdrill harness writes per-doc report.compare.tsv into each
library folder when its run completes", HANDOVER-RULES). 982 of 1,350 documents
have never been measured, so their reports carry empty ink columns and nothing
explains why.

The measurement itself is not secret: it is the same shape `regionink` already
runs for the IMAGE table, pointed at the EQUATION table instead. Two arguments
differ and both matter:

  columns=5   the equation table's own width, from our source. regionink uses
              6 for the image table. Guessing it is how a 5-column lattice was
              read as 6 and every identifier after the first page shifted.
  header=every  the equation table repeats its header via \endhead, so row 0 of
              EVERY page is a header. The image table prints its header once,
              which is why regionink passes `first`. Getting this backwards
              drops one data row per page, silently.

pdfdrill CONSUMES inkdrill: it is a subprocess, never an import.
"""

from __future__ import annotations

from pathlib import Path

from . import regionink as ri

#: Fallback only. The equation table's width is NOT a constant: ink adoption
#: adds a residual column, so the same report is 5 wide without ink and 6 with
#: it. Hardcoding 5 made `reportpages` return no pages at all on an adopted
#: report while its census plainly showed the table — the guess this module's
#: own docstring warns against, made two functions below the warning.
EQUATION_COLUMNS_FALLBACK = 5


def equation_columns(report_tex: Path) -> int:
    r"""The equation table's declared width, from the report's own preamble.

    `report_tex` writes the equation/formula table FIRST and closes with the
    image-region table, so the first `\begin{longtable}` is the one to measure.
    Counting `p{` on that line is exact: every column in these preambles is a
    `p{..mm}`, and `|` decorations carry none.
    """
    try:
        text = Path(report_tex).read_text(errors="replace")
    except OSError:
        return EQUATION_COLUMNS_FALLBACK
    for line in text.splitlines():
        if r"\begin{longtable}" in line:
            n = line.count("p{")
            return n or EQUATION_COLUMNS_FALLBACK
    return EQUATION_COLUMNS_FALLBACK
#: inkdrill's TSV column order, which `inkconvert` parses.
TSV_HEADER = ("report_page", "line", "dis", "A_eq_B",
              "L_comp", "L_holes", "L_stk", "L_cen", "L_off",
              "R_comp", "R_holes", "R_stk", "R_cen", "R_off")


class MeasureRefused(RuntimeError):
    """The report cannot be measured, and saying so beats writing a wrong TSV."""


def measure(report_pdf: Path, work: Path, timeout: int = 900,
            columns: int | None = None) -> list:
    r"""Every equation-table row of the report, in printed order.

    `inkdrill compare` has no header flag, so it returns the header row as
    data. `reportpages --header every` does drop it. With `every` the header
    repeats on EVERY page, so compare comes back exactly one row long per page
    — the same reconciliation 293 made for the image table, where the header
    prints once and only the first page was over by one.

    The drop is explicit and only when the arithmetic says so. Any other
    disagreement refuses: writing a TSV from two disagreeing views would put
    every later identifier on the wrong row, which is the failure that produces
    a file rather than an error.
    """
    work.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = equation_columns(report_pdf.with_suffix(".tex"))
    expected = ri.detect_pages(report_pdf, columns=columns,
                               header="every", timeout=timeout)
    out = []
    for page in sorted(expected):
        want = expected[page]
        a = ri._render(report_pdf, page, 300, work)
        b = ri._render(report_pdf, page, 600, work)
        if not (a.is_file() and b.is_file()):
            raise MeasureRefused("could not render page %d of %s"
                                 % (page, report_pdf.name))
        rows = ri.compare_page(a, b, page, timeout)
        if len(rows) == want + 1:
            rows = rows[1:]                       # the per-page header row
        if len(rows) != want:
            raise MeasureRefused(
                "page %d: inkdrill compare returned %d rows, reportpages "
                "expects %d. Writing a TSV from two disagreeing views would "
                "put every later identifier on the wrong row."
                % (page, len(rows), want))
        out.extend(rows)
    return out


def distance(L: list, R: list) -> int:
    """L1 between the two five-tuples — inkdrill's `dis` column, reproduced.

    `inkdrill compare` does NOT emit a distance; its third column is a label.
    The distance is derived, and this is the same sum `inkconvert.rows` computes
    from L and R, verified against inkdrill's own TSV: rows scoring 2, 5 and 12
    there reproduce exactly here. Writing a placeholder 0 instead would have
    been harmless to the conversion — inkconvert recomputes it — and a
    fabricated number in a file that claims to be a measurement.
    """
    return sum(abs(a - b) for a, b in zip(L, R))


def to_tsv(rows: list) -> str:
    """inkdrill's exact TSV shape, because `inkconvert` already parses it."""
    lines = ["\t".join(TSV_HEADER)]
    for r in rows:
        lines.append("\t".join(str(x) for x in (
            r["page"], r["line"], distance(r["L"], r["R"]),
            "YES" if r["a_eq_b"] else "NO",
            *r["L"], *r["R"])))
    return "\n".join(lines) + "\n"
