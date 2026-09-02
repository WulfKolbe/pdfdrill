#!/usr/bin/env python3
r"""509 — what report.pdf would contain under the rule "unresolved, or changed".

Three states, and a row appears only if it is in one of them:

  corrected            the row carries an accepted refinement. Shown as a
                       PAIR: the failed entry above, the recovered one below,
                       both against the same scan.
  unresolved           the row does not render, and nothing has repaired it.
  doubted but correct  MathPix's confidence is below 0.01 and the ink says
                       the render matches the scan. Not a problem — evidence
                       that the confidence field doubted a correct reading,
                       which is the calibration data the correspondence has
                       been missing.

"The ink says it's right" is K (clean), N (below the measured noise floor)
or S (stable across 300 and 600 dpi). W (weak) and C (component) are the
classes that flag a real difference and are not agreement.

Everything else — read correctly, ink agrees, nothing changed — says nothing
and belongs in formula-report.html and tables.html, which already hold it.
"""
from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import report_tex as rt          # noqa: E402

AGREES = {"K", "N", "S"}
DOUBTED = 0.01
TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")


def measure(doc: Path) -> dict:
    tp = list(doc.glob("*.tiddlers.json"))
    if not tp:
        return {}
    try:
        tids = json.loads(tp[0].read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    tids = tids.get("tiddlers", tids) if isinstance(tids, dict) else tids
    ink_path = doc / "report.ink.json"
    ink, pages_seen = {}, collections.Counter()
    if ink_path.is_file():
        try:
            j = json.loads(ink_path.read_text(encoding="utf-8", errors="replace"))
            for r in j.get("rows", []):
                ink[r.get("id")] = str(r.get("code", "")).split("|")[0]
                if r.get("report_page") is not None:
                    pages_seen[r["report_page"]] += 1
        except (OSError, ValueError):
            pass
    # rows per report page, MEASURED from the ink rather than assumed
    rpp = (sum(pages_seen.values()) / len(pages_seen)) if pages_seen else 6.0

    corrected = unresolved = doubted = 0
    for x in tids:
        title = x.get("title", "")
        lx = x.get("latex") or ""
        if not lx or not TYPED.search(title):
            continue
        refined = x.get("latex_refined")
        if refined and refined != lx:
            corrected += 1
            continue
        if not rt.renderable(lx):
            unresolved += 1
            continue
        c = x.get("confidence")
        try:
            c = float(c)
        except (TypeError, ValueError):
            c = None
        if c is not None and c < DOUBTED and ink.get(title) in AGREES:
            doubted += 1
    # a corrected row is a PAIR, so it costs two rows of space
    rows = corrected * 2 + unresolved + doubted
    build = doc / "report.build.json"
    today = None
    if build.is_file():
        try:
            today = json.loads(build.read_text()).get("pages")
        except (OSError, ValueError):
            pass
    est = 1 if rows == 0 else max(1, math.ceil(rows / max(1.0, rpp)) + 1)
    return {"corrected": corrected, "unresolved": unresolved,
            "doubted": doubted, "rows": rows,
            "rows_per_page": round(rpp, 1), "pages_today": today,
            "pages_estimate": est,
            "ink_rows": len(ink)}


if __name__ == "__main__":
    docs = json.loads(Path(sys.argv[1]).read_text())
    out = {}
    for slug, pdf in sorted(docs.items()):
        if not pdf:
            continue
        out[slug] = measure(Path(pdf).parent)
    json.dump(out, sys.stdout, indent=1)
