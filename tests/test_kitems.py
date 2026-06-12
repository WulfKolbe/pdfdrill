"""
Kitems (src/semantic/kitems.py): knowledge items as GRAPH ENTITIES (the user
decision — no second writable store). statement_md/status/stratum as
properties, the evidence chain as Evidence rows with span grounding,
kitem_derivation as DERIVED_FROM edges. Status is compiler-automatic:
proposed (emitted) -> supported (every evidence row carries a span; or all
parents supported) -> accepted (>=2 INDEPENDENT spans in the transitive
closure); disputed only via a CONTRADICTS edge. The kitem/kitem_evidence SQL
tables are G4 projections.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.entity import EntityType
from semantic.relation import RelationType
from semantic import kitems


def _gr():
    g = SemanticGraph()
    return g, IdentityResolver(g)


def _span(bibkey="Heim1979", node="obj_1", rng="a3..a7", role="asserts", page=14):
    return {"bibkey": bibkey, "node": node, "range": rng, "role": role, "page": page}


def test_emit_creates_kitem_entity_with_status_supported():
    g, r = _gr()
    k = kitems.emit_kitem(g, r, "The mass eigenvalues follow from N(n,m,p,σ).",
                          kind="rule", stratum=4, spans=[_span()],
                          produced_by="claims_v1")
    assert k.type == EntityType.KITEM and k.subtype == "rule"
    p = k.properties()
    assert p["statement_md"].startswith("The mass eigenvalues")
    assert p["stratum"] == 4
    assert kitems.status_of(g, k.id) == "supported"      # 1 grounded span


def test_content_hash_dedup_is_fixpoint_noop():
    g, r = _gr()
    k1 = kitems.emit_kitem(g, r, "Valid for n <= 6.", kind="rule", stratum=4,
                           spans=[_span(node="obj_1")], produced_by="p1")
    n_entities = g.entity_count()
    k2 = kitems.emit_kitem(g, r, "Valid  for n <= 6.",   # whitespace variant
                           kind="rule", stratum=4,
                           spans=[_span(node="obj_2", bibkey="Heim1984")],
                           produced_by="p2")
    assert k1.id == k2.id                                # SAME entity (no-op mint)
    assert g.entity_count() == n_entities
    # the second sighting ADDED evidence -> now 2 independent spans -> accepted
    assert kitems.status_of(g, k1.id) == "accepted"


def test_proposed_without_spans_and_derivation_inherits_support():
    g, r = _gr()
    bare = kitems.emit_kitem(g, r, "An ungrounded guess.", kind="claim",
                             stratum=4, spans=[], produced_by="p")
    assert kitems.status_of(g, bare.id) == "proposed"
    p1 = kitems.emit_kitem(g, r, "Parent A.", kind="rule", stratum=4,
                           spans=[_span(node="n1")], produced_by="p")
    p2 = kitems.emit_kitem(g, r, "Parent B.", kind="rule", stratum=4,
                           spans=[_span(node="n2", bibkey="Other2001")], produced_by="p")
    child = kitems.emit_kitem(g, r, "A follows from B.", kind="derivation",
                              stratum=5, spans=[],
                              derived_from=[p1.id, p2.id], produced_by="p")
    # derivation edges exist
    targets = {rel.object_id for rel in g.relations_of(child.id, RelationType.DERIVED_FROM)}
    assert targets == {p1.id, p2.id}
    # inherits: parents reach 2 independent spans transitively -> accepted
    assert kitems.status_of(g, child.id) == "accepted"


def test_disputed_via_contradiction():
    g, r = _gr()
    k = kitems.emit_kitem(g, r, "X holds.", kind="claim", stratum=4,
                          spans=[_span()], produced_by="p")
    c = kitems.emit_kitem(g, r, "X does not hold.", kind="contradiction",
                          stratum=5, spans=[_span(node="n9", bibkey="B")],
                          produced_by="p")
    g.relate(c.id, RelationType.CONTRADICTS, k.id, produced_by="p")
    assert kitems.status_of(g, k.id) == "disputed"


def test_sqlite_projection_and_tiddlers():
    g, r = _gr()
    k = kitems.emit_kitem(g, r, "The rulebook line.", kind="rule", stratum=4,
                          spans=[_span(), _span(node="obj_9", bibkey="Other")],
                          produced_by="claims_v1")
    from semantic.layers import sqlite_view
    conn = sqlite_view.load_view(g.to_dict())
    row = conn.execute("SELECT kind, status, stratum, statement_md FROM kitem "
                       "WHERE id=?", (k.id,)).fetchone()
    assert row == ("rule", "accepted", 4, "The rulebook line.")
    ev = conn.execute("SELECT bibkey, node, role FROM kitem_evidence "
                      "WHERE kitem=? ORDER BY bibkey", (k.id,)).fetchall()
    assert ("Heim1979", "obj_1", "asserts") in ev and len(ev) == 2

    tids = kitems.kitem_tiddlers(g, "Heim1979")
    assert len(tids) == 1
    t = tids[0]
    assert t["title"].startswith("Heim1979_KI")
    assert t["kind"] == "rule" and t["status"] == "accepted"
    assert "The rulebook line." in t["text"]
    assert t["khash"]                          # the drill-down handle


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
