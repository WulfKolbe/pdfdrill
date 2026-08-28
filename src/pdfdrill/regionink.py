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
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]*)\|" + r"([^|]*)\|" * 12)
_INKDRILL_HOME = Path(os.environ.get("INKDRILL_HOME", Path.home() / "inkdrill"))


class RegionInkRefused(Exception):
    """The pairing cannot be established. No file is written."""


def inkdrill_available() -> bool:
    return (_INKDRILL_HOME / "inkdrill" / "__main__.py").is_file()


def table_pages(report_pdf: Path) -> list:
    """Report pages holding the image table — the section heading to the end.

    KNOWN LIMIT, and it is why `build` asserts rather than trusting this: a
    page carrying a SINGLE image row forms no detectable row lattice and
    `inkdrill compare` returns nothing for it. Measured on 0049 — page 3 holds
    5 rows and yields 4, page 4 holds 1 and yields 0, against a manifest of 6.
    The join then refuses, which is correct, but it means this driver does not
    yet reproduce what inkdrill's own `tools/reportcompare.py` does for the
    equation table: a 150 dpi probe, a leading contiguous run of pages whose
    lattice matches the column count, a coverage check and a sliver filter.
    That detection is inkdrill's, and reimplementing it here badly would
    produce quietly wrong rows instead of a refusal.
    """
    if shutil.which("pdftotext") is None:
        return []
    out = subprocess.run(["pdftotext", "-layout", str(report_pdf), "-"],
                         capture_output=True, text=True, timeout=600).stdout
    # pdftotext ends its output with a form feed, so the split yields a
    # trailing empty segment that is not a page.
    pages = [pg for pg in out.split("\f")]
    while pages and not pages[-1].strip():
        pages.pop()
    first = None
    for i, pg in enumerate(pages, 1):
        if "Image regions" in pg:
            first = i
            break
    if first is None:
        return []
    return list(range(first, len(pages) + 1))


def _render(report_pdf: Path, page: int, dpi: int, out: Path) -> Path:
    dst = out / f"p{page}_{dpi}.png"
    if dst.is_file():
        return dst
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m",
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
        rows.append({"page": int(cells[0]), "line": int(cells[1]),
                     "L": nums[:5], "R": nums[5:],
                     "a_eq_b": cells[13].strip().lower() in ("yes", "true", "1")})
    return rows


def measure(report_pdf: Path, work: Path, timeout: int = 900) -> list:
    """Every image-table row of the report, in printed order."""
    work.mkdir(parents=True, exist_ok=True)
    out = []
    for page in table_pages(report_pdf):
        a = _render(report_pdf, page, 300, work)
        b = _render(report_pdf, page, 600, work)
        if not (a.is_file() and b.is_file()):
            continue
        out.extend(compare_page(a, b, page, timeout))
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
