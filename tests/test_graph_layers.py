"""
Composable graph layers over src/semantic (additive — fractional ordering,
content identity, dual-positioned occurrences, SQLite read view).

These ride inside the existing Relation.grounding dict; no change to
graph/entity/relation/identity/evidence. Port of the proposal's test_fracidx.py
(fuzz) + an integration test exercising the layers on the real SemanticGraph.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.fracidx import key_between, key_after, key_before, n_keys_between
from semantic.graph import SemanticGraph
from semantic.entity import Entity, EntityType
from semantic.evidence import Evidence
from semantic.identity import IdentityResolver, STRONG_KEYS
from semantic.relation import RelationType
from semantic.layers import ordering, content_identity, occurrence, sqlite_view

CONTAINS, DERIVED_FROM = RelationType.CONTAINS, RelationType.DERIVED_FROM


def test_fracidx_known_vectors():
    assert key_between(None, None) == "a0"
    assert key_after("a0") == "a1" and key_after("a1") == "a2"
    assert key_before("a0") == "Zz"
    assert key_between("a0", "a1") == "a0V"
    ks = n_keys_between(None, None, 50)
    assert ks == sorted(ks) and len(set(ks)) == 50


def test_fracidx_fuzz_8000_inserts_keep_order():
    random.seed(1234)
    keys: list[str] = []
    for step in range(8000):
        pos = random.randint(0, len(keys))
        left = keys[pos - 1] if pos > 0 else None
        right = keys[pos] if pos < len(keys) else None
        keys.insert(pos, key_between(left, right))
        if step % 2000 == 0:
            assert keys == sorted(keys), f"order broke at step {step}"
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert max(len(k) for k in keys) <= 8        # stays compact


def test_content_identity_dedups_formulas_and_adds_strong_key():
    assert "content_hash" in STRONG_KEYS         # added at import (idempotent)
    g = SemanticGraph(); rsv = IdentityResolver(g)
    a = content_identity.resolve_formula(rsv, r"\sum_{i=1}^{n} x_i", "p3")
    b = content_identity.resolve_formula(rsv, r"\sum_{i=1}^{n}\,x_i", "p3")  # cosmetic
    assert a.id == b.id                          # re-OCR dedups to one entity
    assert g.entity_count(EntityType.FORMULA) == 1


def test_ordering_insert_between_adds_one_edge_and_preserves_order():
    g = SemanticGraph()
    ch = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT))
    s1 = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT))
    s3 = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT))
    ordering.append_child(g, ch.id, CONTAINS, s1.id, produced_by="docmodel")
    ordering.append_child(g, ch.id, CONTAINS, s3.id, produced_by="docmodel")
    sibs = ordering.ordered_children(g, ch.id, CONTAINS)
    left, right = sibs[0].grounding["ord"], sibs[1].grounding["ord"]

    before = len(g.relations)
    s2 = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT))
    ordering.insert_child(g, ch.id, CONTAINS, s2.id, after=left, before=right, produced_by="edit")
    assert len(g.relations) - before == 1        # exactly one new edge
    order = [r.object_id for r in ordering.ordered_children(g, ch.id, CONTAINS)]
    assert order == [s1.id, s2.id, s3.id]        # s2 lands between s1 and s3


def test_occurrence_dual_position_definition_and_references_roundtrip():
    g = SemanticGraph(); rsv = IdentityResolver(g)
    sec1 = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT, subtype="section"))
    sec3 = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT, subtype="section"))
    eq = content_identity.resolve_formula(rsv, r"\nabla_\mu g^{\mu\nu} = 0", "p7")

    cur = key_after(None)
    occurrence.define(g, eq.id, sec1.id, pdf={"page": 7, "bbox": [72, 300, 320, 330]},
                      path="I.1", doc_ord=cur, produced_by="build")
    cur = key_after(cur)
    occurrence.add_occurrence(g, eq.id, sec3.id, pdf={"page": 9, "bbox": [200, 500, 260, 516]},
                              path="I.3", doc_ord=cur, produced_by="build")

    d = occurrence.definition(g, eq.id)
    assert d.grounding["pdf"]["page"] == 7 and d.grounding["pdf"]["bbox"][0] == 72
    assert d.object_id == sec1.id and d.grounding["path"] == "I.1"   # dual position
    further = occurrence.further_occurrences(g, eq.id)
    assert len(further) == 1 and further[0].grounding["pdf"]["page"] == 9

    # round-trip: occurrence grounding survives JSON
    g2 = SemanticGraph.from_dict(json.loads(json.dumps(g.to_dict())))
    d2 = occurrence.definition(g2, eq.id)
    assert d2.grounding["pdf"]["page"] == 7 and d2.grounding["path"] == "I.1"

    # SQLite dual-axis read view
    conn = sqlite_view.load_view(json.loads(json.dumps(g.to_dict())))
    assert len(sqlite_view.occurrences_of(conn, eq.id)) == 2
    assert len(sqlite_view.items_on_page(conn, 9)) == 1               # item-1 axis
    assert len(sqlite_view.occurrences_in_node(conn, sec3.id)) == 1   # item-2 axis


def test_ingest_docmodel_idempotent_and_dual_position():
    # The scientific docmodel->graph ingest: dual-positioned occurrences, content
    # dedup, and a re-run (reload + reindex) must NOT grow entities or relations.
    from docmodel.core import Document, DocObject
    from semantic.build import ingest_docmodel
    from semantic.layers import occurrence

    doc = Document(); doc.meta["bibkey"] = "T"; doc.meta["title"] = "Paper"
    sec = DocObject(type="Section", id="s1", props={
        "caption": "Metric", "section_number": "6.1", "level": 1, "flow_index": 1, "page": 2})
    eq = DocObject(type="Equation", id="e1", props={
        "latex": r"\nabla_\mu g^{\mu\nu}=0", "equation_number": "(1.1)", "page": 12,
        "region": {"top_left_x": 259, "top_left_y": 666, "width": 994, "height": 67},
        "parent_section": "s1", "flow_index": 2})
    ref = DocObject(type="Reference", id="r1", props={"citekey": "Heim1980", "title": "X", "year": "1980"})
    cit = DocObject(type="Citation", id="c1", props={"cited_reference_id": "r1", "page": 11})
    p1 = DocObject(type="Paragraph", id="p1", props={
        "text": "We use a Convolutional Neural Network (CNN) for this.",
        "page": 3, "parent_section": "s1", "flow_index": 3})
    p2 = DocObject(type="Paragraph", id="p2", props={
        "text": "The CNN is then evaluated.", "page": 5, "parent_section": "s1", "flow_index": 4})
    for o in (sec, eq, ref, cit, p1, p2):
        doc.add(o)

    g = SemanticGraph()
    ingest_docmodel(g, IdentityResolver(g), doc, "T")
    n_ent, n_rel = g.entity_count(), len(g.relations)

    # re-run (simulating reload): fresh resolver + reindex, ingest the SAME doc
    ingest_docmodel(g, IdentityResolver(g).reindex(), doc, "T")
    assert g.entity_count() == n_ent, (n_ent, g.entity_count())   # entities dedup
    assert len(g.relations) == n_rel                              # tree + occ guarded

    # dual position on the equation: PDF {page,bbox} + logical node + path
    eqent = next(e for e in g.entities.values() if e.type == EntityType.FORMULA)
    d = occurrence.definition(g, eqent.id)
    assert d.grounding["pdf"]["page"] == 12
    assert d.grounding["pdf"]["bbox"] == [259, 666, 1253, 733]
    assert d.grounding["path"] == "6.1" and d.object_id  # logical structural node
    # the in-text citation is a further occurrence of the bib entry
    bib = next(e for e in g.entities.values() if e.type == EntityType.CITATION)
    assert len(occurrence.further_occurrences(g, bib.id)) >= 1

    # the acronym concept: one CONCEPT/acronym entity with a definition (p3) + a
    # reference (p5) occurrence — the decl/use split the sTeX projector needs.
    cnn = next(e for e in g.entities.values()
               if e.type == EntityType.CONCEPT and e.subtype == "acronym")
    assert cnn.properties().get("expansion") == "Convolutional Neural Network"
    dcn = occurrence.definition(g, cnn.id)
    assert dcn.grounding["pdf"]["page"] == 3 and dcn.grounding["path"] == "6.1"
    assert len(occurrence.further_occurrences(g, cnn.id)) == 1


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
            import traceback; traceback.print_exc()
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
