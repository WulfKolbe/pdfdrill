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
import re
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


#: 596 — identifier-shaped tokens, permissively. The MANIFEST decides which of
#: these is a row; this pattern only has to be wide enough not to miss one.
#: `_` is a word character, so `\w` already covers the bibkey.
_IDENT_TOKEN = re.compile(r"[A-Za-z0-9][\w.\-+]*_(?:EQ|FO|TAB|DIA|IMG|H)\d{2,}"
                          r"(?:\((?:was|now|basis)\))?")


def _flat(text: str) -> str:
    r"""Page text with every whitespace run removed.

    596 — `pdftotext` WRAPS. A long bibkey pushes the identifier past the
    column and it comes back split across two lines, so both the plain and the
    `-layout` output match nothing at all. Removing whitespace entirely makes
    the wrap invisible, and the identifiers carry no spaces of their own —
    except the ` (was)` suffix, which is why `_key` strips them from the
    manifest side too.
    """
    return re.sub(r"\s+", "", text)


def _key(ident: str) -> str:
    """The manifest identifier in the same shape `_flat` leaves the page in."""
    return re.sub(r"\s+", "", str(ident))


def rows_manifest(doc_dir: Path) -> dict:
    """611 — `pdfdrill-rows.json`, refused when it names another build.

    The manifest records the sha256 of the report.pdf it describes (607B). A
    manifest for a build that no longer exists would pair rows against
    rectangles measured somewhere else, which is the whole class this chain
    keeps finding.
    """
    import hashlib
    f = Path(doc_dir) / "pdfdrill-rows.json"
    if not f.is_file():
        raise MeasureRefused("no pdfdrill-rows.json — the report was built "
                             "without --cellrect, so no row has a rectangle")
    try:
        R = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MeasureRefused("pdfdrill-rows.json unreadable: %s" % exc)
    pdf = Path(doc_dir) / "report.pdf"
    want = ((R.get("measured_against") or {}).get("sha256") or "")
    if pdf.is_file() and want:
        got = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if got != want:
            raise MeasureRefused(
                "pdfdrill-rows.json describes report.pdf %s and the file on "
                "disk is %s — it is a manifest for a build that no longer "
                "exists" % (want[:12], got[:12]))
    return R


def pair_rows(lattice: list, manifest: dict, page: int, dpi: int = 300) -> dict:
    r"""611 — one lattice row to the identifier whose rect CONTAINS it.

    The manifest gives each row the rules that bound it, in bp with y running
    UP from the page bottom; `compare_page` gives each lattice row a y-extent
    in raster pixels running DOWN from the top. Both are converted to pixels
    from the top and a lattice row is claimed by the identifier whose band
    contains its centre.

    Containment, not counting. 604 measured why: page 4 of 0707.4470 had
    three identifiers and three lattice rows that were still not the same
    three, because one row was a repeated header and one identifier's row was
    elsewhere. No count correction can fix a mispairing, and a header row is
    dropped here because nothing claims it — not by a rule that recognises
    headers.

    Returns {"paired": [(row, identifier)], "unpaired": [row],
             "unclaimed_identifiers": [identifier]}.
    """
    H = float(manifest.get("page_height_bp") or 0.0)
    k = dpi / 72.0

    def to_px(y_bp):
        return (H - float(y_bp)) * k

    bands = []
    for r in manifest.get("rows") or []:
        if r.get("rule_above_bp") is None or r.get("page") != page:
            continue
        if not r.get("rules_on_one_page", True):
            continue          # a row broken across pages bounds no rectangle
        top, bot = to_px(r["rule_above_bp"]), to_px(r["rule_below_bp"])
        bands.append((min(top, bot), max(top, bot), r["identifier"]))
    bands.sort()
    paired, unpaired, claimed = [], [], set()
    for row in lattice:
        y0, y1 = row.get("row_y0"), row.get("row_y1")
        if y0 is None or y1 is None:
            unpaired.append(row)
            continue
        mid = (y0 + y1) / 2.0
        hit = next((i for t, b, i in bands if t <= mid <= b), None)
        if hit is None:
            unpaired.append(row)
        else:
            paired.append((row, hit))
            claimed.add(hit)
    return {"paired": paired, "unpaired": unpaired,
            "unclaimed_identifiers": [i for _, _, i in bands
                                      if i not in claimed]}


def identifier_pages(pdf: Path, wanted: list, timeout: int = 900) -> dict:
    r"""Where each manifest identifier appears, and what else looks like one.

    596 — ATTRIBUTION IS PER IDENTIFIER, NEVER PER RUN. inkdrill established
    that neither ordinal nor column count can name a table: a run can hold
    several tables (two adjacent 5-column tables are one run), a table can
    span runs of different widths (one 212-row table crosses a 6-column and a
    5-column run), 608 of 717 documents share a column count between two
    tables, and one 6-column table sits in a run the lattice reads as 7.

    So the table is not selected at all. Every identifier the manifest names
    is located in the PDF's own text layer, and the rows follow.

    Returns {"pages": [page, ...] in manifest order,
             "by_page": {page: [identifier, ...] in MANIFEST order},
             "missing": [identifier, ...] the text layer does not carry,
             "leftover": [token, ...] identifier-shaped and not in the
                         manifest — printed rather than dropped}.
    """
    import subprocess
    n = int(re.search(r"^Pages:\s+(\d+)",
                      subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                     text=True).stdout, re.M).group(1))
    want_keys = [_key(i) for i in wanted]
    want_set = set(want_keys)
    flat_by_page, leftover = {}, []
    for pg in range(1, n + 1):
        # 596 — `-raw` returns the text in CONTENT order rather than the
        # lattice's reading order. The order we use comes from the manifest
        # either way, but -raw is the only mode whose tokens survive the wrap.
        txt = subprocess.run(["pdftotext", "-raw", "-f", str(pg), "-l", str(pg),
                              str(pdf), "-"], capture_output=True, text=True,
                             errors="replace", timeout=timeout).stdout
        flat_by_page[pg] = _flat(txt)
        # Leftovers are scanned on the RAW text, not the flattened one: with
        # every space removed, neighbouring words glue onto the token and the
        # pattern reports `...ScanimageX_EQ0051021` as a stray identifier.
        # A wrapped non-manifest identifier is therefore invisible here, which
        # is the honest trade — the manifest hits are found either way.
        for m in _IDENT_TOKEN.finditer(txt):
            tok = m.group(0)
            if _key(tok) not in want_set and tok not in leftover:
                leftover.append(tok)

    by_page, missing, order = {}, [], []
    for ident, key in zip(wanted, want_keys):
        hit = next((pg for pg in range(1, n + 1) if key in flat_by_page[pg]), None)
        if hit is None:
            missing.append(ident)
            continue
        by_page.setdefault(hit, []).append(ident)   # manifest order, by append
        if hit not in order:
            order.append(hit)
    return {"pages": order, "by_page": by_page,
            "missing": missing, "leftover": leftover}


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

    # 596 — THE IDENTIFIER JOIN REPLACES ORDINAL SELECTION.
    #
    # This used to ask inkdrill for table=1, check that its column count
    # matched, and then hunt `want` rows inside that one run. 594 measured
    # what that costs on a full listing: the 18-page report of 2501.06662
    # segments into NINE runs broken by column width, the Display-equations
    # rows are spread over ordinals 1, 5 and 7, and the search found 3 rows
    # where the manifest named 60. Ordinal and width are both unusable —
    # a run can hold several tables and a table can span runs of different
    # widths — so the table is no longer selected. Each identifier is located.
    idents = list(t.get("identifiers") or [])
    if not idents:
        raise MeasureRefused(
            "the manifest names %d rows but no identifiers, so nothing can be "
            "joined. Rebuild the report: report.tables.json predates 596."
            % want)

    # 613 — POSITIONAL SELECTION. The rect manifest gives every row the rules
    # that bound it, so a lattice row is claimed by the identifier whose band
    # contains it. There is no header rule and no legend rule: a header row
    # is dropped because nothing claims it. 604 measured why counting cannot
    # work — page 4 of 0707.4470 had three identifiers and three lattice rows
    # that were still not the same three.
    M = rows_manifest(Path(report_pdf).parent)
    want_ids = set(idents)
    bands = [r for r in (M.get("rows") or [])
             if r.get("identifier") in want_ids
             and r.get("rule_above_bp") is not None
             and r.get("rules_on_one_page", True)]
    # 613 — A ROW BROKEN ACROSS A PAGE BOUNDS NO RECTANGLE on either page,
    # so it cannot be claimed positionally. That is a REAL GAP and it is
    # reported by name rather than either refusing the document for it or
    # dropping it silently: on 2501.06662 ten of sixty display equations
    # straddle a page break.
    straddle = {r["identifier"] for r in (M.get("rows") or [])
                if r.get("identifier") in want_ids
                and not r.get("rules_on_one_page", True)}
    have = {r["identifier"] for r in bands}
    missing = want_ids - have - straddle
    if missing:
        raise MeasureRefused(
            "%d of %d identifiers in the %s table have no rectangle and do "
            "not straddle a page (%s%s) — the manifest and the report "
            "disagree about what is in it"
            % (len(missing), len(want_ids), t.get("caption"),
               ", ".join(sorted(missing)[:4]),
               " …" if len(missing) > 4 else ""))
    order = {ident: n for n, ident in enumerate(idents)}
    pages = sorted({r["page"] for r in bands})
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
        res = pair_rows(rows, M, page, dpi=300)
        keep = [(r, i) for r, i in res["paired"] if i in want_ids]
        if not keep and res["unpaired"]:
            raise MeasureRefused(
                "page %d: %d lattice row(s) and none claimed by an identifier "
                "of the %s table" % (page, len(res["unpaired"]),
                                     t.get("caption")))
        for r, ident in keep:
            r["identifier"] = ident
        out.extend(keep)
    # manifest order, not page order: the two agree today and the manifest is
    # the record the pairing was made against.
    out.sort(key=lambda ri_: order.get(ri_[1], 1 << 30))
    out = [r for r, _ in out]
    data = len(out)
    want = want - len(straddle)      # 613 — the straddling rows are not measurable
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
