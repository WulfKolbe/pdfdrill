"""
Question registry (src/semantic/question.py): reify each pass — the reusable
definition of what a sensor/LLM invocation is FOR, decoupled from any single
run. `Evidence.produced_by` / `Relation.produced_by` are now references to a
Question.qid (still plain strings — additive). Every existing produced_by value
must resolve to a registered Question, and the compiler warns (severity=info,
never critical) on an unregistered one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import question as Q
from semantic.entity import EntityType
from semantic.relation import RelationType
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic import compiler


_EXISTING = ["bib", "cite", "claims_v1", "concepts", "docmodel", "iban", "ner", "segment"]


def test_every_existing_produced_by_is_registered():
    for qid in _EXISTING:
        q = Q.get(qid)
        assert q is not None, f"{qid} not registered"
        assert q.qid == qid


def test_register_and_get_roundtrip():
    q = Q.Question(qid="test_pass", description="a test pass",
                   prompt_version="v1",
                   emits_entities=frozenset({EntityType.CONCEPT}),
                   emits_relations=frozenset({RelationType.CONTAINS}),
                   stratum=4)
    Q.register(q)
    assert Q.get("test_pass") is q
    d = q.to_dict()
    q2 = Q.Question.from_dict(d)
    assert q2 == q                                    # frozen dataclass round-trip
    assert q2.emits_entities == {EntityType.CONCEPT}


def test_question_is_frozen_and_hashable():
    q = Q.get("docmodel")
    assert hash(q) is not None                         # frozen -> hashable
    try:
        q.qid = "x"; assert False, "should be frozen"
    except Exception:
        pass


def test_compiler_warns_info_on_unregistered_produced_by():
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = r.resolve(EntityType.DOCUMENT, evidence=[])
    # a relation produced by an UNregistered question id
    g.relate(doc.id, RelationType.CONTAINS, doc.id, produced_by="mystery_pass")
    res = compiler.compile(g)
    provs = [w for w in res.warnings if w.code == "unregistered_question"]
    assert provs and all(w.severity == "info" for w in provs)
    assert any("mystery_pass" in w.message for w in provs)
    # critical count is unaffected -> graph still valid w.r.t. provenance
    assert all(w.severity != "critical" for w in provs)


def test_compiler_no_provenance_warning_for_registered():
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = r.resolve(EntityType.DOCUMENT, evidence=[])
    g.relate(doc.id, RelationType.CONTAINS, doc.id, produced_by="docmodel")
    res = compiler.compile(g)
    assert not [w for w in res.warnings if w.code == "unregistered_question"]


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
