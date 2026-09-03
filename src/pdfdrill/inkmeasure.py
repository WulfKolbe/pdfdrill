r"""311/322 — produce inkdrill's report.compare.tsv ourselves.

`inkconvert` reads a TSV that only the peer inkdrill session used to produce,
so most documents have never been measured and their reports carry empty ink
columns with nothing explaining why.

Three facts govern which rows belong in that file, and 311c got two of them
wrong by reasoning instead of reading:

**Only the DISPLAY EQUATIONS table.** `inkconvert.identifiers` matches
`\ident{...EQ<digits>}` and nothing else, so formulas, tables and image
regions are not paired against and must not be measured.

**The legend rows STAY.** `inkconvert.read_tsv` separates one all-zero row per
page as the legend footer and counts display pages from them. Dropping them
here would leave the consumer with no footers to find and a row count short by
one per page. 311c dropped them.

**The table is selected by ORDINAL, not width.** A column count cannot pick a
table when two share one (320), and contiguity cannot separate two ADJACENT
tables of one width — 0049's equations and formulas are both 5 columns, so
inkdrill sees one 28-row run. `report.tables.json` (321) says it is 1 row then
27, and because the builder puts a `\clearpage` between sections, the split
falls on a page boundary and can be taken exactly.

pdfdrill CONSUMES inkdrill: it is a subprocess, never an import.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import regionink as ri

EQUATION_CAPTION = "Display equations"
TSV_HEADER = ("report_page", "line", "dis", "A_eq_B",
              "L_comp", "L_holes", "L_stk", "L_cen", "L_off",
              "R_comp", "R_holes", "R_stk", "R_cen", "R_off")


class MeasureRefused(RuntimeError):
    """The report cannot be measured, and saying so beats a wrong TSV."""


#: 557 — the findings shape has no "Display equations" table. Its equation
#: rows live in the four sections, and a measurement of the PUBLISHED report
#: has to segment those. Order matters: Corrected first because it is the
#: first section the builder emits, so the lattice's row order matches.
FINDINGS_CAPTIONS = ("Corrected", "Unresolved", "Flagged, not acted on",
                     "Doubted but correct")


def equations_table(doc_dir: Path) -> dict:
    """The builder's own record of the table whose rows are to be measured.

    321 named it "Display equations", which is the full listing's section.
    557 — a FINDINGS report has no such table: `report.tables.json` names
    Corrected / Unresolved / Flagged / Doubted instead, and refusing on that
    is what stopped the published shape being measurable at all. The sections
    are concatenated in emission order, so the run reads as one sequence of
    rows exactly as the lattice sees it.
    """
    f = Path(doc_dir) / "report.tables.json"
    if not f.is_file():
        return _from_tex(Path(doc_dir) / "report.tex")
    try:
        tables = json.loads(f.read_text(encoding="utf-8")).get("tables") or []
    except Exception as exc:
        raise MeasureRefused("report.tables.json unreadable: %s" % exc)
    for t in tables:
        if t.get("caption") == EQUATION_CAPTION:
            return t
    found = [t for cap in FINDINGS_CAPTIONS
             for t in tables if t.get("caption") == cap]
    if found:
        idents = [i for t in found for i in (t.get("identifiers") or [])]
        return {"caption": " + ".join(t["caption"] for t in found),
                "columns": found[0].get("columns"),
                "legend": any(t.get("legend") for t in found),
                "endhead": any(t.get("endhead") for t in found),
                "rows": sum(int(t.get("rows") or 0) for t in found),
                "identifiers": idents,
                "sections": [t["caption"] for t in found],
                "shape": "findings"}
    raise MeasureRefused(
        "report.tables.json names neither %r nor any findings section (%s) — "
        "it holds %r" % (EQUATION_CAPTION, ", ".join(FINDINGS_CAPTIONS),
                         [t.get("caption") for t in tables]))


def _from_tex(tex: Path) -> dict:
    r"""The equations table read back out of report.tex.

    A FALLBACK for the 1,222 reports built before the builder started stating
    its boundaries (321), so 322 does not have to rebuild the corpus first.
    It is derived rather than stated, and the two differ in what they can
    know: this reads the FIRST longtable and trusts that it is the equations
    table, which the builder's own record does not have to assume.
    """
    import re
    if not tex.is_file():
        raise MeasureRefused("no report.tables.json and no report.tex")
    lines = tex.read_text(encoding="utf-8", errors="replace").splitlines()
    start = next((i for i, l in enumerate(lines)
                  if r"\begin{longtable}" in l), None)
    if start is None:
        raise MeasureRefused("report.tex holds no longtable")
    end = next((i for i, l in enumerate(lines[start:], start)
                if r"\end{longtable}" in l), len(lines))
    body = lines[start:end]
    idents = [l for l in body if r"\ident{" in l and "EQ" in l]
    return {"caption": EQUATION_CAPTION, "columns": lines[start].count("p{"),
            "legend": any("multicolumn" in l for l in body),
            "endhead": any(r"\endhead" in l for l in body),
            "rows": len(idents), "identifiers": [], "derived_from": "report.tex"}


def _pages_for(rows_by_page: dict, pages: list, want: int, legend: bool):
    """The leading pages of a run that hold `want` data rows.

    The builder `\\clearpage`s between sections, so a table owns whole pages
    and the split is exact. A split landing mid-page means the premise is
    wrong, and this refuses rather than taking a prefix of a page.
    """
    got, take = 0, []
    for p in pages:
        n = len(rows_by_page.get(str(p), []))
        got += n - (1 if legend else 0)
        take.append(p)
        if got == want:
            return take
        if got > want:
            raise MeasureRefused(
                "the equations table does not end on a page boundary: %d rows "
                "after page %d against %d expected. The builder clearpages "
                "between sections, so this means the run is not the table."
                % (got, p, want))
    raise MeasureRefused(
        "run holds %d data rows, the manifest expects %d for the equations "
        "table" % (got, want))


def measure(report_pdf: Path, work: Path, timeout: int = 900) -> list:
    r"""Every Display-equations row of the report, legend rows included."""
    doc_dir = Path(report_pdf).parent
    t = equations_table(doc_dir)
    want, cols = t["rows"], t["columns"]
    header = "every" if t.get("endhead") else "first"
    if not want:
        return []
    work.mkdir(parents=True, exist_ok=True)
    sel = ri.reportpages_json(report_pdf, columns=cols, table=1,
                              header=header, timeout=timeout)
    runs = sel.get("tables") or []
    if not runs:
        raise MeasureRefused("inkdrill found no table in %s" % report_pdf.name)
    # ordinal 1 is the equations table on nearly every document; when the
    # first run is a different width, take the first run that matches.
    if runs[0]["columns"] != cols:
        cand = [r for r in runs if r["columns"] == cols]
        if not cand:
            raise MeasureRefused(
                "no run is %d columns wide; inkdrill saw %s"
                % (cols, [r["columns"] for r in runs]))
        sel = ri.reportpages_json(report_pdf, columns=cols,
                                  table=cand[0]["ordinal"], header=header,
                                  timeout=timeout)
    pages = _pages_for(sel.get("rows") or {}, sel.get("pages") or [],
                       want, bool(t.get("legend")))
    out = []
    for page in pages:
        a = ri._render(report_pdf, page, 300, work)
        b = ri._render(report_pdf, page, 600, work)
        if not (a.is_file() and b.is_file()):
            raise MeasureRefused("could not render page %d" % page)
        rows = ri.compare_page(a, b, page, timeout)
        # 388 — the rasters go now. A PGM is uncompressed, so a 400-page book
        # would leave 50 GB of intermediates for a TSV of a few kilobytes.
        for _f in (a, b):
            try:
                _f.unlink()
            except OSError:
                pass
        expect = len((sel.get("rows") or {}).get(str(page), []))
        if len(rows) == expect + 1:
            rows = rows[1:]                  # compare has no header rule
        if len(rows) != expect:
            raise MeasureRefused(
                "page %d: compare returned %d rows, reportpages expects %d"
                % (page, len(rows), expect))
        if t.get("legend") and rows:
            # THE FOOTER RECONCILIATION (322). One legend row per page, and it
            # is the LAST row: `legend_foot` emits the key as \endfoot and
            # \endlastfoot, so LaTeX sets it at the bottom of every page.
            #
            # It is dropped HERE rather than left for inkconvert, whose rule is
            # that a footer is all-zero in BOTH five-tuples. That holds only
            # for the 6-column table, where the last two columns are Rendered
            # and Scan and the legend fills neither. On a 5-column table they
            # are LaTeX source and Rendered, the legend's \multicolumn covers
            # the source cell, and the row measures L=[68,23,3,3,0] against
            # R=[0,0,0,0,0] -- not all-zero, so inkconvert would count it as an
            # equation and refuse the pairing. Measured on 0049.
            rows = rows[:-1]
        out.extend(rows)
    data = len(out)
    if data != want:
        raise MeasureRefused(
            "%d data rows measured against %d identifiers — the pairing would "
            "be unknown and inkconvert would refuse it anyway" % (data, want))
    return out


def distance(L: list, R: list) -> int:
    """L1 between the two five-tuples — inkdrill's `dis`, reproduced.

    `inkdrill compare` emits no distance; its third column is a label. This is
    the sum `inkconvert` recomputes, verified against inkdrill's own TSV:
    rows scoring 2, 5 and 12 there reproduce exactly.
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
