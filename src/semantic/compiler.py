"""
Phase D — the semantic compiler / validator.

Deterministic gate over a SemanticGraph. It does the work a prompt cannot be
trusted to do reliably:

  * type-check every relation against a signature table (subject/object types);
  * verify grounding — a cited evidence_text must actually occur in the cited
    block (this is pdfdrill's edge over a raw LLM run: it HAS the OCR text);
  * detect dangling references (edge to a missing entity);
  * detect derived_from cycles (provenance must be a DAG);
  * flag contradictory functional relations (a document with two issuers).

Returns validity + graded warnings. Pure (graph in, result out); blocks optional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .entity import EntityType
from .graph import SemanticGraph
from .relation import RelationType

# ---- type sets ------------------------------------------------------------
ALL = set(EntityType)
AGENT = {EntityType.PERSON, EntityType.COMPANY, EntityType.ORGANIZATION,
         EntityType.AUTHORITY, EntityType.BANK, EntityType.DEPARTMENT}
DOC = {EntityType.DOCUMENT, EntityType.PAPER}
SCI = {EntityType.CONCEPT, EntityType.FORMULA}

# predicate -> (allowed subject types, allowed object types)
SIGNATURE_TABLE: dict[RelationType, tuple[set, set]] = {
    RelationType.CITES: (DOC, DOC | {EntityType.CITATION}),
    # provenance is for ARTIFACTS, not only documents: image_source edges
    # (IMAGE derived_from IMAGE), kitem chains (KITEM derived_from KITEM),
    # formula/table derivations.
    RelationType.DERIVED_FROM: (DOC | SCI | {EntityType.KITEM, EntityType.IMAGE,
                                             EntityType.TABLE},
                                DOC | SCI | {EntityType.KITEM, EntityType.IMAGE,
                                             EntityType.TABLE}),
    RelationType.EXPLAINS: (DOC | SCI, SCI),
    RelationType.CONTAINS: (DOC, ALL),
    RelationType.CONTRADICTS: (ALL, ALL),
    RelationType.IMPLEMENTS: (ALL, SCI),
    RelationType.OWNS: (AGENT, {EntityType.BANK_ACCOUNT}),
    RelationType.SENDER: (DOC, AGENT),
    RelationType.RECEIVER: (DOC, AGENT),
    RelationType.REPRESENTED_BY: ({EntityType.COMPANY, EntityType.ORGANIZATION,
                                   EntityType.AUTHORITY}, {EntityType.PERSON}),
    RelationType.ACTS_FOR: ({EntityType.PERSON},
                            {EntityType.COMPANY, EntityType.ORGANIZATION, EntityType.AUTHORITY}),
    RelationType.PUBLISHES: (AGENT, DOC),
    RelationType.BELONGS_TO: ({EntityType.BANK_ACCOUNT}, AGENT),
    RelationType.ISSUED_BY: (DOC, AGENT),
    RelationType.SENT_TO: (DOC, AGENT),
    RelationType.HAS_ATTACHMENT: (DOC, DOC),
    RelationType.REFERENCES: (DOC, ALL),
    # quantitative layer (S4.1): concepts/sections/documents measure quantities;
    # a quantity can hold under another quantity (R@P under P=0.9)
    RelationType.MEASURES: (SCI | DOC, {EntityType.QUANTITY}),
    RelationType.UNDER_CONDITION: ({EntityType.QUANTITY}, {EntityType.QUANTITY}),
}

# predicates that may hold at most ONE object per subject
FUNCTIONAL = {RelationType.ISSUED_BY}


@dataclass
class Warning:
    severity: str      # critical | warning | info
    code: str
    message: str


@dataclass
class CompileResult:
    validity: str
    warnings: list[Warning] = field(default_factory=list)

    def critical(self) -> list[Warning]:
        return [w for w in self.warnings if w.severity == "critical"]

    def to_dict(self) -> dict[str, Any]:
        return {"validity": self.validity,
                "warnings": [{"severity": w.severity, "code": w.code,
                              "message": w.message} for w in self.warnings]}


# ---- individual checks ----------------------------------------------------

def check_dangling(graph: SemanticGraph) -> list[Warning]:
    out = []
    for r in graph.relations:
        for side, eid in (("subject", r.subject_id), ("object", r.object_id)):
            if graph.get(eid) is None:
                out.append(Warning("critical", "dangling_reference",
                                   f"{r.predicate.value} {side} '{eid}' is not in the graph"))
    return out


def typecheck(graph: SemanticGraph) -> list[Warning]:
    out = []
    for r in graph.relations:
        # LAYER edges (G3 occurrences on the REFERENCES carrier, kitem
        # derivations) are positional/structural, not domain assertions —
        # the predicate signature does not apply to them.
        if (r.grounding or {}).get("layer") in ("occurrence", "kitem_derivation"):
            continue
        s, o = graph.get(r.subject_id), graph.get(r.object_id)
        if s is None or o is None:
            continue                      # reported by check_dangling
        sig = SIGNATURE_TABLE.get(r.predicate)
        if sig is None:
            out.append(Warning("info", "unknown_predicate",
                               f"no signature for predicate '{r.predicate.value}'"))
            continue
        subs, objs = sig
        if s.type not in subs:
            out.append(Warning("critical", "type_violation",
                               f"{r.predicate.value}: subject {s.id} is {s.type.value}, "
                               f"not one of {sorted(t.value for t in subs)}"))
        if o.type not in objs:
            out.append(Warning("critical", "type_violation",
                               f"{r.predicate.value}: object {o.id} is {o.type.value}, "
                               f"not one of {sorted(t.value for t in objs)}"))
    return out


def check_acyclic(graph: SemanticGraph,
                  predicate: RelationType = RelationType.DERIVED_FROM) -> list[Warning]:
    edges: dict[str, list[str]] = {}
    for r in graph.relations:
        if r.predicate == predicate:
            edges.setdefault(r.subject_id, []).append(r.object_id)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(n: str) -> bool:
        color[n] = GREY
        for m in edges.get(n, []):
            if color.get(m, WHITE) == GREY:
                return True
            if color.get(m, WHITE) == WHITE and visit(m):
                return True
        color[n] = BLACK
        return False

    for node in list(edges):
        if color.get(node, WHITE) == WHITE and visit(node):
            return [Warning("critical", "cycle",
                            f"{predicate.value} relations contain a cycle (must be a DAG)")]
    return []


def verify_grounding(graph: SemanticGraph,
                     blocks: Optional[dict[str, str]]) -> list[Warning]:
    if not blocks:
        return []
    out = []
    for e in graph.entities.values():
        for ev in e.evidence:
            g = ev.grounding or {}
            txt = g.get("evidence_text")
            bid = g.get("block_id")
            if not txt or not bid:
                continue
            block = blocks.get(bid)
            if block is None or txt not in block:
                out.append(Warning("warning", "grounding_unsupported",
                                   f"{e.id}.{ev.prop}: grounding '{txt}' not found in "
                                   f"block '{bid}'"))
    return out


def check_provenance(graph: SemanticGraph) -> list[Warning]:
    """Every `produced_by` value should reference a registered `Question`. This
    is the reified-pass migration check: severity `info` (NOT critical) so it
    never invalidates a graph — it only surfaces a process that emitted evidence
    or edges without a registered intent."""
    from . import question
    out = []
    seen: set[str] = set()

    def check(pb: str) -> None:
        if pb and pb not in seen and question.get(pb) is None:
            seen.add(pb)
            out.append(Warning("info", "unregistered_question",
                               f"produced_by '{pb}' has no registered Question"))

    for e in graph.entities.values():
        for ev in e.evidence:
            check(ev.produced_by)
    for r in graph.relations:
        check(r.produced_by)
    return out


def check_contradictions(graph: SemanticGraph) -> list[Warning]:
    out = []
    seen: dict[tuple, set] = {}
    for r in graph.relations:
        if r.predicate in FUNCTIONAL:
            seen.setdefault((r.subject_id, r.predicate), set()).add(r.object_id)
    for (subj, pred), objs in seen.items():
        if len(objs) > 1:
            out.append(Warning("warning", "contradiction",
                               f"{subj} has {pred.value} to multiple objects "
                               f"{sorted(objs)} (functional — expected one)"))
    return out


# ---- the compiler ---------------------------------------------------------

def compile(graph: SemanticGraph,
            blocks: Optional[dict[str, str]] = None) -> CompileResult:
    warnings: list[Warning] = []
    warnings += check_dangling(graph)
    warnings += typecheck(graph)
    warnings += check_acyclic(graph)
    warnings += verify_grounding(graph, blocks)
    warnings += check_contradictions(graph)
    warnings += check_provenance(graph)
    validity = "invalid" if any(w.severity == "critical" for w in warnings) else "valid"
    return CompileResult(validity=validity, warnings=warnings)
