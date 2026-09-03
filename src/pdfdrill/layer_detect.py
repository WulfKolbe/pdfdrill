"""Per-layer DETECTORS: is this derived layer present in the model right now?

A fact says a layer was built once. A detector says it is there now. `model
--force` discards every derived layer while the facts and evidence counters
that assert them survive — `BIBLIOGRAPHY_BUILT` outlived the destruction of all
40 References on 1706.03762, and `status` reported nothing.

Each detector is a pure predicate over the doc (plus, for a projection, its
artifact). The rule they encode is the one already in
`planner._tiddlers_current`: an artifact is done only while the thing it was
projected FROM has not moved on.

COVERAGE, so the next reader sees nine gaps and one decision rather than ten
gaps. Six layers are covered: bibliography, geometry, tiddlers, compare, svg,
expandmath.

EXCLUDED BY DECISION — not missing:
  quant   `cmd_quantities` is a pure REPORT. It reads the model, prints a
          tally, writes no artifact and records no fact. It has no state, so it
          cannot be stale and there is nothing to retract; a detector would
          invent a status for something that has none. `present("quant", …)`
          raises, and a test pins that so it cannot be added absent-mindedly.

NOT YET COVERED — nine layers that also write a fact a rebuild outlives, i.e.
the same defect this module fixes, still open for each of them:
  annotate, eqnums, lists, algorithms, semantic, elements, scikgtex, stex, lean
Adding one is: a detector here, an entry in LAYERS, and a before/after test
against a real model in both states.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional


def _objects(doc: Any) -> Iterable:
    o = getattr(doc, "objects", None)
    if isinstance(o, dict):
        return o.values()
    if isinstance(doc, dict):
        return doc.get("objects") or []
    return o or []


def _props(obj: Any) -> dict:
    p = getattr(obj, "props", None)
    if p is None and isinstance(obj, dict):
        p = obj.get("props")
    return p or {}


def _type(obj: Any) -> str:
    t = getattr(obj, "type", None)
    if t is None and isinstance(obj, dict):
        t = obj.get("type")
    return t or ""


def _streams(doc: Any) -> dict:
    s = getattr(doc, "streams", None)
    if s is None and isinstance(doc, dict):
        s = doc.get("streams")
    return s or {}


# ------------------------------------------------------------- model layers
def has_bibliography(doc: Any) -> bool:
    """A Reference object exists. `bibliography` creates them; a rebuild drops
    all 40 while BIBLIOGRAPHY_BUILT survives."""
    return any(_type(o) == "Reference" for o in _objects(doc))


def has_geometry(doc: Any) -> bool:
    """The `pdf_lines` stream exists.

    NOT "some object has a region": measured on 1706.03762, regions SURVIVE the
    rebuild (65 before, 65 after) because the merged born-digital build sets
    them itself. Only the fused stream distinguishes the two states, so a
    region-based test would report geometry present on a model that has none.
    """
    return "pdf_lines" in _streams(doc)


def has_svg(doc: Any) -> bool:
    """Some graphic carries a rendered SVG."""
    return any((_props(o).get("svg") or "").strip() for o in _objects(doc))


def has_expanded_math(doc: Any) -> bool:
    """Some math object carries `expandmath`'s provenance marker.

    `expandmath` MUTATES the model rather than projecting from it, so this is
    an adequacy test over content — no artifact, no mtime.
    """
    return any(_props(o).get("latex_expanded_by") for o in _objects(doc))


# -------------------------------------------------------------- projections
def artifact_current(paths: Iterable[Path], model_path: Path) -> bool:
    """Do these projections exist AND post-date the model?

    The same rule as `planner._tiddlers_current`, factored so a second
    projection does not grow a second staleness notion — there are already two
    in `commands.py` and a third is how they drift apart. MIN, not max: every
    matching artifact is a projection of this model, and taking the newest lets
    a fresh one mask a stale sibling.
    """
    paths = [Path(p) for p in paths]
    if not paths or not Path(model_path).exists():
        return False
    try:
        return min(p.stat().st_mtime for p in paths) >= Path(model_path).stat().st_mtime
    except OSError:
        return False


def has_tiddlers(blob_dir: Path, model_path: Path) -> bool:
    # 560 — THE GLOB HERE IS CORRECT AND IS NOT THE 558 DEFECT.
    #
    # I replaced it with `tidpath.tiddlers_in` and two tests said no:
    # `test_the_oldest_sibling_decides_not_the_newest` and
    # `test_one_fresh_artifact_does_not_mask_a_stale_sibling`. They are about
    # VARIANT arrays — `x.spoken.tiddlers.json`, the translated projection —
    # not about the pre-rename predecessors 558 deleted. Every variant is a
    # projection of the same model and they must all be current TOGETHER, so
    # `artifact_current` takes min(mtime) on purpose and a fresh main array
    # must not mask a stale spoken one.
    #
    # "Which file is this document's array" and "are all its projections
    # current" are different questions. Only the first one was globbing for
    # want of an answer.
    try:
        arts = list(Path(blob_dir).glob("*.tiddlers.json"))
    except OSError:
        return False
    return artifact_current(arts, model_path)


def has_compare(blob_dir: Path, model_path: Path) -> bool:
    """`compare.html` is the LaTeX | KaTeX | image surface a human reads to
    judge whether the maths is right. Stale, it shows a VERDICT about a model
    that no longer exists — so presence alone is not enough."""
    p = Path(blob_dir) / "compare.html"
    return artifact_current([p], model_path) if p.exists() else False


# The layer -> (fact, evidence counters) contract, for U2's retraction.
LAYERS: dict[str, dict] = {
    "bibliography": {"fact": "BIBLIOGRAPHY_BUILT", "rebuild": "bibliography",
                     "evidence": ("bibliography_entries", "bibliography_cites",
                                  "bibliography_with_year",
                                  "bibliography_numeric_citations",
                                  "bibliography_authoryear_citations")},
    "geometry": {"fact": "GEOMETRY_FUSED", "rebuild": "geometry",
                 "evidence": ("geometry_matched", "geometry_mean_sim",
                              "geometry_pdf_lines")},
    "tiddlers": {"fact": "TIDDLERS_BUILT", "rebuild": "tiddlers",
                 "evidence": ("tiddlers_count", "tiddlers_path",
                              "tiddlers_svg_mode")},
    "compare": {"fact": "COMPARE_BUILT", "rebuild": "compare",
                "evidence": ("compare_path", "compare_rows")},
    # no fact of its own — evidence only
    "svg": {"fact": None, "rebuild": "svg",
            "evidence": ("svg_rendered", "svg_errors", "svg_skipped", "svg_present")},
    # neither fact nor evidence; detectable, and that is what status needs
    "expandmath": {"fact": None, "rebuild": "expandmath", "evidence": ()},
}


def present(layer: str, doc: Any, blob_dir: Optional[Path] = None,
            model_path: Optional[Path] = None) -> bool:
    """Dispatch to the detector for `layer`. Projections need their paths."""
    if layer == "bibliography":
        return has_bibliography(doc)
    if layer == "geometry":
        return has_geometry(doc)
    if layer == "svg":
        return has_svg(doc)
    if layer == "expandmath":
        return has_expanded_math(doc)
    if layer == "tiddlers":
        return bool(blob_dir) and has_tiddlers(blob_dir, model_path)
    if layer == "compare":
        return bool(blob_dir) and has_compare(blob_dir, model_path)
    raise KeyError(f"no detector for layer {layer!r}")


def retract_absent_layers(doc: Any, sc: Any, blob_dir: Optional[Path],
                          model_path: Optional[Path]) -> list[str]:
    """Drop the fact and evidence counters of every layer that is no longer there.

    Called after a DESTRUCTIVE rebuild. It does not re-derive and it does not
    warn-and-continue: a fact that outlives its layer is read by the planner as
    "done", so the layer is never rebuilt and `status` reports nothing wrong.
    `BIBLIOGRAPHY_BUILT` survived the destruction of all 40 References on
    1706.03762 exactly this way.

    Returns the layer names retracted, so the caller can name them and the
    command that rebuilds each.
    """
    retracted: list[str] = []
    for layer, spec in LAYERS.items():
        try:
            if present(layer, doc, blob_dir, model_path):
                continue
        except Exception:
            continue                       # a detector must never end a rebuild
        touched = False
        fact = spec.get("fact")
        if fact:
            try:
                if fact in getattr(sc, "facts", set()):
                    sc.remove_fact(fact)
                    touched = True
            except Exception:
                pass
        for key in spec.get("evidence", ()):
            try:
                if key in getattr(sc, "evidence", {}):
                    del sc.evidence[key]
                    touched = True
            except Exception:
                pass
        if touched:
            retracted.append(layer)
    if retracted:
        # Remember WHAT was dropped. After retraction the facts are gone, so
        # status can no longer tell "never built" from "destroyed by a rebuild"
        # — and those need different words. Cleared per layer as each returns.
        try:
            prev = list(sc.get_evidence("retracted_layers") or [])
        except Exception:
            prev = []
        sc.set_evidence("retracted_layers", sorted(set(prev) | set(retracted)))
    return retracted


def still_retracted(sc: Any, doc: Any, blob_dir: Optional[Path],
                    model_path: Optional[Path]) -> list[str]:
    """Layers a rebuild dropped that are STILL absent — what status should say.

    Filtered by the live detector, so a layer drops off the list the moment its
    command re-runs, without anyone having to remember to clear the record.
    """
    try:
        recorded = list(sc.get_evidence("retracted_layers") or [])
    except Exception:
        return []
    out = []
    for layer in recorded:
        if layer not in LAYERS:
            continue
        try:
            if not present(layer, doc, blob_dir, model_path):
                out.append(layer)
        except Exception:
            continue
    return out


def rebuild_hint(layers: Iterable[str]) -> str:
    """`layer (pdfdrill <cmd>)`, … — the layer AND how to get it back."""
    parts = [f"{n} (pdfdrill {LAYERS[n]['rebuild']})" for n in layers if n in LAYERS]
    return ", ".join(parts)
