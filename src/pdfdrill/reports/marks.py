"""672 — draw inkdrill's formula marks onto a COPY of the crop.

inkdrill measures ink against pdfdrill's own formula HOST LINES and hands
back, per document, `~/inkdrill-marks/<bibkey>/marks.json`: one row per
formula, a rectangle (`rect`, full-size MathPix pixels relative to the
host region's top-left; `rect_frac`, the same rectangle as fractions of
the region — scale-independent) when their policy decided the position is
unambiguous, `mark: false` and a reason otherwise (out/658's policy; do
not try to raise the marked fraction — see ~/inkdrill-marks/README.md).

WHERE THE MARKED IMAGE MAY NOT LIVE. `report-crops/<title>.jpg` is an
IDENTITY: `report_tex.crop_sha256`/`reports.gate.crop_gate` (667) hash that
exact file to answer "is the crop a reader sees the crop the ink measured",
and 655's budget ladder (`reports.budget.choose_rung`) predicts re-encoded
bytes from it too — both arguments rest on the file never being
overwritten. `report_tex.scale_crops` already keeps this rule (655's
scaled copies go to the separate `report-crops-b/`); this module keeps it
the same way, into a THIRD directory (`MARKS_DIR`) that neither `crop_gate`
nor `choose_rung` ever reads. In THIS task the two populations do not even
overlap: `crop_gate` walks `report.ink.json`'s rows, which are Equation
rows (`_EQ...`, ink-measured against `report.pdf`); this module only ever
touches Formula rows (`_FO...`, inline formulas' host-line crops) — the
kind `evidence-formula.pdf` shows. So crop_gate's comparison is UNCHANGED
by this task, in file identity and in the population it walks; it keeps
answering the question it always has ("is the ink-measured Equation crop
still the one on disk"), which stays the right question — a marked
Formula crop is a PRESENTATION derivative recomputed fresh every build
from the untouched `report-crops/`/`report-crops-b/` source (never cached
across builds the way a stale `crop_sha256` would need catching), and its
own correctness is enforced at draw time by the two checks below, not by
a persisted hash a later build could drift from.

Two checks per row, BEFORE drawing, refused (never silently skipped) when
either fails:

  * `region` and `host_page` must equal OUR OWN host line for that row —
    inkdrill's own docstring: "a consumer MUST compare it with its own
    host line and draw nothing on a mismatch: a rectangle is meaningless
    on another line."
  * `math` must equal the row's current reading, taken through the SAME
    transform `evidence-formula.tex`'s Rendered cell uses
    (`report_tex.display_safe`) — that transform is what inkdrill's own
    `math` field was parsed back OUT of (`tools/formulafind.py:rows`,
    the `\\FitMath{$\\displaystyle ...$}` group), not the raw `latex`.

Model-agnostic, like every module in this package except `from_document.py`
(that package's one rule): this reads `FormulaRow` objects and files on
disk, never a `docmodel.core.Document`.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import report_tex as rt
from .rows import FormulaRow

#: A DERIVED, disposable annotation layer — never `crops.CROPS_DIR`
#: ("report-crops") or `crops.CROPS_DIR_B` ("report-crops-b"), both of
#: which 667/655 depend on staying byte-identical to what was measured/
#: budgeted. Regenerated every time `apply()` runs; nothing else reads it.
MARKS_DIR = "report-crops-marks"

#: A visible red, distinct from a crop's own black ink and MathPix's own
#: red-ish flags elsewhere in this project's LaTeX (`_INK_COLOUR`), chosen
#: for contrast against a JPEG scan, not reused from there — those are
#: colour NAMES for a LaTeX macro, not RGB triples for a raster draw.
LINE_RGB = (220, 20, 20)

#: 672 — the outline must survive downsampling to the 655 floor (scale
#: 0.42, ~105 dpi of MathPix's own ~250) and stay VISIBLE without
#: obscuring the glyphs it points at: an outline (never filled), width
#: proportional to the image's own short side so it neither vanishes at
#: the floor nor overwhelms a small crop, floored at 2px so it is never
#: sub-pixel. Verified by rendering, not by this arithmetic alone — see
#: out/672.txt.
_MIN_LINE_PX = 2
_LINE_FRACTION = 0.018

_REGION_KEYS = ("top_left_x", "top_left_y", "width", "height")


def load(path: "Path | str") -> dict:
    """The marks file for one document, verbatim. Raises on a missing or
    unparsable file — a `--marks` path the caller named explicitly is an
    operator claim about what exists; masking a bad one here would be
    exactly the silent-skip HANDOVER-RULES rule 11 warns against."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _region_matches(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in _REGION_KEYS)


def check_row(row: FormulaRow, mark_row: dict) -> "str | None":
    """None when both checks pass; otherwise the refusal reason (a stable
    short phrase — the caller tallies these VERBATIM, so wording here is
    what ends up counted and reported)."""
    host = row.host_line
    if host is None or host.page is None or not host.region:
        return "our own row carries no host line to compare"
    if host.page != mark_row.get("host_page") or \
            not _region_matches(host.region, mark_row.get("region") or {}):
        return "host line differs from ours (region/host_page mismatch)"
    want = rt.display_safe(row.latex) if row.latex else ""
    got = mark_row.get("math")
    if want != (got or ""):
        return "reading differs from the marks file (math mismatch)"
    return None


def _draw(src: Path, dst: Path, rect_frac) -> bool:
    """One outline rectangle, `rect_frac` = (x0, y0, x1, y1) as FRACTIONS
    of the image — the same rectangle regardless of which resolution `src`
    happens to be at (full-size `report-crops/` or an already-scaled
    `report-crops-b/` copy), so one code path handles both sizes rather
    than a scale-specific branch. Never mutates `src`; returns False on
    any failure (no PIL, unreadable/corrupt image) so the caller counts a
    refusal instead of raising mid-build."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    try:
        im = Image.open(src).convert("RGB")
    except Exception:
        return False
    w, h = im.size
    x0, y0, x1, y1 = rect_frac
    box = [x0 * w, y0 * h, x1 * w, y1 * h]
    box = [min(box[0], box[2]), min(box[1], box[3]),
           max(box[0], box[2]), max(box[1], box[3])]
    lw = max(_MIN_LINE_PX, round(min(w, h) * _LINE_FRACTION))
    ImageDraw.Draw(im).rectangle(box, outline=LINE_RGB, width=lw)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=92)
    return True


def _empty_counts(n_rows: int) -> dict:
    return {"rows": n_rows, "marked_in_file": None, "checked": 0,
            "drawn": 0, "refused": {}}


def apply(rows: dict, marks_path: "Path | str | None", doc_dir: "Path | str"):
    """Formula rows only; every other kind passes through untouched.

    Off by construction when `marks_path` is falsy — returns `rows`
    UNCHANGED (the same dict, not a copy) so a document with no marks file
    builds byte-identical to before this module existed (672's own
    required proof; see tests/test_reports_marks.py and out/672.txt).

    Otherwise returns a NEW `{kind: [rows]}` — every kind but `formula`
    is the caller's own list object, reused; `formula` is a new list
    whose drawn rows are `dataclasses.replace(row, crop=<marked file>)`
    and whose every other row (no entry in the file, `mark: false`,
    refused, or undrawable) is the SAME row object `ensure_crops` already
    gave it, crop unmoved.

    `counts` (always the same shape, so a caller need not branch on
    whether marking ran): `rows` (this document's own formula-row count),
    `marked_in_file` (the marks file's own `counts.marked`, or `None` when
    off or the file refuses the whole document), `checked` (rows this
    module actually ran the two checks against), `drawn`, and `refused`
    ({reason: count}) — a silent skip here would be indistinguishable
    from a mark that was never offered (the brief's own words), so every
    row that does not get drawn is accounted for under exactly one of
    "not in the file", "not marked in the file", a `check_row` reason, or
    "could not draw (no PIL or unreadable crop)".
    """
    formula = rows.get("formula") or ()
    counts = _empty_counts(len(formula))
    if not marks_path:
        return rows, counts

    def _refuse(reason, n=1):
        counts["refused"][reason] = counts["refused"].get(reason, 0) + n

    data = load(marks_path)
    counts["marked_in_file"] = (data.get("counts") or {}).get("marked")
    if data.get("refused"):
        reason = "marks file refuses the whole document: %s" % data["refused"]
        _refuse(reason, len(formula))
        return rows, counts

    doc_dir = Path(doc_dir)
    by_id = {r["id"]: r for r in (data.get("rows") or [])}
    out_formula = []
    for row in formula:
        mrow = by_id.get(row.identifier)
        if mrow is None:
            _refuse("not offered a mark (no row of this id in the file)")
            out_formula.append(row)
            continue
        if not mrow.get("mark"):
            out_formula.append(row)
            continue
        counts["checked"] += 1
        reason = check_row(row, mrow)
        if reason is None and row.crop is None:
            reason = "no crop to draw on"
        if reason is not None:
            _refuse(reason)
            out_formula.append(row)
            continue
        dst = doc_dir / MARKS_DIR / row.crop.name
        if _draw(row.crop, dst, mrow["rect_frac"]):
            out_formula.append(dataclasses.replace(row, crop=dst))
            counts["drawn"] += 1
        else:
            _refuse("could not draw (no PIL or unreadable crop)")
            out_formula.append(row)

    out = dict(rows)
    out["formula"] = out_formula
    return out, counts
