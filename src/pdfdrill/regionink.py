"""
284 — measure the two image columns with inkdrill, per region.

The report's image table ends with the two cells that matter: Rendered and
Scan. `inkdrill compare a b` reads a rendered page, finds the table lattice and
compares its LAST TWO columns by default — which is why they are last.

pdfdrill CONSUMES inkdrill, it never imports it: inkdrill is invoked as a
subprocess and its markdown table parsed, the same relationship `inkconvert`
has with `report.compare.tsv`.

The result goes to `report.regions.ink.json`, BESIDE `report.ink.json` and not
inside it. The two are different populations: the equation measurement compares
a rendered formula against its scan, while a region row whose LaTeX is missing
compares the scan against ITSELF. Merging them would put self-comparisons into
a distribution read as agreement between two sources — so every record carries
`duplicated`, taken from the build's own manifest rather than inferred from the
pixels.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .report_tex import REGIONS_INK, REGIONS_MANIFEST
from .inkconvert import flag_of, FLAG_CODE, NOISE_DISTANCE, NOISE_COMP_DELTA

#: inkdrill's markdown row: | page | line | label | L×5 | R×5 | A=B | B stable |…
#: 611 — inkdrill's compare gained `row h`, `row y0`, `row y1` (606), so the
#: table is 20 columns where it was 15. The trailing three are OPTIONAL here:
#: an older inkdrill returns 15 and its rows simply carry no y-extent.
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]*)\|"
                  + r"([^|]*)\|" * 14
                  + r"(?:([^|]*)\|([^|]*)\|([^|]*)\|)?")
_INKDRILL_HOME = Path(os.environ.get("INKDRILL_HOME", Path.home() / "inkdrill"))


class RegionInkRefused(Exception):
    """The pairing cannot be established. No file is written."""


def inkdrill_available() -> bool:
    return (_INKDRILL_HOME / "inkdrill" / "__main__.py").is_file()


#: inkdrill's page detection, as a subprocess (286). It carries the 150 dpi
#: probe, the contiguous-run selection, the coverage check and the sliver
#: filter, and since their 285ec9a it picks the table as the LARGEST region
#: rather than the holliest — which is what fixed both the 6-vs-5 column
#: disagreement and the single-row page.
REPORTPAGES = _INKDRILL_HOME / "tools" / "reportpages.py"
#: The region table's column count, from OUR source. Never guessed here, and
#: never inferred from the lattice: `reportpages` takes it as an argument
#: precisely so the two views of the table can be compared rather than
#: conflated.
REGION_COLUMNS = 6


def reportpages_json(report_pdf: Path, columns: int, table: int | None = None,
                     header: str = "first", timeout: int = 1800) -> dict:
    """inkdrill's page/row detection, whole. Subprocess, never an import.

    322 — `--table N` selects by ORDINAL because a column count cannot pick a
    table when two share one. inkdrill cross-checks the two and reports a
    disagreement rather than reconciling it, so a wrong column count returns
    no rows and says why instead of measuring the wrong table.
    """
    if not REPORTPAGES.is_file():
        raise RegionInkRefused(
            "inkdrill's tools/reportpages.py not found at %s" % REPORTPAGES)
    cmd = ["python3", str(REPORTPAGES), "--pdf", str(report_pdf),
           "--columns", str(columns), "--header", header]
    if table is not None:
        cmd += ["--table", str(table)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        d = json.loads(p.stdout)
    except Exception:
        raise RegionInkRefused(
            "reportpages emitted no JSON for %s (rc=%d): %s"
            % (report_pdf.name, p.returncode, (p.stderr or p.stdout)[:200]))
    if d.get("mismatch"):
        raise RegionInkRefused("reportpages: %s" % d["mismatch"])
    return d


def detect_pages(report_pdf: Path, columns: int = REGION_COLUMNS,
                 timeout: int = 1800, header: str = "first") -> dict:
    r"""{page: expected row count} for the region table, from inkdrill.

    `--header first`: our region table prints its header ONCE, not per page.
    reportcompare's own rule is to skip row 0 on EVERY page, which is right for
    the equation table (\endhead repeats it) and would eat a DATA row from
    every page after the first here. inkdrill exposed it as a flag rather than
    a constant because of that difference.
    """
    if not REPORTPAGES.is_file():
        raise RegionInkRefused(
            "inkdrill's tools/reportpages.py not found at %s — 286's entry "
            "point is what carries the page detection, and guessing it here is "
            "what produced a short join before." % REPORTPAGES)
    # `header` is a PARAMETER, not a constant: the image table prints its
    # header once (`first`) and the equation table repeats it via \endhead
    # (`every`). The default stays `first`, so this module's own behaviour is
    # unchanged; 311 passes `every`.
    p = subprocess.run(["python3", str(REPORTPAGES), "--pdf", str(report_pdf),
                        "--columns", str(columns), "--header", header],
                       capture_output=True, text=True, timeout=timeout)
    try:
        d = json.loads(p.stdout)
    except Exception:
        raise RegionInkRefused(
            "reportpages emitted no JSON for %s (rc=%d): %s"
            % (report_pdf.name, p.returncode, (p.stderr or p.stdout)[:200]))
    rows = d.get("rows") or {}
    out = {int(k): len(v) for k, v in rows.items()}
    if not out:
        raise RegionInkRefused(
            "reportpages found no %d-column table in %s. Census of what it did "
            "see: %s — a column count that disagrees with our source is a real "
            "difference between the two views of the table, not a miss."
            % (columns, report_pdf.name, d.get("census")))
    return out


def _render(report_pdf: Path, page: int, dpi: int, out: Path) -> Path:
    """388 — pgmraw, not png16m.

    inkdrill decodes PNG in pure Python at ~0.7 s per megapixel; an A3 report
    page at 600 dpi is 69.6 Mpx, so the decode alone was 44 s and 93% of the
    cost of measuring a page. PGM is a header parse and a table lookup, 0.002
    s/Mpx. Measured end to end on one page through the real subprocess:
    60.65 s -> 4.6 s. The masks are byte-identical, which is asserted in
    inkdrill's tests/test_pnm_stream.py and was re-checked on this corpus
    before either caller was switched.

    The trade is size — the same page is 0.4 MB as PNG and 66 MB as PGM — so
    the caller deletes each pair as soon as its compare has run. Re-rendering
    costs 0.3 s, which is less than decoding the PNG it replaces.
    """
    dst = out / f"p{page}_{dpi}.pgm"
    if dst.is_file():
        return dst
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pgmraw",
                    f"-r{dpi}", f"-dFirstPage={page}", f"-dLastPage={page}",
                    f"-sOutputFile={dst.name}", str(report_pdf)],
                   cwd=out, capture_output=True, timeout=900)
    return dst


def compare_page(a: Path, b: Path, page: int, timeout: int = 900) -> list:
    """`inkdrill compare` on one page -> [{L, R, a_eq_b}, …] in row order."""
    env = dict(os.environ, PYTHONPATH=str(_INKDRILL_HOME))
    p = subprocess.run(["python3", "-m", "inkdrill", "compare", a.name, b.name,
                        "--page-number", str(page)],
                       cwd=a.parent, capture_output=True, text=True,
                       env=env, timeout=timeout)
    rows = []
    for line in p.stdout.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.groups()]
        if cells[2].strip().lower().startswith("---"):
            continue
        try:
            nums = [int(x) for x in cells[3:13]]
        except ValueError:
            continue                     # the header separator, or a blank row
        try:
            dis = int(cells[2])
        except ValueError:
            dis = 0                  # a non-numeric distance cell
        rec = {"page": int(cells[0]), "line": int(cells[1]),
               "dis": dis,
               "L": nums[:5], "R": nums[5:],
               "a_eq_b": cells[13].strip().lower() in ("yes", "true", "1")}
        # columns 18 and 19: the row's y-extent in raster px, top-down.
        try:
            rec["row_y0"] = int(cells[18])
            rec["row_y1"] = int(cells[19])
        except (IndexError, TypeError, ValueError):
            rec["row_y0"] = rec["row_y1"] = None
        rows.append(rec)
    return rows


def measure(report_pdf: Path, work: Path, timeout: int = 900) -> list:
    """Every image-table row of the report, in printed order.

    Two tools, one job each: inkdrill's `reportpages` says WHICH pages and HOW
    MANY rows (it owns the lattice), `inkdrill compare` says what the two
    columns measure. The counts are reconciled per page rather than trusted —
    `compare` has no header rule, so on the page carrying the once-printed
    header it returns one row more than `reportpages` does, and that row is
    dropped explicitly and only when the arithmetic says so.
    """
    work.mkdir(parents=True, exist_ok=True)
    expected = detect_pages(report_pdf)
    out = []
    for page in sorted(expected):
        want = expected[page]
        a = _render(report_pdf, page, 300, work)
        b = _render(report_pdf, page, 600, work)
        if not (a.is_file() and b.is_file()):
            raise RegionInkRefused("could not render page %d of %s"
                                   % (page, report_pdf.name))
        rows = compare_page(a, b, page, timeout)
        if len(rows) == want + 1:
            rows = rows[1:]                       # the once-printed header
        if len(rows) != want:
            raise RegionInkRefused(
                "page %d: inkdrill compare returned %d rows, reportpages "
                "expects %d. The two disagree about the same page, and zipping "
                "them would put every later identifier on the wrong row."
                % (page, len(rows), want))
        out.extend(rows)
    return out


def build(rows: list, manifest: list, stamp: dict | None = None) -> dict:
    """Join the measurement to the manifest and classify.

    The join is POSITIONAL — inkdrill reports a lattice row, not an identifier —
    so the count is ASSERTED, exactly as `inkconvert` asserts its own. A
    mismatch refuses rather than zipping: zip() would drop the tail silently and
    produce a file that passes every structural check.
    """
    if len(rows) != len(manifest):
        raise RegionInkRefused(
            "%d measured rows against %d manifest rows — the pairing is "
            "unknown. The manifest is written by the build in printed order; a "
            "difference means the report was rebuilt after it was measured."
            % (len(rows), len(manifest)))
    recs = []
    for r, m in zip(rows, manifest):
        L, R = r["L"], r["R"]
        distance = sum(abs(x - y) for x, y in zip(L, R))
        signed = R[0] - L[0]
        flag = flag_of(distance, abs(signed), r["a_eq_b"])
        recs.append({
            "id": m["id"], "page": m["page"],
            "report_page": r["page"], "line": r["line"],
            "rendered_source": m["rendered_source"],
            "scan_source": m["scan_source"],
            # A duplicated row measured the scan against ITSELF. Its distance
            # is a floor, not agreement between two sources, and nothing
            # downstream may average the two together.
            "duplicated": bool(m["duplicated"]),
            "has_latex": bool(m.get("has_latex")),
            "L": L, "R": R,
            "distance": distance, "comp_delta": abs(signed),
            "signed_delta": signed,
            "flag": flag, "code": "%s|%+d" % (FLAG_CODE[flag], signed),
        })
    payload = {"rows": recs,
               "noise_distance": NOISE_DISTANCE,
               "noise_comp_delta": NOISE_COMP_DELTA,
               "duplicated_rows": sum(1 for r in recs if r["duplicated"]),
               "measured_rows": sum(1 for r in recs if not r["duplicated"]),
               "source": "inkdrill compare (last two columns)"}
    if stamp:
        payload["measured_against"] = stamp
    return payload
