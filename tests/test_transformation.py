"""
Transformation (src/semantic/transformation.py): one process INVOCATION reified
as a content-addressed provenance node (a KnowledgeCommit). tid is a content
hash over (qid, model, version, sorted source content-hashes) — deliberately
EXCLUDING timestamp/cost/responses, so re-running the same invocation on the
same inputs is a fixpoint no-op (same tid, found not minted). Stored on the
SemanticGraph (not as Relations — they are many→many hyperedges), persisted, and
its tid is stamped into the grounding of the evidence/relations it produced.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.entity import EntityType
from semantic import transformation as T
from semantic import compiler, build


def test_content_address_stable_and_ignores_timestamp_cost_responses():
    g = SemanticGraph()
    r = IdentityResolver(g)
    a = r.resolve(EntityType.FORMULA, keys=[("content_hash", "h1")],
                  evidence=[__import__("semantic.evidence", fromlist=["Evidence"]).Evidence(
                      "s", "content_hash", "h1", "mathpix")])
    t1 = T.make(g, "claims_v1", source_ids=[a.id], target_ids=[a.id], model="sonar")
    t2 = T.make(g, "claims_v1", source_ids=[a.id], target_ids=[a.id], model="sonar",
                timestamp="2026-01-01", cost=9.9, responses=["raw"])
    assert t1.tid == t2.tid                                  # ts/cost/responses excluded
    t3 = T.make(g, "claims_v1", source_ids=[a.id], target_ids=[a.id], model="ner")
    assert t3.tid != t1.tid                                  # model IS part of the hash


def test_record_transformation_idempotent():
    g = SemanticGraph()
    t = T.make(g, "docmodel", source_ids=[], seed="docA")
    g.record_transformation(t)
    g.record_transformation(T.make(g, "docmodel", source_ids=[], seed="docA"))
    assert len(g.transformations) == 1


def test_graph_roundtrip_persists_transformations():
    g = SemanticGraph()
    g.record_transformation(T.make(g, "docmodel", source_ids=[], seed="docA",
                                   model="m", target_ids=["x"]))
    g2 = SemanticGraph.from_dict(g.to_dict())
    assert list(g2.transformations) == list(g.transformations)
    (a,), (b,) = g.transformations.values(), g2.transformations.values()
    assert a.to_dict() == b.to_dict()


def test_ingest_document_twice_identical_transformations():
    g = SemanticGraph()
    r = IdentityResolver(g)
    build.ingest_document(g, r, source="docX", sender="ACME GmbH")
    snap1 = {tid: t.to_dict() for tid, t in g.transformations.items()}
    build.ingest_document(g, r, source="docX", sender="ACME GmbH")   # re-ingest
    snap2 = {tid: t.to_dict() for tid, t in g.transformations.items()}
    for d in list(snap1.values()) + list(snap2.values()):
        d.pop("timestamp", None)
    assert snap1 == snap2                                    # identical modulo timestamp
    assert len(g.transformations) >= 1
    # the produced relations carry the invocation tid in grounding["trans"]
    assert any((rel.grounding or {}).get("trans") for rel in g.relations)
    assert compiler.compile(g).validity == "valid"          # gate stays green


def test_targets_traceable_to_invocation():
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = build.ingest_document(g, r, source="docY", sender="Beta AG")
    # the document entity is a target of the recorded ingest transformation
    assert any(doc.id in t.target_ids for t in g.transformations.values())


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
