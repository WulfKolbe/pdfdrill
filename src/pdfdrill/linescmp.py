r"""Score one `lines.json` against another on the same pages.

WHY A READER NEEDS THIS AND NOT A GOLD FILE
-------------------------------------------
A new reader's output cannot be checked against a hand transcription at any
useful scale: 48 pages is 1,800 lines, and a hand reference exists for 8 of
them. What DOES exist, for every document pdfdrill has ever bought, is MathPix's
reading of exactly those pages — and MathPix's geometry is the thing a new
reader is most likely to get wrong, because it is the half a language model
does not return at all.

So this module answers one question: given two readings of the same pages,
how often does the new reading put a line WHERE the reference put it, and does
it CALL it the same thing. That is not a claim that MathPix is right; it is a
claim that a disagreement is worth looking at, which on a 1,800-line document
is the only tractable form of review.

THE BOXES ARE NORMALISED PER PAGE, AND THAT IS NOT A CONVENIENCE
----------------------------------------------------------------
The two readings are in different pixel frames: MathPix reads at its own
resolution (measured: 1,066 x 1,893 for the reference Killing pages) and this
reader renders at 400 dpi (1,928 x 3,072 for the same page). Comparing raw
regions would score every line zero. Each box is therefore divided by its OWN
page's declared `page_width`/`page_height` before any overlap is computed —
which is also the only reason the comparison is meaningful at all, and the
reason `page_width` is a required field of the contract rather than metadata.

NOT `mathpix_conformance`, AND THE DIFFERENCE IS THE WHOLE POINT
---------------------------------------------------------------
`cmd_conformance` (879) already asks a question about our reading against
MathPix's, and this module would be a duplicate of it if the questions were the
same. They are not, and that module says so itself: it compares DISTRIBUTIONS —
how many lines of each type, which fields are populated — and declines the
alignment explicitly, because "an alignment needs region-overlap thresholds and
every number would carry them". It is the right instrument for "which of the
eighteen types do we emit at all", and it is silent on geometry.

This module is that declined alignment, with the thresholds stated (`HIT`, and
per-page normalisation). It is the right instrument for "is this line's box
where the reference put it", which is the half a language model does not return
and so the half a new reader gets wrong. Run both: conformance says what the
reading is MISSING, this says whether what it has is in the right place.

WHAT IS LEFT OUT, AND WHY
-------------------------
`page_info` is excluded from both sides. The running head and the folio are
printed at opposite ends of one row; MathPix emits two boxes, a reader that
emits one spanning box scores zero on both, and a reader that emits two scores
well — but neither outcome says anything about the reading of the page's
CONTENT, which is what the score is for. It is reported separately instead.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .inkbox import iou

#: Types that mean the same thing to a consumer even when the two readers
#: disagree on which to use: all four are prose a sentence runs through, and
#: `line_types` treats a heading and a title identically (both are forbidden
#: transclusion hosts). A disagreement inside this set is not a defect.
_SAME = frozenset({"text", "section_header", "title", "authors", "footnote",
                   "list_item"})

#: The overlap at which two readers are held to have found the same line.
#: 0.5 is the detection convention and is what the reference measurements in
#: the handover used, so scores here are comparable with those.
HIT = 0.5


def _norm(line: dict, page: dict) -> Optional[tuple[float, float, float, float]]:
    r = line.get("region") or {}
    w = page.get("page_width") or 0
    h = page.get("page_height") or 0
    if not w or not h or not r.get("width") or not r.get("height"):
        return None
    x0 = r["top_left_x"] / w
    y0 = r["top_left_y"] / h
    return (x0, y0, x0 + r["width"] / w, y0 + r["height"] / h)


def _iou(a, b) -> float:
    """IoU on normalised (float) boxes — `inkbox.iou` is integer-pixel."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    denom = ua + ub - inter
    return inter / denom if denom > 0 else 0.0


def compare(ours: dict, theirs: dict, *, hit: float = HIT) -> dict:
    """Score `ours` against the reference `theirs`, per reference line.

    The direction matters and is deliberate: we walk THEIR lines and ask
    whether we found each one. A reader that emits twice as many boxes would
    score well in the other direction by covering everything, which is the
    failure a recall-only score cannot see; the extra boxes show up as
    `ours_unmatched` instead.
    """
    tp = {p.get("page"): p for p in (theirs.get("pages") or [])}
    res: dict = {
        "pages": 0, "lines": 0, "hit": 0, "type_ok": 0,
        "by_type": {}, "ours_lines": 0, "ours_unmatched": 0,
        "page_info_ours": 0, "page_info_theirs": 0,
    }
    ious: list[float] = []
    for p in ours.get("pages") or []:
        q = tp.get(p.get("page"))
        if q is None:
            continue
        res["pages"] += 1
        mine = []
        for l in p.get("lines") or []:
            if l.get("type") == "page_info":
                res["page_info_ours"] += 1
                continue
            b = _norm(l, p)
            if b is not None:
                mine.append([b, l.get("type"), False])
        res["ours_lines"] += len(mine)
        for l in q.get("lines") or []:
            if l.get("type") == "page_info":
                res["page_info_theirs"] += 1
                continue
            b = _norm(l, q)
            if b is None:
                continue
            res["lines"] += 1
            bt = res["by_type"].setdefault(l.get("type"), [0, 0, 0])
            bt[0] += 1
            best, bi = 0.0, -1
            for n, (mb, _mt, _used) in enumerate(mine):
                v = _iou(b, mb)
                if v > best:
                    best, bi = v, n
            ious.append(best)
            if best >= hit and bi >= 0:
                mine[bi][2] = True
                res["hit"] += 1
                bt[1] += 1
                mt = mine[bi][1]
                if mt == l.get("type") or {mt, l.get("type")} <= _SAME:
                    res["type_ok"] += 1
                    bt[2] += 1
        res["ours_unmatched"] += sum(1 for m in mine if not m[2])
    ious.sort()
    res["median_iou"] = round(ious[len(ious) // 2], 3) if ious else 0.0
    res["hit_rate"] = round(res["hit"] / res["lines"], 4) if res["lines"] else 0.0
    res["type_rate"] = (round(res["type_ok"] / res["hit"], 4)
                        if res["hit"] else 0.0)
    return res


def compare_files(ours: Path, theirs: Path, *, hit: float = HIT) -> dict:
    return compare(json.loads(Path(ours).read_text(encoding="utf-8")),
                   json.loads(Path(theirs).read_text(encoding="utf-8")),
                   hit=hit)


def report(res: dict, *, ours_name: str = "ours",
           theirs_name: str = "reference") -> str:
    """The score as prose, in the shape every other pdfdrill report has."""
    lines = [
        f"{ours_name} vs {theirs_name} — {res['pages']} pages in common",
        f"  found       {res['hit']}/{res['lines']} reference lines at "
        f"IoU>={HIT} ({res['hit_rate']:.0%}), median IoU {res['median_iou']}",
        f"  typed alike {res['type_ok']}/{res['hit']} of those "
        f"({res['type_rate']:.0%})",
        f"  ours         {res['ours_lines']} lines, "
        f"{res['ours_unmatched']} matching no reference line",
        f"  page_info    {res['page_info_ours']} ours / "
        f"{res['page_info_theirs']} reference (excluded from the score)",
    ]
    by = res.get("by_type") or {}
    if by:
        lines.append("  per reference type (found/total, typed alike):")
        for t, (tot, hit_n, ok) in sorted(by.items(), key=lambda kv: -kv[1][0]):
            lines.append(f"    {t:18} {hit_n:5}/{tot:<5} {ok:5}")
    return "\n".join(lines)
