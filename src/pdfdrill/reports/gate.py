"""The publish gate for the redrawn surface.

The old gate compared the ink's PDF checksum with the measure build's, so a
layout change could never publish without re-measuring. The measurement is
about the MODEL's equations, not about a PDF: the ink records the model it
measured (sha256 and mtime, 575), and that is what is compared. The PDF
checksum is recorded and never compared.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import report_tex as rt

PUBLISHED_FILES = ("evidence-equation.pdf", "evidence-formula.pdf",
                   "evidence-table.pdf", "evidence-image.pdf", "residuals.pdf")
FIX = "run `pdfdrill residuals --measure --pdf <pdf>`"


def _ink(doc_dir: Path) -> dict:
    p = Path(doc_dir) / "report.ink.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def timestamp_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    ink = _ink(doc_dir)
    if not ink:
        return False, "no report.ink.json; %s" % FIX
    ma = ink.get(rt.MEASURED_AGAINST) or {}
    if not ma.get("built_at"):
        return False, "the ink does not say when it was measured; %s" % FIX
    live = rt.model_state(doc_dir)
    same_sha = (ma.get("model_sha256") and live.get("model_sha256")
                and ma["model_sha256"] == live["model_sha256"])
    if same_sha:
        return True, "measured %s against the model on disk" % ma["built_at"]
    try:
        older = int(live.get("model_mtime") or 0) > int(ma.get("model_mtime") or 0)
    except (TypeError, ValueError):
        older = True
    if older:
        return False, ("measured %s, but the model was rebuilt since (model "
                       "mtime %s > measured %s); %s"
                       % (ma["built_at"], live.get("model_mtime"),
                          ma.get("model_mtime"), FIX))
    return True, ("measured %s; model sha differs but is not newer (mtime %s)"
                  % (ma["built_at"], live.get("model_mtime")))


def coverage_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    tex = doc_dir / "residuals.tex"
    if not tex.is_file():
        return False, "no residuals.tex to read row identifiers from"
    from ..inkconvert import identifiers
    shown = {i for i in identifiers(tex.read_text(encoding="utf-8", errors="replace"))
             if "_EQ" in i}
    measured = {r.get("id") for r in (_ink(doc_dir).get("rows") or []) if r.get("id")}
    straddle = set()
    mf = doc_dir / rt.ROWS_MANIFEST
    if mf.is_file():
        try:
            straddle = {r["identifier"] for r in
                        (json.loads(mf.read_text(encoding="utf-8")).get("rows") or [])
                        if not r.get("rules_on_one_page", True)}
        except Exception:
            straddle = set()
    gone = sorted((shown - measured) - straddle)
    if gone:
        return False, ("%d equation row(s) shown carry no measurement and do not "
                       "straddle a page: %s" % (len(gone), ", ".join(gone[:8])))
    return True, "%d equation rows shown, all measured (%d straddle)" % (
        len(shown), len(shown & straddle))


def artefacts_gate(doc_dir) -> tuple:
    missing = [f for f in PUBLISHED_FILES
               if not (Path(doc_dir) / f).is_file()
               or (Path(doc_dir) / f).stat().st_size == 0]
    if missing:
        return False, "missing: %s" % ", ".join(missing)
    return True, "all five present"


def glyphs_gate(doc_dir) -> tuple:
    bad = []
    for f in PUBLISHED_FILES:
        log = (Path(doc_dir) / f).with_suffix(".log")
        if not log.is_file():
            bad.append("%s: no log" % f)
            continue
        lost = rt.glyphs_dropped(log)
        if lost is not None:
            bad.append("%s: %d dropped" % (f, lost[0]))
    return (not bad), ("clean" if not bad else "; ".join(bad))


def checklist(doc_dir) -> dict:
    doc_dir = Path(doc_dir)
    ink_p = doc_dir / "report.ink.json"
    live = [n for n in ("report.ink.json.REFUSED", "report.ink.json.MISPAIRED")
            if (doc_dir / n).is_file() and ink_p.is_file()
            and (doc_dir / n).stat().st_mtime >= ink_p.stat().st_mtime]
    return {
        "artefacts": artefacts_gate(doc_dir),
        "glyphs": glyphs_gate(doc_dir),
        "ink": ((ink_p.is_file() and not live),
                "present" if ink_p.is_file() and not live else
                ("%s is newer: the last attempt failed to pair" % live[0]
                 if live else "no report.ink.json")),
        "timestamp": timestamp_gate(doc_dir),
        "coverage": coverage_gate(doc_dir),
    }
