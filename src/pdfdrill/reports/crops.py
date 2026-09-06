"""One entry point fills `row.crop` for every kind.

The crop functions in report_tex take dict records (title, canonical_uri,
page, region keys). Those records are built HERE from rows — the package
never reads a tiddler. Equations with a CDN uri are downloaded; anything
without one (tables, images, a formula's HOST LINE) is rendered from the
PDF (461, 530). Cached files are reused.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import report_tex as rt
from .rows import FormulaRow

CROPS_DIR = "report-crops"
KINDS_ALL = ("_EQ", "_FO", "_TAB", "_DIA", "_PIC")


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


def ensure_crops(rows: dict, doc_dir: Path, pdf: Path, *, bibkey: str,
                 history=None, images: bool = True):
    """Returns (rows with `crop` set, one-line note)."""
    if not images:
        return rows, "images: off"
    doc_dir = Path(doc_dir)
    crops = doc_dir / CROPS_DIR
    recs = records(rows)
    ok, cached, failed = rt.download_crops(recs, crops)
    r_ok, r_cached, r_skip = rt.render_crops(recs, crops, Path(pdf),
                                             kinds=KINDS_ALL)
    out = {}
    for kind, lst in rows.items():
        out[kind] = [dataclasses.replace(
            r, crop=rt.crop_file(crops, r.identifier, bibkey, history))
            for r in lst]
    note = ("crops: %d fetched, %d cached, %d failed; %d rendered from the "
            "PDF, %d cached, %d skipped" % (ok, cached, failed, r_ok, r_cached,
                                            r_skip))
    return out, note
