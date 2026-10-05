"""879, Phase 0 — IS OUR lines.json MATHPIX-SHAPED? Measured, not asserted.

pdf2mmd is to become a complete replacement for MathPix, emitting a fully
compatible `lines.json`. Nothing in this repository could say how far from
that it is. "Full compatible" was an opinion, and an opinion about a 31-type
vocabulary is not something anyone can act on.

So this is the first thing built, before any feature: take a document for
which we hold BOTH a MathPix reading and our own, and report, per line type
and per line field, what MathPix emits that we do not.

WHAT IT COMPARES, AND WHAT IT DELIBERATELY DOES NOT. It compares
DISTRIBUTIONS — how many lines of each type, which fields ever appear — and
not lines one-to-one. The two readers segment differently (1,068 lines against
967 on the same 26 pages), so a 1:1 alignment would be a region-overlap
matching with its own thresholds and its own failure modes, and every number
it produced would carry them. A type the reference emits 55 times and we emit
zero times is a fact that needs no threshold. Alignment is worth building
later, to ask "is THIS line right"; it is the wrong instrument for "do we
speak the vocabulary at all".

OUR READING IS BUILT IN MEMORY, from the PDF, every time. It is not read from
disk: the on-disk `lines.json` for a document with a MathPix backup is
whatever last wrote it — MathPix, visionocr, or us — and comparing the
reference against an unknown is not a measurement. Nothing here writes a
`lines.json`; a conformance check that modified the thing it checks would be
the worst kind of instrument.

THE REFERENCE IS MATHPIX AND MATHPIX IS NOT TRUTH. It is the richest reading
available and the target for compatibility, which is a different claim. A type
we do not emit is a gap in compatibility; it is not necessarily an error in
our reading, and this module never says it is.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

#: A line type MathPix emits. Not a closed set — it is whatever the references
#: we hold actually contain, which is the only honest definition available.
#: Recorded per run so the vocabulary grows with the evidence rather than with
#: a guess about what MathPix might emit elsewhere.


def _lines(doc: dict):
    for page in doc.get("pages") or []:
        for line in page.get("lines") or []:
            if isinstance(line, dict):
                yield line


def profile(doc: dict) -> dict:
    """{types: Counter, fields: Counter, lines: int, pages: int} for a reading."""
    types: collections.Counter = collections.Counter()
    fields: collections.Counter = collections.Counter()
    n = 0
    for line in _lines(doc):
        n += 1
        types[line.get("type")] += 1
        for k in line:
            fields[k] += 1
    return {"types": types, "fields": fields, "lines": n,
            "pages": len(doc.get("pages") or [])}


def compare(reference: dict, ours: dict) -> dict:
    """What the reference emits that we do not. Pure; no I/O."""
    ref, mine = profile(reference), profile(ours)
    missing_types = {t: n for t, n in ref["types"].items()
                     if t and not mine["types"].get(t)}
    shared_types = sorted(t for t in ref["types"] if t and mine["types"].get(t))
    extra_types = {t: n for t, n in mine["types"].items()
                   if t and not ref["types"].get(t)}
    missing_fields = {f: n for f, n in ref["fields"].items()
                      if not mine["fields"].get(f)}
    extra_fields = {f: n for f, n in mine["fields"].items()
                    if not ref["fields"].get(f)}
    ref_types = [t for t in ref["types"] if t]
    # COVERAGE PER SHARED TYPE, because "the type is emitted" and "the type is
    # covered" are different claims and the first one hides the second.
    # Measured the moment this was needed: emitting `equation_number` moved the
    # headline from 8 of 18 to 9 of 18 while finding 13 of the reference's 40.
    # A tick in the type column would have read as finished.
    coverage = {}
    for t in shared_types:
        r, m = ref["types"][t], mine["types"][t]
        coverage[t] = {"reference": r, "ours": m,
                       "ratio": round(m / r, 3) if r else None}
    thin = {t: v for t, v in coverage.items()
            if v["ratio"] is not None and v["ratio"] < 0.5}
    return {
        "reference": {"pages": ref["pages"], "lines": ref["lines"],
                      "types": len(ref_types)},
        "coverage": coverage,
        "thin_types": dict(sorted(thin.items(), key=lambda kv: kv[1]["ratio"])),
        "ours": {"pages": mine["pages"], "lines": mine["lines"],
                 "types": len([t for t in mine["types"] if t])},
        "types_covered": len(shared_types),
        "types_in_reference": len(ref_types),
        "shared_types": shared_types,
        "missing_types": dict(sorted(missing_types.items(),
                                     key=lambda kv: -kv[1])),
        "extra_types": dict(sorted(extra_types.items(), key=lambda kv: -kv[1])),
        "missing_fields": dict(sorted(missing_fields.items(),
                                      key=lambda kv: -kv[1])),
        "extra_fields": dict(sorted(extra_fields.items(),
                                    key=lambda kv: -kv[1])),
    }


def reference_for(pdf: Path) -> "Path | None":
    """The MathPix reading for this document, or None.

    `<stem>.lines.mathpix.bak.json` is where 845 parks a MathPix reading that a
    free reader displaced. A live `lines.json` counts only when it is MathPix's
    own — which is what the ABSENCE of the `source` key means, since 846 added
    that key and only our reader writes it.
    """
    stem = pdf.with_suffix("")
    bak = stem.parent / (stem.name + ".lines.mathpix.bak.json")
    if bak.exists():
        return bak
    live = stem.parent / (stem.name + ".lines.json")
    if live.exists():
        try:
            d = json.load(open(live, encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            return None
        src = str(d.get("source") or "")
        if not src or src.startswith("mathpix"):
            # No `source` at all is ambiguous: it is either MathPix, or one of
            # our own readings from before 846 added the key. The line FIELDS
            # settle it — ours carries `deferred_glyphs`, which MathPix has no
            # concept of.
            for line in _lines(d):
                if "deferred_glyphs" in line or "gaps" in line:
                    return None
            return live
    return None


def render(result: dict, name: str) -> str:
    r = result
    out = [
        f"conformance: {name} — {r['types_covered']} of "
        f"{r['types_in_reference']} MathPix line types emitted",
        f"  reference  {r['reference']['pages']} pages, "
        f"{r['reference']['lines']} lines, {r['reference']['types']} types",
        f"  ours       {r['ours']['pages']} pages, {r['ours']['lines']} lines, "
        f"{r['ours']['types']} types",
    ]
    if r.get("thin_types"):
        out.append("  THINLY COVERED (the type is emitted; most of its lines "
                   "are not found):")
        for t, v in r["thin_types"].items():
            out.append(f"    {v['ours']:6d} of {v['reference']:<6d} "
                       f"({v['ratio']:.0%})  {t}")
    if r["missing_types"]:
        out.append("  MISSING TYPES (the reference emits these, we emit none):")
        for t, n in r["missing_types"].items():
            out.append(f"    {n:6d}  {t}")
    if r["missing_fields"]:
        out.append("  MISSING FIELDS:")
        out.append("    " + ", ".join(r["missing_fields"]))
    if r["extra_types"]:
        out.append("  ours only (additive; a MathPix consumer ignores these): "
                   + ", ".join(r["extra_types"]))
    if r["extra_fields"]:
        out.append("  extra fields: " + ", ".join(r["extra_fields"]))
    out.append("  Counts are DISTRIBUTIONS, not an alignment: the two readers "
               "segment differently, so this says whether the vocabulary is "
               "spoken, never whether a given line is right.")
    return "\n".join(out)
