"""509/510 — the corrected PAIR, selected and identified once.

A corrected row is the same fact in two artefacts: `corrections.html` shows
every one in the corpus, `report.pdf` shows the ones in its own document.
422 was written because four artefacts had already drifted, and two
implementations of one idea is how that happens — so the SELECTION and the
ROW MODEL live here and both renderers read them.

What is NOT shared is the rendering. corrections.html sets a pair as HTML with
an inline SVG or KaTeX; report.pdf sets it as two longtable rows. Those are
different jobs and pretending otherwise would be its own kind of drift.

THE PAIR IS THE UNIT. The failed reading above, the recovered one below, and
ONE scan spanning both — it is a single region, so the reader compares two
readings of one picture rather than two pictures (437).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import refine as rf

LIB_DEFAULT = Path.home() / "pdfdrill-library"
MAX_MODEL_BYTES = 300 * 1024 * 1024


def pairs_in(doc_dir: Path) -> list:
    """Every ACCEPTED correction in one document, newest evidence first.

    The filter is "accepted", and the BASIS IS A COLUMN, not a filter: 438
    found 32 corrections verified by ink and one verified against the author's
    e-print by counting, and filtering to `verified_by: ink` would have
    dropped the strongest correction in the corpus.
    """
    doc_dir = Path(doc_dir)
    f = doc_dir / "model.docmodel.json"
    if not f.is_file() or f.stat().st_size > MAX_MODEL_BYTES:
        return []
    try:
        s = f.read_text(encoding="utf-8", errors="replace")
        if '"provenance": "change"' not in s:
            return []
        model = json.loads(s)
    except (OSError, ValueError):
        return []
    bib = (model.get("meta") or {}).get("bibkey") or doc_dir.name
    # 509 — THE REGION IS NOT ALWAYS IN props. On 1 of 33 corrections
    # (0707.4470_FO0175, the one 502 repaired) `props.region` is absent and
    # the region lives on the object's realizations, which is the same trap
    # 492 hit when it looked for props["top_left_x"] on 0 of 70,000 objects.
    # Left unresolved the identifier key degenerates to all-None and matches
    # whatever tiddler is also all-None — it silently returned a PAGE tiddler.
    from .docinspect import build_stream_index, object_geometry
    sidx = build_stream_index(model)
    out = []
    for o in model.get("objects", []):
        pr = dict(o.get("props") or {})
        if not pr.get("region"):
            try:
                page, bbox, _ = object_geometry(o, sidx)
            except Exception:                       # noqa: BLE001
                page, bbox = None, None
            if page is not None and bbox:
                pr.setdefault("page", "%03d" % int(page))
                pr["region"] = {"top_left_x": bbox["x"], "top_left_y": bbox["y"],
                                "width": bbox["w"], "height": bbox["h"]}
        for r in (o.get("realizations") or []):
            if r.get("provenance") != "change":
                continue
            rp = r.get("props") or {}
            if not rp.get("verified_by"):
                continue                       # a proposal, not a solution
            out.append({
                "doc": doc_dir.name, "bibkey": bib, "obj": o["id"],
                "type": o.get("type"), "page": pr.get("page"),
                "conf": pr.get("confidence"),
                "before": pr.get("latex") or "",
                "after": rp.get(rf.REFINED_FIELD) or "",
                "basis": rp.get("basis") or "",
                "verified_by": rp.get("verified_by"),
                "ink_before": rp.get("ink_before"),
                "ink_after": rp.get("ink_after"),
                "author": rp.get("author") or "",
                "at": rp.get("at") or "",
                "evidence": ("" if rp.get("evidence") is None
                             else str(rp["evidence"])),
                "region": pr.get("region") or {},
            })
    return out


def collect(lib: Path | None = None) -> list:
    """Every accepted correction in the corpus."""
    lib = Path(lib or LIB_DEFAULT)
    out = []
    for d in sorted(p for p in lib.iterdir() if p.is_dir()):
        out.extend(pairs_in(d))
    return out


_TID_CACHE: dict = {}
_TXT_CACHE: dict = {}


def identifier_for(rec, lib: Path | None = None):
    """The report identifier of a pair, via the tiddler at its REGION.

    Crops are named `<bibkey>_EQnnnn.jpg` and an object id appears in no
    filename, so the join is region -> tiddler title -> crop. Matching on the
    region rather than on the LaTeX is what 282 established: the 5-tuple names
    a region and the text does not.
    """
    lib = Path(lib or LIB_DEFAULT)
    doc = rec["doc"]
    if doc not in _TID_CACHE:
        # 560 — the identifier join read a two-day-old array on four
        # documents while the duplicates were on disk (558).
        from .tidpath import tiddlers_in as _tin
        f = _tin(lib / doc)
        idx: dict = {}
        bytext: dict = {}
        if f is not None:
            try:
                t = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                for x in (t if isinstance(t, list) else t.get("tiddlers", [])):
                    k = (str(x.get("page")), str(x.get("top_left_x")),
                         str(x.get("top_left_y")), str(x.get("width")),
                         str(x.get("height")))
                    idx.setdefault(k, x.get("title"))
                    # 509 — the text index, for rows the region cannot reach.
                    # An FO tiddler carries NO region (488 measured the same
                    # absence on page and confidence), so region -> title is
                    # structurally impossible for inline formulas. A UNIQUE
                    # latex match is unambiguous; a repeated one is not, and
                    # is dropped rather than guessed at.
                    lx = x.get("latex")
                    if lx:
                        bytext[lx] = None if lx in bytext else x.get("title")
            except (OSError, ValueError):
                pass
        _TID_CACHE[doc] = idx
        _TXT_CACHE[doc] = bytext
    reg = rec.get("region") or {}
    if not reg or reg.get("top_left_x") is None:
        # an all-None key matches any tiddler that also has none, which is how
        # a Formula's identifier came back as a Page's. Refuse the region
        # route and try the text, which is exact when it is unique.
        return _TXT_CACHE.get(doc, {}).get(rec.get("before") or "")
    key = (str(rec.get("page")).zfill(3), str(reg.get("top_left_x")),
           str(reg.get("top_left_y")), str(reg.get("width")),
           str(reg.get("height")))
    hit = _TID_CACHE[doc].get(key)
    if hit is None:                        # the page may be stored unpadded
        hit = _TID_CACHE[doc].get((str(rec.get("page")),) + key[1:])
    if hit is None:
        hit = _TXT_CACHE.get(doc, {}).get(rec.get("before") or "")
    return hit


def crop_path(rec, lib: Path | None = None):
    """The scan crop for a pair — ONE file, shared by both halves."""
    lib = Path(lib or LIB_DEFAULT)
    ident = identifier_for(rec, lib)
    if not ident:
        return None
    f = lib / rec["doc"] / "report-crops" / ("%s.jpg" % ident)
    return f if f.is_file() else None
