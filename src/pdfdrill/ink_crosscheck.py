"""Cross-check pdfdrill's table grid against inkdrill's, and classify.

inkdrill is not a competing extractor. It sees ink no text extractor reports —
on a Word-produced handbook page it recovers the ruled table as ONE connected
component with 52 holes, 13 rows x 4 columns, while `pdfdrill tables` on the
same page reports a different 6x5 table (the nameplate figure above it) and
misses the ruled one. Both tools are behaving correctly; the disagreement is
the signal.

So this returns a CLASSIFICATION, never a score. A single percentage over that
page would describe neither tool, and averaging two correct answers about two
different objects is how a real finding becomes a number nobody can act on.

The contract is `docs`-side: inkdrill writes a MathPix-shaped `lines.json`
whose extra measurements ride on namespaced `ink.*` keys, so a MathPix-shaped
consumer ignores them. `ink_props` is the seam that keeps them alive on the
DocObject: the stream payload already preserves every field of a line
(`ingest_lines_json` does `dict(line)`), but object construction copies only
the props it names, so an `ink.*` key reached the stream and died there.
"""
from __future__ import annotations

from typing import Any, Optional

AGREE = "agree"
GRID_DISAGREE = "grid_disagreement"
ONLY_IN_MODEL = "only_in_model"
ONLY_IN_INK = "only_in_ink"

_INK_PREFIX = "ink."
# Below this, two regions are different objects rather than two views of one.
_MATCH_IOU = 0.30


def ink_props(line: Optional[dict]) -> dict[str, Any]:
    """The `ink.*` measurements on a line, to carry onto the DocObject.

    The dot is the contract: `inkjet` and `thinking` are not the namespace, and
    a substring test would sweep them in.
    """
    if not isinstance(line, dict):
        return {}
    return {k: v for k, v in line.items() if k.startswith(_INK_PREFIX)}


def region_iou(a: Optional[dict], b: Optional[dict]) -> float:
    """Intersection over union of two MathPix regions, 0.0 when either is absent."""
    if not a or not b:
        return 0.0
    ax0, ay0 = float(a.get("top_left_x") or 0), float(a.get("top_left_y") or 0)
    ax1, ay1 = ax0 + float(a.get("width") or 0), ay0 + float(a.get("height") or 0)
    bx0, by0 = float(b.get("top_left_x") or 0), float(b.get("top_left_y") or 0)
    bx1, by1 = bx0 + float(b.get("width") or 0), by0 + float(b.get("height") or 0)
    iw, ih = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _grid(t: dict) -> dict:
    return {"n_rows": t.get("n_rows"), "n_cols": t.get("n_cols"),
            "cells": len(t.get("cells") or [])}


def _warnings(t: dict) -> list[str]:
    """What the EXISTING validator says — not a second overlap implementation."""
    from .table_structure import check
    try:
        return check(list(t.get("cells") or []),
                     int(t.get("n_rows") or 0), int(t.get("n_cols") or 0))
    except Exception:
        return []


def crosscheck_tables(model_tables: list[dict], ink_tables: list[dict]) -> list[dict]:
    """One finding per table on either side; every table appears exactly once.

    A table dropped from the report is the failure this exists to avoid, so the
    result partitions both inputs rather than listing only the interesting rows.
    """
    findings: list[dict] = []
    used_ink: set[int] = set()

    for m in model_tables:
        best_i, best_iou = -1, 0.0
        for i, k in enumerate(ink_tables):
            if i in used_ink:
                continue
            iou = region_iou(m.get("region"), k.get("region"))
            if iou > best_iou:
                best_i, best_iou = i, iou
        if best_i < 0 or best_iou < _MATCH_IOU:
            findings.append({"verdict": ONLY_IN_MODEL, "model": _grid(m), "ink": None,
                             "iou": round(best_iou, 3), "warnings": _warnings(m)})
            continue
        k = ink_tables[best_i]
        used_ink.add(best_i)
        gm, gk = _grid(m), _grid(k)
        if gm == gk:
            findings.append({"verdict": AGREE, "model": gm, "ink": gk,
                             "iou": round(best_iou, 3), "warnings": _warnings(m)})
        else:
            detail = {key: {"model": gm[key], "ink": gk[key]}
                      for key in gm if gm[key] != gk[key]}
            findings.append({"verdict": GRID_DISAGREE, "model": gm, "ink": gk,
                             "iou": round(best_iou, 3), "detail": detail,
                             "warnings": _warnings(m)})

    for i, k in enumerate(ink_tables):
        if i not in used_ink:
            findings.append({"verdict": ONLY_IN_INK, "model": None, "ink": _grid(k),
                             "iou": 0.0, "warnings": _warnings(k)})
    return findings
