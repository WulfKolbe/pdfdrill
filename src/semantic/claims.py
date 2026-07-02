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


def extract_qclaims(doc, bibkey: str) -> list[dict]:
    """S4.3, kind `qclaim`: a sentence carrying a bound Measurement
    (`props['meas']` from the measurement pass) becomes a quantitative claim.
    Each record keeps the bound quantity record + its FO node so the fixpoint
    pass can gate promotion on the verifier's outcome."""
    out = []
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        for m in (o.props.get("meas") or []):
            span = m.get("sentence_span") or [0, 0]
            sent = text[span[0]:span[1]]
            stmt = _statement(sent)
            if len(stmt) < 15:
                continue
            qref = m.get("quantity_ref") or {}
            fo = doc.objects.get(qref.get("obj_id") or "")
            quant = None
            if fo is not None:
                ql = fo.props.get("quant") or []
                idx = qref.get("idx", 0)
                quant = ql[idx] if idx < len(ql) else None
            out.append({"statement_md": stmt, "kind": "qclaim", "node": o.id,
                        "page": o.props.get("page"),
                        "fo_node": qref.get("obj_id"),
                        "quant": quant,
                        "flow_index": o.props.get("flow_index")})
    return out


def _quantity_entity(graph, resolver, qrec: dict, fo_node: str):
    """The QUANTITY entity the ingest minted for this record, or None."""
    from .entity import EntityType
    from .build import quantity_content_key
    from .layers.content_identity import content_hash
    h = content_hash(quantity_content_key({**(qrec or {}), "obj_id": fo_node}))
    return resolver.find_existing_entity(EntityType.QUANTITY,
                                         [("content_hash", h)])


def make_claims_pass(doc, bibkey: str):
    """A (graph, resolver) pass for the fixpoint driver: emit one kitem per
    extracted claim/definition/qclaim, evidence = the span into the docmodel.

    qclaim promotion rule (the honesty gate, expressed WITHIN the status
    lattice — its semantics untouched): a qclaim with a CHECKABLE derivation
    gets its spans only once the verifier has landed a `verifies` Evidence row
    on the bound Quantity — until then it stays span-less (`proposed`); the
    next fixpoint round after verification attaches the spans (same kitem,
    found by content hash) and the status rises. A `refutes` row forces
    `disputed` via the sanctioned CONTRADICTS mechanism — demotion only."""
    extracted = extract_claims(doc, bibkey)
    q_extracted = extract_qclaims(doc, bibkey)

    def claims_pass(graph, resolver):
        from . import transformation as _trans
        from .relation import RelationType
        snap = _trans.snapshot(graph)
        for c in extracted:
            _kitems.emit_kitem(
                graph, resolver, c["statement_md"], kind=c["kind"], stratum=4,
                spans=[{"bibkey": bibkey, "node": c["node"],
                        "range": c["range"], "role": "asserts",
                        "page": c["page"]}],
                produced_by="claims_v1")
        for c in q_extracted:
            q = c.get("quant") or {}
            checkable = q.get("kind") == "derivation" and q.get("payload")
            qent = _quantity_entity(graph, resolver, q, c.get("fo_node") or "")
            verified = refuted = False
            if qent is not None:
                for ev in qent.evidence:
                    if ev.produced_by == "arith":
                        verified |= ev.prop == "verifies"
                        refuted |= ev.prop == "refutes"
            spans = []
            if not checkable or verified or refuted:    # the promotion gate
                spans = [{"bibkey": bibkey, "node": c["node"], "range": "",
                          "role": "asserts", "page": c["page"]}]
                if c.get("fo_node"):
                    spans.append({"bibkey": bibkey, "node": c["fo_node"],
                                  "range": "", "role": "measures",
                                  "page": c["page"]})
            k = _kitems.emit_kitem(
                graph, resolver, c["statement_md"], kind="qclaim", stratum=4,
                spans=spans, produced_by="claims_v1")
            if refuted and qent is not None and \
                    not graph.has_relation(qent.id, RelationType.CONTRADICTS, k.id):
                graph.relate_once(qent.id, RelationType.CONTRADICTS, k.id,
                                  produced_by="arith")
        # group this invocation's kitems under one Transformation; doc-specific
        # via `seed=bibkey` (no entity sources). Idempotent + a fixpoint no-op on
        # later rounds: same tid (found, not re-recorded), and stamping only
        # touches grounding (never evidence counts → quiescence is preserved).
        _trans.record_batch(graph, "claims_v1", snap, seed=bibkey)
    return claims_pass
