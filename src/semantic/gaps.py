"""
Gap detection — "cohomology as a linter".

Where `compiler.py` validates what IS in the graph (type signatures,
grounding, cycles), this pass reports what is MISSING: the failures of
local-to-global gluing, surfaced as actionable diagnostics — never
exceptions. Four rules (all pure queries over the docmodel; the concept
producers in `concepts.py` supply the declaration/use split):

  acronym_undefined    an acronym-like token is USED (>=2x) but never expanded
                       (no Schwartz-Hearst long form, no glossary entry)
  symbol_undefined     a greek symbol appears in display math but has no
                       notation/glossary declaration
  claim_unsupported    a novelty/contribution sentence carries no citation
  citation_unmatched   an in-text citation resolves to no Reference

Each gap: {kind, severity (3=high..1=low), name, detail, locations:[{page,
section_id|object_id}]}. `report(gaps)` renders prose, most severe first.
"""
from __future__ import annotations

import re
from typing import Any

from . import concepts as _concepts

_GREEK = ("alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|iota|kappa"
          "|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega"
          "|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega")
_GREEK_CMD = re.compile(r"\\(" + _GREEK + r")\b")

_CLAIM = re.compile(
    r"(?i)\b(we (propose|introduce|present)|novel|outperform\w*|state[- ]of[- ]the[- ]art"
    r"|first (to|time)|our (method|approach|model) (is|achieves))\b")
_HAS_CITE = re.compile(r"\\cite[tp]?\{[^}]+\}|\[\d{1,3}(?:[,–-]\s*\d{1,3})*\]"
                       r"|\(\s*[A-Z][A-Za-zÀ-ÿ'-]+[^)]*\d{4}\s*\)")


def _loc(props: dict) -> dict:
    return {"page": props.get("page"), "section_id": props.get("parent_section")}


def detect_gaps(doc) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    # 1. acronyms used but never expanded/declared
    for u in _concepts.undefined_concept_uses(doc):
        out.append({
            "kind": "acronym_undefined", "severity": 2, "name": u["name"],
            "detail": (f"'{u['name']}' is used {len(u['occurrences'])}x but no "
                       f"expansion/definition was found — add one at first use "
                       f"or in an Acronyms section."),
            "locations": u["occurrences"][:5],
        })

    # 2. greek symbols in display math with no notation/glossary declaration
    declared = {r["name"].lower() for r in _concepts.concept_records(doc)
                if r["kind"] == "symbol"}
    sym_sites: dict[str, list[dict]] = {}
    for o in doc.objects.values():
        if o.type not in ("Equation", "Formula"):
            continue
        latex = o.props.get("latex") or o.props.get("latex_original") or ""
        for m in _GREEK_CMD.finditer(latex):
            name = m.group(1)
            if name.lower() in declared:
                continue
            sym_sites.setdefault(name, []).append(
                {"page": o.props.get("page"), "object_id": o.id})
    has_notation_section = any(
        _concepts._section_kind(o.props.get("caption") or "") == "symbol"
        for o in doc.objects.values() if o.type == "Section")
    for name, sites in sorted(sym_sites.items()):
        out.append({
            "kind": "symbol_undefined", "severity": 1 + (1 if has_notation_section else 0),
            "name": name,
            "detail": (f"\\{name} appears in {len(sites)} equation(s) with no "
                       f"notation/glossary declaration"
                       + (" (the document HAS a notation section — add it there)."
                          if has_notation_section else ".")),
            "locations": sites[:5],
        })

    # 3. novelty/contribution claims without any citation in the sentence/par.
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        if _CLAIM.search(text) and not _HAS_CITE.search(text):
            out.append({
                "kind": "claim_unsupported", "severity": 3,
                "name": _CLAIM.search(text).group(0),
                "detail": ("a novelty/contribution claim carries no citation: "
                           f"“{text[:120]}…”"),
                "locations": [_loc(o.props)],
            })

    # 4. in-text citations that resolve to no Reference
    ref_keys = set()
    ref_nums = set()
    for o in doc.objects.values():
        if o.type == "Reference":
            if o.props.get("citekey"):
                ref_keys.add(str(o.props["citekey"]).lower())
            if o.props.get("number") is not None:
                ref_nums.add(o.props["number"])
    for o in doc.objects.values():
        if o.type != "Citation":
            continue
        key = (o.props.get("citekey") or "").lower()
        num = o.props.get("reference_number")
        if num is None:
            num = o.props.get("number")
        # cited_reference_id is the authoritative marker set by the linkers
        # (bibliography/bibsource/markdown) — trust it before key matching.
        matched = (bool(o.props.get("cited_reference_id"))
                   or (key and key in ref_keys)
                   or (num is not None and num in ref_nums))
        if not matched:
            out.append({
                "kind": "citation_unmatched", "severity": 2,
                "name": o.props.get("citekey") or f"[{num}]",
                "detail": "an in-text citation resolves to no bibliography entry.",
                "locations": [_loc(o.props)],
            })

    out.sort(key=lambda g: (-g["severity"], g["kind"], str(g["name"])))
    return out


def report(gaps: list[dict[str, Any]]) -> str:
    if not gaps:
        return "No gaps detected (acronyms, symbols, claims, citations all resolve)."
    by_kind: dict[str, int] = {}
    for g in gaps:
        by_kind[g["kind"]] = by_kind.get(g["kind"], 0) + 1
    head = (f"{len(gaps)} gap(s): "
            + ", ".join(f"{v} {k}" for k, v in sorted(by_kind.items())))
    lines = [head, ""]
    for g in gaps:
        locs = ", ".join(f"p{l.get('page')}" for l in g["locations"]
                         if l.get("page") is not None) or "-"
        lines.append(f"  [{'!' * g['severity']:3}] {g['kind']}: {g['name']} "
                     f"({locs}) — {g['detail']}")
    return "\n".join(lines)
