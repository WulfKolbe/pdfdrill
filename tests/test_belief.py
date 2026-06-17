"""
Derived belief (src/semantic/belief.py) — a REPORT COLUMN, not a source of truth.

Weakest-link belief over the derived_from DAG: belief(node) = min(parent beliefs)
* own_confidence (own_confidence if no parents). It is computed lazily and exposed
only as a projector/proof column — it never feeds the kitems status lattice and
is never stored on an Entity/Evidence that another pass reads.

Prerequisite (deliverable-3 #2): Entity.best() ties are now broken by
deterministic content-hash ordering, not recency — so best() and therefore
belief are reproducible regardless of ingestion order.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.entity import Entity, EntityType
from semantic.evidence import Evidence
from semantic.relation import RelationType
from semantic import belief


def test_belief_min_pure():
    assert belief.belief_min([], 0.8) == 0.8                 # no parents -> own
    assert belief.belief_min([0.9, 0.5, 0.7], 0.8) == 0.5 * 0.8   # weakest link * own
    assert belief.belief_min([1.0], 1.0) == 1.0


def test_best_tiebreak_is_order_independent():
    # two equal-confidence values attached in OPPOSITE orders must yield the
    # same best() — deterministic content-hash tiebreak, not recency
    a = Entity(id="company:1", type=EntityType.COMPANY)
    a.attach(Evidence("d1", "name", "Alpha", "ner", confidence=0.8))
    a.attach(Evidence("d2", "name", "Beta", "ner", confidence=0.8))
    b = Entity(id="company:2", type=EntityType.COMPANY)
    b.attach(Evidence("d2", "name", "Beta", "ner", confidence=0.8))
    b.attach(Evidence("d1", "name", "Alpha", "ner", confidence=0.8))
    assert a.best("name").value == b.best("name").value      # same winner regardless of order


def _build(order):
    """A derived_from chain: leaf <- mid <- top, with own confidences, edges/
    evidence attached in the given `order` of node keys."""
    g = SemanticGraph()
    nodes = {
        "leaf": (EntityType.KITEM, 1.0),
        "mid":  (EntityType.KITEM, 0.9),
        "top":  (EntityType.KITEM, 0.8),
    }
    for k in order:
        et, conf = nodes[k]
        g.add_entity(Entity(id=f"kitem:{k}", type=et,
                            evidence=[Evidence("s", "statement_md", k, "claims_v1",
                                               confidence=conf)]))
    # top derived_from mid derived_from leaf (edges added in `order` too)
    edges = [("kitem:top", "kitem:mid"), ("kitem:mid", "kitem:leaf")]
    for s, o in (edges if order[0] == "leaf" else list(reversed(edges))):
        g.relate(s, RelationType.DERIVED_FROM, o, produced_by="claims_v1")
    return g


def test_belief_is_order_independent():
    g1 = _build(["leaf", "mid", "top"])
    g2 = _build(["top", "mid", "leaf"])
    c1, c2 = belief.belief_column(g1), belief.belief_column(g2)
    assert c1 == c2
    # weakest-link math: leaf=1.0, mid=min(1.0)*0.9=0.9, top=min(0.9)*0.8=0.72
    assert abs(c1["kitem:leaf"] - 1.0) < 1e-9
    assert abs(c1["kitem:mid"] - 0.9) < 1e-9
    assert abs(c1["kitem:top"] - 0.72) < 1e-9


def test_belief_never_touches_status_lattice():
    # belief is a column; emitting it must not add Evidence or mutate entities
    g = _build(["leaf", "mid", "top"])
    before = {e.id: len(e.evidence) for e in g.entities.values()}
    belief.belief_column(g)
    after = {e.id: len(e.evidence) for e in g.entities.values()}
    assert before == after                                   # no write-back


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
