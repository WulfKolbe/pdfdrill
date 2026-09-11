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

672 review, fix round 1 — two findings confirmed on real, currently-
published production data (not this module's own dry-run script, which
under-reported both):

  * A crop can EXIST (not `None`) and still carry no visible content at
    all — `1510.06699_FO0765`/`_FO0911` and `kohlhase-omdoc_FO0045` are
    all pure white (`stddev == 0.0`) at every size on disk, and
    `evidence-formula.tex` already shows `---` for them today because
    the content never rendered upstream, not because of anything this
    module does. Drawing a rectangle on one of these asserts an evidence
    claim that is not there — worse than the "---" it would replace, and
    exactly the failure the two mandatory checks above exist to prevent.
    `apply()` now refuses these too (`_is_blank`), counted under their
    own reason, never silently — see out/672.txt for the corpus count.
  * `_draw`'s JPEG quality must follow the RUNG `reports.budget` chose
    for this kind (`reports.crops._apply_budget`'s `(scale, quality)`),
    not a constant: measured on real gilmore crops at the 655 floor
    (0.42/q70), a fixed quality of 92 nearly doubled a 30-row sample's
    bytes (86,805 -> 163,231) — re-encoding an already-scaled, already-
    quality-70 source at quality 92 does not shrink it back down, it
    just spends more bits on the SAME lossy pixels plus the rectangle's
    own high-frequency edges. `apply()` now takes the caller's own
    `rung` and threads its quality through; a kind that was never scaled
    (`rung is None`) draws at `DEFAULT_QUALITY` (92), matching
    `report_tex.render_crops`'s own save quality for an UNSCALED crop —
    so an unscaled document sees no quality change at all, only a
    scaled one does, and it now uses ITS OWN rung's quality rather than
    a value unrelated to it.
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

#: 672 review, fix round 1 — the quality `_draw` uses for a kind whose rung
#: is `None` (never scaled by 655's ladder — `reports.budget.choose_rung`
#: returned `scale >= 1.0`). Matches `report_tex.render_crops`'s own save
#: quality for a freshly-rendered, unscaled crop, so an unscaled document's
#: marked crops cost no more than the rectangle's own ink. A SCALED kind
#: never uses this constant — see `apply`'s `rung` parameter.
DEFAULT_QUALITY = 92

_REGION_KEYS = ("top_left_x", "top_left_y", "width", "height")

#: 672 review, fix round 1 — a crop this uniform carries no ink at all.
#: Measured on the real blank crops the review found (`1510.06699_FO0765`/
#: `_FO0911`, `kohlhase-omdoc_FO0045`): all exactly `stddev == 0.0` (a
#: perfectly flat JPEG). A small positive floor, not exactly 0.0, allows
#: for JPEG re-encoding noise on an otherwise-blank source without
#: letting a genuinely blank crop through.
_BLANK_STDDEV = 1.0


def _is_blank(path: Path) -> bool:
    """True when `path` carries no visible content — drawing on it would
    assert an evidence claim the crop itself does not support (672
    review, finding 1). `False`, never raises, when the file cannot be
    read at all: that failure belongs to `_draw`'s own try/except, not to
    this check, which only ever makes REFUSAL more likely, not less."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(path).convert("L")
        return ImageStat.Stat(im).stddev[0] < _BLANK_STDDEV
    except Exception:
        return False


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


def _draw(src: Path, dst: Path, rect_frac, quality: int = DEFAULT_QUALITY) -> bool:
    """One outline rectangle, `rect_frac` = (x0, y0, x1, y1) as FRACTIONS
    of the image — the same rectangle regardless of which resolution `src`
    happens to be at (full-size `report-crops/` or an already-scaled
    `report-crops-b/` copy), so one code path handles both sizes rather
    than a scale-specific branch. Never mutates `src`; returns False on
    any failure (no PIL, unreadable/corrupt image) so the caller counts a
    refusal instead of raising mid-build.

    `quality` (672 review, fix round 1) MUST be the rung's own quality
    for a scaled crop, never a constant independent of it — `apply` is
    the only production caller and always passes one; a caller of this
    function directly (tests) gets `DEFAULT_QUALITY`, which is only
    correct for an unscaled crop."""
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
    im.save(dst, "JPEG", quality=quality)
    return True


def _empty_counts(n_rows: int) -> dict:
    return {"rows": n_rows, "marked_in_file": None, "checked": 0,
            "drawn": 0, "refused": {}}


def apply(rows: dict, marks_path: "Path | str | None", doc_dir: "Path | str",
         rung=None):
    """Formula rows only; every other kind passes through untouched.

    Off by construction when `marks_path` is falsy — returns `rows`
    UNCHANGED (the same dict, not a copy) so a document with no marks file
    builds byte-identical to before this module existed (672's own
    required proof; see tests/test_reports_marks.py and out/672.txt).

    `rung` (672 review, fix round 1) is the caller's OWN `(scale,
    quality)` — or `None` — that `reports.crops.ensure_crops` chose for
    the "formula" kind (the SAME value it already carries for
    `commands._evidence_line`'s "OVER BUDGET" message, `rungs.get(
    "formula")`). Every marked crop is re-encoded at THIS rung's quality,
    never a constant independent of it: a scaled kind's crops are already
    lossy at the rung's own quality, and re-encoding them again at a
    HIGHER quality does not recover detail, it only spends more bytes on
    the same pixels plus the rectangle's own edges (measured: a fixed 92
    nearly doubled a 30-row real sample at gilmore's 0.42/q70 floor).
    `rung is None` (this kind was never scaled) draws at
    `DEFAULT_QUALITY`, matching the quality an unscaled crop was already
    saved at, so an unscaled document's marked bytes cost only the
    rectangle's own ink.

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
    "not offered a mark", a `check_row` reason, "no crop to draw on",
    "marks file row is missing rect_frac", "crop has no visible content
    (blank)" (672 review, finding 1 — verified on real production data:
    a crop can exist and still carry no ink at all, and drawing a
    rectangle on one asserts an evidence claim that is not there), or
    "could not draw (no PIL or unreadable crop)".
    """
    formula = rows.get("formula") or ()
    counts = _empty_counts(len(formula))
    if not marks_path:
        return rows, counts
    quality = rung[1] if rung else DEFAULT_QUALITY

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
        rect_frac = mrow.get("rect_frac")
        if reason is None and row.crop is None:
            reason = "no crop to draw on"
        elif reason is None and not (isinstance(rect_frac, (list, tuple))
                                     and len(rect_frac) == 4):
            reason = "marks file row is missing rect_frac"
        elif reason is None and _is_blank(row.crop):
            reason = "crop has no visible content (blank)"
        if reason is not None:
            _refuse(reason)
            out_formula.append(row)
            continue
        dst = doc_dir / MARKS_DIR / row.crop.name
        if _draw(row.crop, dst, rect_frac, quality=quality):
            out_formula.append(dataclasses.replace(row, crop=dst))
            counts["drawn"] += 1
        else:
            _refuse("could not draw (no PIL or unreadable crop)")
            out_formula.append(row)

    out = dict(rows)
    out["formula"] = out_formula
    return out, counts
