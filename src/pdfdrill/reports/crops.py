"""One entry point fills `row.crop` for every kind.

The crop functions in report_tex take dict records (title, canonical_uri,
page, region keys). Those records are built HERE from rows — the package
never reads a tiddler. Equations with a CDN uri are downloaded; anything
without one (tables, images, a formula's HOST LINE) is rendered from the
PDF (461, 530). Cached files are reused.

655 — after every crop is fetched/rendered at full size, a size BUDGET is
applied per KIND: each of `gate.PUBLISHED_FILES`'s `evidence-<kind>.pdf` is
a separate file with its own crops, so the rung that keeps
`evidence-formula.pdf` under budget is decided from formula rows' crops
alone, not the whole document's. `residuals.pdf` draws a small SUBSET of
the same equation/formula rows and inherits whichever copy (full or
already-scaled) that row was given here — including the Corrected section,
which `reports.residuals` routes through the same row objects as of review
round 1's finding-4 fix, rather than a bibkey-only lookup back into the
full-size directory. This makes an independent RUNG SELECTION for
`residuals.pdf` unnecessary, but not a real-artefact OVER BUDGET check —
see `reports.budget.check_artifact`, run by `evidence.build`/
`residuals.build` after the PDF is actually compiled, since a crop-byte
PREDICTION (this module, `_apply_budget`) is not the same claim as a
verdict on the finished file (review round 1, finding 3). See
`reports.budget` for the ladder and the rung choice.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import report_tex as rt
from . import budget as _budget
from .rows import FormulaRow

CROPS_DIR = "report-crops"
#: 655 — scaled copies live in a SEPARATE directory, same reason `scale_crops`
#: itself never overwrites its source: `report.pdf`'s tables and the CDN
#: equation crops read CROPS_DIR directly, and a document whose rung is
#: already 1.0 must leave it byte-for-byte untouched.
CROPS_DIR_B = "report-crops-b"
#: 644 — the substring `render_crops` filters titles by, built from the title
#: scheme's own prefixes for the kinds a report has rows for.
def _kinds_all() -> tuple:
    from docops.projectors.tiddlywiki import TITLE_SHAPES
    from .. import report_tex as _rt
    return tuple(dict.fromkeys(
        "_" + TITLE_SHAPES[k].prefix for k in _rt.REPORT_KINDS
        if not TITLE_SHAPES[k].keyed))


KINDS_ALL = _kinds_all()


def records(rows: dict) -> list:
    """The dict records download_crops/render_crops read, one per row that
    has somewhere to crop from. A formula uses its host line's page and
    region; without one it has no record."""
    out = []
    for lst in rows.values():
        for r in lst:
            if isinstance(r, FormulaRow):
                h = r.host_line
                if h is None or h.page is None or not h.region:
                    continue
                page, region, uri = str(h.page), h.region, ""
            else:
                page, region, uri = r.page, r.region, r.cdn_url
            if not region and not uri:
                continue
            rec = {"title": r.identifier, "canonical_uri": uri or "",
                   "page": page}
            rec.update({k: region[k] for k in ("top_left_x", "top_left_y",
                                               "width", "height") if k in region})
            out.append(rec)
    return out


def _apply_budget(lst: list, crops: Path, crops_b: Path, budget_mb: float):
    """One kind's rows, all crops already at full size in `crops`. Returns
    (rows with `crop`/`px_width` possibly repointed into `crops_b`, note or
    "" when the rung is 1.0 -- nothing scaled, nothing to say).

    Titles come from the rows' OWN resolved crop paths (already run through
    `crop_file`'s bibkey-history lookup), never re-derived from `identifier`
    directly — a renamed document's crop may not be filed under its current
    bibkey (264)."""
    titles = sorted({r.crop.stem for r in lst if r.crop is not None})
    if not titles:
        return lst, ""
    scale, quality, total, over = _budget.choose_rung(crops, titles,
                                                       budget_mb=budget_mb)
    mb = _budget._mb_for_bytes(total)   # DECIMAL MB (655 review round 1, finding 1)
    if scale >= 1.0:
        return lst, ""
    widths = rt.scale_crops(crops, crops_b, titles, scale=scale,
                            quality=quality, force=True)
    out = [dataclasses.replace(r, crop=crops_b / ("%s.jpg" % r.crop.stem),
                               px_width=str(widths[r.crop.stem]))
           if r.crop is not None and r.crop.stem in widths else r
           for r in lst]
    # 655 review round 1, finding 3 -- this is a PREDICTION (crop bytes,
    # before xelatex adds its own apparatus), never the verdict: the actual
    # "OVER BUDGET" the user sees comes from `reports.budget.check_artifact`
    # against the COMPILED PDF, in `evidence.build`/`residuals.build`. Say
    # so here rather than reusing that phrase for a different claim.
    note = "scale=%.2f q=%d %.1fMB predicted%s" % (
        scale, quality, mb, " (floor, still over budget predicted)" if over else "")
    return out, note


def ensure_crops(rows: dict, doc_dir: Path, pdf: Path, *, bibkey: str,
                 history=None, images: bool = True,
                 budget_mb: float = _budget.CROP_BUDGET_MB):
    """Returns (rows with `crop` set, one-line note).

    655 — after every crop is fetched/rendered, each KIND's rows are checked
    against `budget_mb` (default `reports.budget.CROP_BUDGET_MB`, the
    user's own stated comfort) independently, since each kind is a
    SEPARATE published PDF. A kind already under budget is left pointing at
    its full-size crop, byte-identical; one that is not is repointed at a
    scaled copy in `CROPS_DIR_B`, with `px_width` set to the ORIGINAL pixel
    width so the physical size on the page does not move (`crop_cell`)."""
    if not images:
        return rows, "images: off"
    doc_dir = Path(doc_dir)
    crops = doc_dir / CROPS_DIR
    crops_b = doc_dir / CROPS_DIR_B
    recs = records(rows)
    ok, cached, failed = rt.download_crops(recs, crops)
    r_ok, r_cached, r_skip = rt.render_crops(recs, crops, Path(pdf),
                                             kinds=KINDS_ALL)
    out, budget_notes = {}, []
    for kind, lst in rows.items():
        lst = [dataclasses.replace(
            r, crop=rt.crop_file(crops, r.identifier, bibkey, history))
            for r in lst]
        # 655 review round 1, finding 5 -- a distinct name from the final
        # `note` below: this one is per-KIND and never read after the loop.
        out[kind], kind_note = _apply_budget(lst, crops, crops_b, budget_mb)
        if kind_note:
            budget_notes.append("%s %s" % (kind, kind_note))
    note = ("crops: %d fetched, %d cached, %d failed; %d rendered from the "
            "PDF, %d cached, %d skipped" % (ok, cached, failed, r_ok, r_cached,
                                            r_skip))
    if budget_notes:
        note += "; budget (%.0fMB): %s" % (budget_mb, "; ".join(budget_notes))
    return out, note
