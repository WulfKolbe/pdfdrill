"""
Tests for the semantic graph core (src/semantic/) — the CSP-style layered model:

  Entity layer    : stable typed identities (person/company/paper/formula/…)
  Relation layer  : typed edges (cites/derived_from/contains/owns/…)
  Process layer    : the sensors (OCR/MathPix/Stanza/libpostal/IBAN/…) that emit
  Proof layer     : every node/edge records which evidence + which process made it

The unifying thesis (the reason this is not a per-page field extractor):
  * The GRAPH is the primary artifact.
  * Extractors are SENSORS that emit EVIDENCE; they never create final entities.
  * An IdentityResolver does find-or-create + attach-evidence, so the SAME
    real-world entity accumulates evidence across many documents over time.
  * The address/IBAN/VAT are EVIDENCE pointing at an Organization — not the
    primary object. The Company is the entity.
  * The same primitives model a scientific paper and a commercial invoice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.evidence import Evidence
from semantic.entity import Entity, EntityType
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver


# ---- evidence: the atomic observation a sensor emits ----------------------

def test_evidence_carries_provenance():
    ev = Evidence(source="invoice001", prop="address",
                  value="Hauptstraße 1, 50667 Köln", produced_by="libpostal",
                  version="1.1", confidence=0.9,
                  grounding={"block_id": "b6", "start": 0, "end": 23})
    assert ev.source == "invoice001"
    assert ev.prop == "address" and ev.value.startswith("Hauptstraße")
    assert ev.produced_by == "libpostal" and ev.version == "1.1"
    assert ev.confidence == 0.9 and ev.grounding["block_id"] == "b6"


# ---- entity: accumulates evidence, derives properties ----------------------

def test_entity_derives_properties_from_evidence_by_confidence():
    e = Entity(id="company:1", type=EntityType.COMPANY)
    e.attach(Evidence("inv1", "name", "Acme GmbH", "ner", confidence=0.7))
    e.attach(Evidence("inv2", "name", "ACME GMBH", "ner", confidence=0.9))
    e.attach(Evidence("inv1", "iban", "DE89370400440532013000", "iban", confidence=1.0))
    props = e.properties()
    assert props["name"] == "Acme GmbH" or props["name"] == "ACME GMBH"
    # higher-confidence name wins
    assert e.best("name").confidence == 0.9
    assert props["iban"] == "DE89370400440532013000"
    assert {ev.source for ev in e.evidence} == {"inv1", "inv2"}


# ---- the core: identity resolution unifies an entity across documents ------

def test_identity_resolver_unifies_company_across_two_documents():
    g = SemanticGraph()
    r = IdentityResolver(g)

    # Document 1 mentions the company by name + an address.
    c1 = r.resolve(EntityType.COMPANY, keys=[("name", "Acme GmbH")], evidence=[
        Evidence("inv001", "name", "Acme GmbH", "ner", confidence=0.9),
        Evidence("inv001", "address", "Hauptstr. 1, 50667 Köln", "libpostal", confidence=0.9),
    ])
    # Document 2 mentions the SAME company (same name) + a new IBAN.
    c2 = r.resolve(EntityType.COMPANY, keys=[("name", "Acme GmbH")], evidence=[
        Evidence("inv002", "iban", "DE89370400440532013000", "iban", confidence=1.0),
    ])

    assert c1.id == c2.id                                  # ONE entity, not two
    assert g.entity_count(EntityType.COMPANY) == 1
    props = c1.properties()
    assert "address" in props and "iban" in props          # evidence accumulated
    assert {ev.source for ev in c1.evidence} == {"inv001", "inv002"}


def test_address_and_iban_are_evidence_not_standalone_entities():
    """The address/IBAN are attached AS EVIDENCE to the Company — the graph holds
    one Company entity, not separate Address/IBAN nodes."""
    g = SemanticGraph()
    r = IdentityResolver(g)
    r.resolve(EntityType.COMPANY, keys=[("name", "Acme GmbH")], evidence=[
        Evidence("inv001", "name", "Acme GmbH", "ner", confidence=0.9),
        Evidence("inv001", "address", "Hauptstr. 1, 50667 Köln", "libpostal", confidence=0.9),
        Evidence("inv001", "iban", "DE89370400440532013000", "iban", confidence=1.0),
    ])
    assert g.entity_count() == 1                            # only the Company
    assert g.entity_count(EntityType.COMPANY) == 1


def test_identity_by_strong_key_resolves_across_documents():
    """A later document that mentions ONLY the IBAN still resolves to the company
    first seen by name — strong-key evidence is indexed."""
    g = SemanticGraph()
    r = IdentityResolver(g)
    r.resolve(EntityType.COMPANY, keys=[("name", "Provinzial AG")], evidence=[
        Evidence("d1", "name", "Provinzial AG", "ner", confidence=0.9),
        Evidence("d1", "iban", "DE89370400440532013000", "iban", confidence=1.0)])
    # IBAN given with spaces — normalisation must still match.
    c = r.resolve(EntityType.COMPANY, keys=[("iban", "DE89 3704 0044 0532 0130 00")],
                  evidence=[Evidence("d2", "address", "Provinzialplatz 1, 40591 Düsseldorf",
                                     "libpostal", confidence=0.9)])
    assert g.entity_count(EntityType.COMPANY) == 1
    assert "address" in c.properties() and "name" in c.properties()


def test_typed_relation_carries_provenance():
    from semantic.relation import RelationType
    g = SemanticGraph()
    r = IdentityResolver(g)
    comp = r.resolve(EntityType.COMPANY, keys=[("name", "Acme")],
                     evidence=[Evidence("d1", "name", "Acme", "ner")])
    acct = r.resolve(EntityType.BANK_ACCOUNT, keys=[("iban", "DE89370400440532013000")],
                     evidence=[Evidence("d1", "iban", "DE89370400440532013000", "iban")])
    g.relate(comp.id, RelationType.OWNS, acct.id, produced_by="rule:iban-ownership",
             confidence=0.8, grounding={"block_id": "b12"})
    rels = g.relations_of(comp.id)
    assert len(rels) == 1
    assert rels[0].predicate == RelationType.OWNS and rels[0].object_id == acct.id
    assert rels[0].produced_by == "rule:iban-ownership" and rels[0].grounding["block_id"] == "b12"


def test_same_primitives_model_scientific_and_commercial():
    """The unifying proof: a paper+citation and a company+author use the SAME
    Entity/Relation/Evidence primitives in one graph."""
    from semantic.relation import RelationType
    g = SemanticGraph()
    r = IdentityResolver(g)
    # commercial
    comp = r.resolve(EntityType.COMPANY, keys=[("name", "Acme")],
                     evidence=[Evidence("inv", "name", "Acme", "ner")])
    author = r.resolve(EntityType.PERSON, keys=[("name", "M. Müller")],
                       evidence=[Evidence("inv", "name", "M. Müller", "ner")])
    g.relate(author.id, RelationType.ACTS_FOR, comp.id, produced_by="rule")
    # scientific — identical machinery
    p1 = r.resolve(EntityType.PAPER, keys=[("title", "On Foo")],
                   evidence=[Evidence("pdf", "title", "On Foo", "mathpix")])
    p2 = r.resolve(EntityType.PAPER, keys=[("title", "On Bar")],
                   evidence=[Evidence("pdf", "title", "On Bar", "mathpix")])
    g.relate(p1.id, RelationType.CITES, p2.id, produced_by="bibsource", grounding={"label": "[1]"})
    assert g.entity_count() == 4
    assert any(x.predicate == RelationType.CITES for x in g.relations_of(p1.id))
    assert any(x.predicate == RelationType.ACTS_FOR for x in g.relations_of(author.id))


def test_proof_layer_answers_provenance_questions():
    from semantic import proof
    g = SemanticGraph()
    r = IdentityResolver(g)
    c = r.resolve(EntityType.COMPANY, keys=[("name", "Acme")], evidence=[
        Evidence("d1", "name", "Acme", "ner", version="stanza-1.10", confidence=0.9),
        Evidence("d2", "iban", "DE89370400440532013000", "iban", version="mod97", confidence=1.0)])
    assert proof.processes(c) == {"ner", "iban"}        # which agents produced it
    assert proof.sources(c) == {"d1", "d2"}             # which documents
    assert proof.created_by(c) == "ner"                 # why/who created it (origin)
    assert "stanza-1.10" in proof.versions(c)["ner"]    # which version


def test_graph_roundtrips_to_json():
    import json
    from semantic.relation import RelationType
    g = SemanticGraph()
    r = IdentityResolver(g)
    c = r.resolve(EntityType.COMPANY, keys=[("name", "Acme")],
                  evidence=[Evidence("d1", "name", "Acme", "ner", confidence=0.9)])
    a = r.resolve(EntityType.BANK_ACCOUNT, keys=[("iban", "DE89370400440532013000")],
                  evidence=[Evidence("d1", "iban", "DE89370400440532013000", "iban")])
    g.relate(c.id, RelationType.OWNS, a.id, produced_by="rule")
    g2 = SemanticGraph.from_dict(json.loads(json.dumps(g.to_dict())))
    assert g2.entity_count() == 2
    assert g2.get(a.id).properties()["iban"] == "DE89370400440532013000"
    assert len(g2.relations) == 1 and g2.relations[0].predicate == RelationType.OWNS


if __name__ == "__main__":
    test_evidence_carries_provenance(); print("PASS evidence")
    test_entity_derives_properties_from_evidence_by_confidence(); print("PASS entity")
    test_identity_resolver_unifies_company_across_two_documents(); print("PASS resolve")
    test_address_and_iban_are_evidence_not_standalone_entities(); print("PASS evidence-not-entity")
    test_identity_by_strong_key_resolves_across_documents(); print("PASS strong-key")
    test_typed_relation_carries_provenance(); print("PASS relation")
    test_same_primitives_model_scientific_and_commercial(); print("PASS unify")
    test_proof_layer_answers_provenance_questions(); print("PASS proof")
    test_graph_roundtrips_to_json(); print("PASS roundtrip")
    print("\nAll tests passed.")
