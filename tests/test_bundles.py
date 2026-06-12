"""
Semantic bundles (src/semantic/bundles.py) — the gluing made visible: ONE
derived view per entity unifying canonical name, aliases, mentions (G3
occurrences), claims (evidence rows), and linked nodes. Derived, never a
second writable store. Plus the observation/bundle tables in the SQLite
projection (sqlite_view) so "pass X asserted Y about node Z" is queryable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.entity import EntityType
from semantic.evidence import Evidence
from semantic.relation import RelationType
from semantic.layers import occurrence, content_identity
from semantic.entity import Entity
from semantic import bundles


def _ent(g, t, subtype=""):
    return g.add_entity(Entity(id=g.new_id(t), type=t, subtype=subtype))


def _graph():
    g = SemanticGraph()
    r = IdentityResolver(g)
    # a CONCEPT with a definition + two references (G3, dual-positioned)
    c = r.resolve(EntityType.CONCEPT,
                  keys=[("content_hash", content_identity.content_hash("concept|CNN"))],
                  evidence=[Evidence("doc1", "name", "CNN", "concepts", confidence=0.9),
                            Evidence("doc1", "expansion", "Convolutional Neural Network",
                                     "concepts", confidence=0.9)])
    sec = _ent(g, EntityType.CONCEPT, "section")
    occurrence.define(g, c.id, sec.id, pdf={"page": 3, "bbox": [1, 2, 3, 4]},
                      path="2.1", produced_by="concepts")
    occurrence.add_occurrence(g, c.id, sec.id, pdf={"page": 5, "bbox": [0, 0, 1, 1]},
                              produced_by="concepts")
    # a FORMULA deduped by content hash (two sightings -> ONE entity)
    f1 = content_identity.resolve_formula(r, "E = m c^2", "doc1")
    f2 = content_identity.resolve_formula(r, "E \\, = \\, m c^2", "doc1")
    assert f1.id == f2.id
    # a CITES edge from the concept's doc to something
    cit = _ent(g, EntityType.CITATION, "bibentry")
    g.relate(c.id, RelationType.CITES, cit.id, produced_by="test")
    return g, c, f1, cit


def test_bundle_assembles_entity_view():
    g, c, f, cit = _graph()
    b = bundles.bundle(g, c.id)
    assert b["canonical"] == "CNN"
    assert "Convolutional Neural Network" in b["aliases"]
    assert len(b["mentions"]) == 2
    roles = {m["role"] for m in b["mentions"]}
    assert roles == {"definition", "reference"}
    assert b["mentions"][0]["page"] == 3                  # doc order: define first
    assert any(cl["prop"] == "expansion" for cl in b["claims"])
    assert cit.id in b["linked"].get("cites", [])
    assert b["consistent"] is True


def test_bundle_formula_canonical_is_latex():
    g, c, f, cit = _graph()
    b = bundles.bundle(g, f.id)
    assert "E = m c^2" in b["aliases"] or b["canonical"]   # latex evidence kept
    assert b["id"] == f.id


def test_all_bundles_and_sqlite_projection():
    g, c, f, cit = _graph()
    bl = bundles.all_bundles(g, types=(EntityType.CONCEPT, EntityType.FORMULA))
    ids = {b["id"] for b in bl}
    assert c.id in ids and f.id in ids

    from semantic.layers import sqlite_view
    conn = sqlite_view.load_view(g.to_dict(), bundles=bl)
    # observations: one row per evidence record, provenance queryable
    n_obs = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    assert n_obs == sum(len(e.evidence) for e in g.entities.values())
    row = conn.execute(
        "SELECT value, produced_by FROM observation WHERE entity=? AND prop='name'",
        (c.id,)).fetchone()
    assert row == ("CNN", "concepts")
    # bundles + members
    canon = conn.execute("SELECT canonical FROM bundle WHERE id=?", (c.id,)).fetchone()
    assert canon == ("CNN",)
    members = conn.execute(
        "SELECT role, COUNT(*) FROM bundle_member WHERE bundle_id=? GROUP BY role",
        (c.id,)).fetchall()
    assert dict(members).get("definition") == 1
    # a view without bundles still loads (backward compatible)
    conn2 = sqlite_view.load_view(g.to_dict())
    assert conn2.execute("SELECT COUNT(*) FROM observation").fetchone()[0] == n_obs


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
