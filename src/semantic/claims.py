"""
Stratum-4 claim extractor — the first kitem producer (two-store plan, step 4).

Deterministic, sentence-level: a Paragraph/ListItem sentence carrying a
novelty/contribution marker becomes a `claim` kitem; a definitional sentence
("X is defined as …") becomes a `definition` kitem. Each kitem's evidence is
the span {bibkey, node (the docmodel object id), range, role=asserts, page} —
the proof pointer the rulebook's drill-down follows back into the document.

The statement is rendered through the `detranscluded` policy (the stratum
contract), so a transcluded placeholder never leaks into a rulebook line.
Emitting is idempotent by content hash — the pass can run inside the fixpoint
driver any number of times.
"""
from __future__ import annotations

import re

from docops.transclusion_render import render as _render
from . import kitems as _kitems

# sentence-ish splitter (good enough for claim harvesting; one shallow line)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")
_WS = re.compile(r"\s+")

_CLAIM = re.compile(
    r"(?i)\b(we (propose|introduce|present)|novel|outperform\w*"
    r"|state[- ]of[- ]the[- ]art|first (to|time)"
    r"|our (method|approach|model|formula) (is|achieves|yields))\b")
_DEFINITION = re.compile(
    r"(?i)\b(is defined (as|by)|we define|is called|denotes"
    r"|ist definiert (als|durch)|bezeichnet|heißt)\b")

_MAX_STATEMENT = 300


def _statement(sentence: str) -> str:
    s = _render(sentence, policy="detranscluded")
    s = _WS.sub(" ", s).strip()
    return s[:_MAX_STATEMENT]


def extract_claims(doc, bibkey: str) -> list[dict]:
    """Pure: [{statement_md, kind, node, page, range, flow_index}] — one entry
    per claim/definition sentence in the prose objects."""
    out = []
    for o in doc.objects.values():
        if o.type not in ("Paragraph", "ListItem"):
            continue
        text = o.props.get("text") or o.props.get("content") or ""
        if not text.strip():
            continue
        rng = ""
        if o.realizations:
            r0 = o.realizations[0]
            if r0.start is not None:
                rng = getattr(r0.start, "id", "") or ""
        for sent in _SENT.split(text):
            kind = None
            if _DEFINITION.search(sent):
                kind = "definition"
            elif _CLAIM.search(sent):
                kind = "claim"
            if kind is None:
                continue
            stmt = _statement(sent)
            if len(stmt) < 15:
                continue
            out.append({"statement_md": stmt, "kind": kind, "node": o.id,
                        "page": o.props.get("page"), "range": rng,
                        "flow_index": o.props.get("flow_index")})
    return out


def make_claims_pass(doc, bibkey: str):
    """A (graph, resolver) pass for the fixpoint driver: emit one kitem per
    extracted claim/definition, evidence = the span into the docmodel."""
    extracted = extract_claims(doc, bibkey)

    def claims_pass(graph, resolver):
        from . import transformation as _trans
        snap = _trans.snapshot(graph)
        for c in extracted:
            _kitems.emit_kitem(
                graph, resolver, c["statement_md"], kind=c["kind"], stratum=4,
                spans=[{"bibkey": bibkey, "node": c["node"],
                        "range": c["range"], "role": "asserts",
                        "page": c["page"]}],
                produced_by="claims_v1")
        # group this invocation's kitems under one Transformation; doc-specific
        # via `seed=bibkey` (no entity sources). Idempotent + a fixpoint no-op on
        # later rounds: same tid (found, not re-recorded), and stamping only
        # touches grounding (never evidence counts → quiescence is preserved).
        _trans.record_batch(graph, "claims_v1", snap, seed=bibkey)
    return claims_pass
