"""
SO.MEAS.BIND — bind transcluded quantities to concepts (L6→L7, S2.1).

A MEASUREMENT is a quantity IN CONTEXT: which concept it measures, under which
verb, under which conditions. The tiddler design gives the binding for free —
a materialized Paragraph's text carries `{{<bibkey>_FO0043||FO}}` transclusion
placeholders, each a pre-linked pointer at a Formula object whose
`props['quant']` (the S1.3 pass) already types its quantity. This module walks
those placeholders sentence by sentence and emits

    {concept, concept_source, measure, quantity_ref: {obj_id, idx},
     conditions: {...}, sentence_span, para_id}

Binding rules (conservative — no verb, no record):
  * measure: a verb from the pattern set (achieves / reaches / could add /
    costs / drops to / we set|sampled / contains around / agreement of),
  * concept: the nearest `concepts.concept_records` name in the same sentence,
    else the containing Section's caption (`concept_source` says which),
  * conditions: a ratio quantity in the same sentence PRECEDED by
    precision|accuracy|P= is a CONDITION on the sentence's other measurements
    ("… with an accuracy of {{FO}} …" → conditions={'accuracy': 0.82},
    canonical fraction), never its own measurement.

FO-title → object resolution mirrors the projector's deterministic numbering
(`tiddlywiki._assign_titles`): FO index = 1-based position in the flow-sorted
Formula list — matched on the `_FO(\\d+)` suffix so a bibkey mismatch never
breaks the join.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import units as U
from .concepts import concept_records
from .registry import FnSpec, register_fn

_FO_MARK = re.compile(r"\{\{[^|{}]*_FO(\d+)\|\|FO\}\}")
_MEASURE = re.compile(
    r"(?i)\b(achieves?|reach(?:es)?|could add|costs?|drops? to|"
    r"we (?:set|sampled?)|contains?(?: around| about)?|agreement of)\b")
_COND_KEY = re.compile(r"(?i)\b(precision|accuracy|P)\s*(?:=|of)?\s*$")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) spans over the paragraph text."""
    out, pos = [], 0
    for part in _SENT_SPLIT.split(text):
        start = text.index(part, pos)
        out.append((start, start + len(part), part))
        pos = start + len(part)
    return out


def _fo_by_index(doc) -> dict[int, Any]:
    """1-based FO number → Formula object (the projector's flow-order numbering)."""
    formulas = sorted((o for o in doc.objects.values() if o.type == "Formula"),
                      key=lambda o: o.props.get("flow_index", 10**9))
    return {i + 1: f for i, f in enumerate(formulas)}


def _concept_in_sentence(sentence: str, names: list[str],
                         anchor: int) -> Optional[str]:
    """The concept name whose whole-token match sits nearest to `anchor`."""
    best, best_d = None, None
    for name in names:
        rx = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
        m = rx.search(sentence)
        if m:
            d = abs(m.start() - anchor)
            if best_d is None or d < best_d:
                best, best_d = name, d
    return best


def _section_caption(doc, para) -> Optional[str]:
    sid = para.props.get("parent_section")
    if not sid:
        return None
    sec = doc.objects.get(sid)
    return (sec.props.get("caption") or None) if sec is not None else None


def measurement_records(doc) -> list[dict]:
    """Measurements bound from transcluded quantities, in document order."""
    fo_map = _fo_by_index(doc)
    cnames = [r["name"] for r in concept_records(doc)]
    records: list[dict] = []

    paras = sorted((o for o in doc.objects.values() if o.type == "Paragraph"),
                   key=lambda o: o.props.get("flow_index", 10**9))
    for para in paras:
        text = para.props.get("text") or ""
        if not isinstance(text, str) or "||FO}}" not in text:
            continue
        for s_start, s_end, sent in _sentences(text):
            marks = list(_FO_MARK.finditer(sent))
            if not marks:
                continue
            mv = _MEASURE.search(sent)
            if not mv:                                  # no verb → no binding
                continue
            measure = re.sub(r"\s+", " ", mv.group(1).strip().lower())

            # split the marks: condition ratios vs measured quantities
            conditions: dict[str, float] = {}
            measured: list[tuple[Any, dict]] = []       # (formula, quant record)
            for m in marks:
                fo = fo_map.get(int(m.group(1)))
                quants = (fo.props.get("quant") or []) if fo is not None else []
                if not quants:
                    continue
                q = quants[0]
                lead = sent[:m.start()].rstrip()
                key = _COND_KEY.search(lead[-30:]) if lead else None
                if q.get("kind") == "ratio" and key:
                    kname = key.group(1).lower()
                    kname = "precision" if kname == "p" else kname
                    frac = U.convert(q["value"], q.get("unit") or "%", "")
                    conditions[kname] = frac if frac is not None else q["value"]
                else:
                    measured.append((fo, q))

            if not measured:
                continue
            concept = _concept_in_sentence(sent, cnames, mv.start())
            source = "concept" if concept else None
            if concept is None:
                concept = _section_caption(doc, para)
                source = "section" if concept else None
            for fo, q in measured:
                records.append({
                    "concept": concept, "concept_source": source,
                    "measure": measure,
                    "quantity_ref": {"obj_id": fo.id,
                                     "idx": (fo.props.get("quant") or []).index(q)},
                    "conditions": dict(conditions),
                    "sentence_span": [s_start, s_end],
                    "para_id": para.id,
                })
    return records


register_fn(FnSpec(
    fid="SO.MEAS.BIND",
    description="Bind transcluded quantities to the nearest concept + measure "
                "verb per sentence; keyword-preceded ratios become conditions.",
    version="1",
    params={"measure_verbs": "achieves|reaches|could add|costs|drops to|"
                             "we set|we sampled|contains|agreement of",
            "condition_keys": "precision|accuracy|P="},
    laws=("no-verb-no-record", "conditions-are-not-measurements"),
), measurement_records)
