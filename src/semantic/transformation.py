"""
Transformation — a process INVOCATION reified as a content-addressed node
(a "KnowledgeCommit").

`Question` (question.py) is the reusable DEFINITION of a pass; a `Transformation`
is one EXECUTION of it: which entities it consumed, which it produced/touched,
the model/version that ran, and (for replay) the raw responses. Provenance used
to be a bare `produced_by` string with no record of a single invocation — this
closes that gap.

Content address: `tid = content_hash("trans|" + qid + "|" + model + "|" +
version + "|" + "|".join(sorted(source content_hashes)))`, reusing
`layers.content_identity.content_hash`. The hash deliberately EXCLUDES timestamp,
cost and responses, so re-running the same invocation on the same inputs is a
fixpoint no-op — same tid, found-not-minted, exactly like `kitems.emit_kitem`.

Transformations are stored on the `SemanticGraph` in `transformations: {tid:
Transformation}` — NOT as `Relation`s: they are many→many hyperedges (many
sources → many targets) and would break the binary `SIGNATURE_TABLE`. The tid is
stamped into `grounding["trans"]` of the evidence/relations an invocation
produced, so any target traces back to its exact invocation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .layers.content_identity import content_hash


@dataclass
class Transformation:
    tid: str                                   # = content hash (see module docstring)
    qid: str                                   # FK into question.REGISTRY
    source_ids: list[str] = field(default_factory=list)   # entity ids consumed
    target_ids: list[str] = field(default_factory=list)   # entity ids produced/touched
    model: str = ""                            # "mathpix" / "sonar" / "ner" / "" (pure code)
    version: str = ""
    confidence: float = 1.0
    cost: float = 0.0
    timestamp: str = ""                        # iso; NOT part of the hash
    responses: list[str] = field(default_factory=list)    # raw output, for replay
    fns: tuple[str, ...] = ()                  # registry fids composed; NOT in the hash

    def to_dict(self) -> dict[str, Any]:
        return {"tid": self.tid, "qid": self.qid,
                "source_ids": list(self.source_ids), "target_ids": list(self.target_ids),
                "model": self.model, "version": self.version,
                "confidence": self.confidence, "cost": self.cost,
                "timestamp": self.timestamp, "responses": list(self.responses),
                "fns": list(self.fns)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transformation":
        return cls(tid=d["tid"], qid=d.get("qid", ""),
                   source_ids=list(d.get("source_ids", [])),
                   target_ids=list(d.get("target_ids", [])),
                   model=d.get("model", ""), version=d.get("version", ""),
                   confidence=d.get("confidence", 1.0), cost=d.get("cost", 0.0),
                   timestamp=d.get("timestamp", ""),
                   responses=list(d.get("responses", [])),
                   fns=tuple(d.get("fns", ())))


def _entity_content_hash(graph, eid: str) -> str:
    """A STABLE content hash for a source entity — its `content_hash` property if
    it has one (formulas/kitems/documents do), else a hash of type+display value
    (companies/persons). Stable across runs ⇒ stable tid, independent of the
    counter-based entity id."""
    e = graph.get(eid)
    if e is None:
        return eid
    ch = e.properties().get("content_hash")
    return ch or content_hash(f"entity|{e.type.value}|{e.value}")


def compute_tid(qid: str, model: str, version: str, source_hashes: list[str]) -> str:
    payload = ("trans|" + qid + "|" + model + "|" + version + "|"
               + "|".join(sorted(source_hashes)))
    return content_hash(payload)


def make(graph, qid: str, source_ids=(), target_ids=(), *, model: str = "",
         version: str = "", seed: str = "", confidence: float = 1.0,
         cost: float = 0.0, timestamp: str = "",
         responses: Optional[list] = None,
         fns: tuple[str, ...] = ()) -> Transformation:
    """Build a Transformation, computing its content-address `tid` from the
    source entities' content hashes. `seed` folds an extra stable token into the
    hash (e.g. a bibkey) for invocations that have no entity sources, so two
    documents' same-qid passes don't collide on one tid. `fns` records the
    registry fids the invocation composed — provenance only, EXCLUDED from the
    hash (existing tids stay valid)."""
    hashes = [_entity_content_hash(graph, sid) for sid in source_ids]
    if seed:
        hashes.append(content_hash(f"seed|{seed}"))
    tid = compute_tid(qid, model, version, hashes)
    return Transformation(tid=tid, qid=qid, source_ids=list(source_ids),
                          target_ids=list(target_ids), model=model, version=version,
                          confidence=confidence, cost=cost, timestamp=timestamp,
                          responses=list(responses or []), fns=tuple(fns))


# --------------------------------------------------------------------------- #
#  Batch wiring: group one invocation's emitted evidence/edges under a tid.
# --------------------------------------------------------------------------- #

def snapshot(graph) -> tuple[dict[str, int], int]:
    """(per-entity evidence-row counts, #relations) — capture BEFORE an
    invocation so `record_batch` can stamp exactly what it added."""
    return ({eid: len(e.evidence) for eid, e in graph.entities.items()},
            len(graph.relations))


def record_batch(graph, qid: str, snap: tuple[dict[str, int], int], *,
                 source_ids=(), seed: str = "", model: str = "", version: str = "",
                 **kw) -> Transformation:
    """Record ONE invocation that grouped the evidence/edges added since `snap`.
    Targets = entities that gained evidence; the tid is stamped into
    `grounding["trans"]` of each new relation + new evidence row (setdefault — a
    re-run with the same tid never overwrites). Idempotent on tid."""
    ev_snap, rel_start = snap
    targets = sorted(eid for eid, e in graph.entities.items()
                     if len(e.evidence) > ev_snap.get(eid, 0))
    t = make(graph, qid, source_ids, targets, seed=seed, model=model,
             version=version, **kw)
    graph.record_transformation(t)
    for r in graph.relations[rel_start:]:
        g = dict(r.grounding or {})
        g.setdefault("trans", t.tid)
        r.grounding = g
    for eid, e in graph.entities.items():
        for ev in e.evidence[ev_snap.get(eid, 0):]:
            g = dict(ev.grounding or {})
            g.setdefault("trans", t.tid)
            ev.grounding = g
    return t
