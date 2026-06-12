"""
Phase D — the semantic compiler / validator.

The deterministic gate that makes the graph defensible: type-check every relation
against a signature table, verify grounding (does the cited evidence_text actually
appear in the cited block?), detect dangling references, derived_from cycles, and
contradictory functional relations. Returns validity + graded warnings — turning
"impressive but inconsistent" into "verified", catching exactly the failure modes
the LLM test exhibited.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.entity import Entity, EntityType
from semantic.evidence import Evidence
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.relation import RelationType
from semantic.build import ingest_document
from semantic import compiler


def _valid_commercial_graph():
    g = SemanticGraph()
    r = IdentityResolver(g)
    ingest_document(g, r, source="inv001", sender="Acme GmbH",
                    entities_rec={"iban": [{"iban": "DE89370400440532013000"}],
                                  "bic": [], "address": [], "ids": []})
    return g


def test_valid_graph_compiles_valid():
    res = compiler.compile(_valid_commercial_graph())
    assert res.validity == "valid"
    assert not [w for w in res.warnings if w.severity == "critical"]


def test_type_violation_is_critical_and_invalid():
    # belongs_to requires a BankAccount subject, not a Document → violation
    # (this is exactly the d3(Document) belongs_to e4(Agent) bug from the test).
    g = SemanticGraph()
    doc = g.add_entity(Entity("document:1", EntityType.DOCUMENT))
    comp = g.add_entity(Entity("company:1", EntityType.COMPANY))
    g.relate(doc.id, RelationType.BELONGS_TO, comp.id, produced_by="llm")
    res = compiler.compile(g)
    assert res.validity == "invalid"
    assert any(w.code == "type_violation" and w.severity == "critical"
               for w in res.warnings)


def test_dangling_reference_is_critical():
    g = SemanticGraph()
    g.add_entity(Entity("document:1", EntityType.DOCUMENT))
    g.relate("document:1", RelationType.ISSUED_BY, "company:999", produced_by="llm")
    res = compiler.compile(g)
    assert res.validity == "invalid"
    assert any(w.code == "dangling_reference" for w in res.warnings)


def test_derived_from_cycle_is_detected():
    g = SemanticGraph()
    a = g.add_entity(Entity("document:1", EntityType.DOCUMENT))
    b = g.add_entity(Entity("document:2", EntityType.DOCUMENT))
    g.relate(a.id, RelationType.DERIVED_FROM, b.id, produced_by="x")
    g.relate(b.id, RelationType.DERIVED_FROM, a.id, produced_by="x")
    res = compiler.compile(g)
    assert res.validity == "invalid"
    assert any(w.code == "cycle" for w in res.warnings)


def test_grounding_verification_flags_unsupported_evidence():
    g = SemanticGraph()
    e = g.add_entity(Entity("company:1", EntityType.COMPANY))
    e.attach(Evidence("d1", "name", "Acme GmbH", "llm",
                      grounding={"block_id": "b1", "evidence_text": "Acme GmbH"}))
    e.attach(Evidence("d1", "name", "Ghost AG", "llm",
                      grounding={"block_id": "b1", "evidence_text": "Ghost AG"}))
    blocks = {"b1": "Rechnung von Acme GmbH, Hauptstr. 1"}
    res = compiler.compile(g, blocks=blocks)
    bad = [w for w in res.warnings if w.code == "grounding_unsupported"]
    assert len(bad) == 1 and "Ghost AG" in bad[0].message      # only the unsupported one


def test_contradictory_functional_relation_flagged():
    g = SemanticGraph()
    doc = g.add_entity(Entity("document:1", EntityType.DOCUMENT))
    c1 = g.add_entity(Entity("company:1", EntityType.COMPANY))
    c2 = g.add_entity(Entity("company:2", EntityType.COMPANY))
    g.relate(doc.id, RelationType.ISSUED_BY, c1.id, produced_by="x")
    g.relate(doc.id, RelationType.ISSUED_BY, c2.id, produced_by="x")
    res = compiler.compile(g)
    assert any(w.code == "contradiction" for w in res.warnings)


def test_occurrence_carrier_edges_are_exempt_from_signatures():
    """G3 occurrence edges ride on REFERENCES with grounding layer='occurrence'
    (formula REFERENCES section-node) — they are LAYER edges, not assertions,
    and must not be type-checked against the REFERENCES signature. Same for
    kitem_derivation-grounded edges."""
    from semantic.graph import SemanticGraph
    from semantic.entity import Entity, EntityType
    from semantic.relation import RelationType
    from semantic import compiler
    g = SemanticGraph()
    f = g.add_entity(Entity(id=g.new_id(EntityType.FORMULA), type=EntityType.FORMULA))
    sec = g.add_entity(Entity(id=g.new_id(EntityType.CONCEPT), type=EntityType.CONCEPT,
                              subtype="section"))
    g.relate(f.id, RelationType.REFERENCES, sec.id,
             grounding={"layer": "occurrence", "role": "definition", "ord": "a1"})
    # provenance between ARTIFACTS is legitimate: image derived_from image
    # (the docmodel image_source edge), kitem derived_from kitem
    i1 = g.add_entity(Entity(id=g.new_id(EntityType.IMAGE), type=EntityType.IMAGE))
    i2 = g.add_entity(Entity(id=g.new_id(EntityType.IMAGE), type=EntityType.IMAGE))
    g.relate(i1.id, RelationType.DERIVED_FROM, i2.id)
    warnings = compiler.typecheck(g)
    assert not [w for w in warnings if w.code == "type_violation"]


if __name__ == "__main__":
    test_valid_graph_compiles_valid(); print("PASS valid")
    test_type_violation_is_critical_and_invalid(); print("PASS type-violation")
    test_dangling_reference_is_critical(); print("PASS dangling")
    test_derived_from_cycle_is_detected(); print("PASS cycle")
    test_grounding_verification_flags_unsupported_evidence(); print("PASS grounding")
    test_contradictory_functional_relation_flagged(); print("PASS contradiction")
    test_occurrence_carrier_edges_are_exempt_from_signatures(); print("PASS occurrence-exempt")
    print("\nAll tests passed.")
