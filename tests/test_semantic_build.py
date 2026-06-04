"""
Phase B — evidence producers / graph builder.

`ingest_document` turns one document's existing pdfdrill extractor output
(sender from segment, IBAN/BIC/address/ids from the entities command, persons
from NER) into Evidence fed through the IdentityResolver. Extractors are sensors;
the builder never invents entities outside the resolver. Crucially, passing the
SAME graph+resolver across documents makes one Company accumulate evidence — the
whole point of the design.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import proof
from semantic.entity import EntityType
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.relation import RelationType
from semantic.build import ingest_document


def _rec(**kw):
    base = {"iban": [], "bic": [], "address": [], "ids": []}
    base.update(kw)
    return base


def test_ingest_builds_document_company_and_bank_account():
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = ingest_document(g, r, source="inv001", sender="Acme GmbH",
                          persons=["Wulf Kolbe"],
                          entities_rec=_rec(
                              iban=[{"iban": "DE89370400440532013000", "bank": "Sparkasse Köln",
                                     "blz": "37040044", "konto": "0532013000"}],
                              bic=["COBADEFFXXX"],
                              address=["Hauptstr. 1, 50667 Köln"],
                              ids=[("STEUERNUMMER", "204/5189/1009")]))
    # a Document entity, a Company (sender), a Person (recipient), a BankAccount
    assert doc.type == EntityType.DOCUMENT
    assert g.entity_count(EntityType.COMPANY) == 1
    assert g.entity_count(EntityType.PERSON) == 1
    assert g.entity_count(EntityType.BANK_ACCOUNT) == 1
    company = g.entities_of(EntityType.COMPANY)[0]
    acct = g.entities_of(EntityType.BANK_ACCOUNT)[0]
    # relations: doc issued_by company, doc sent_to person, account belongs_to company
    assert any(x.predicate == RelationType.ISSUED_BY and x.object_id == company.id
               for x in g.relations_of(doc.id))
    assert any(x.predicate == RelationType.SENT_TO for x in g.relations_of(doc.id))
    assert any(x.predicate == RelationType.BELONGS_TO and x.object_id == company.id
               for x in g.relations_of(acct.id))
    # the IBAN/BIC are EVIDENCE on the bank account, not standalone entities
    assert acct.properties().get("iban") == "DE89370400440532013000"
    assert "bic" in acct.properties()
    # the Steuernummer + address are evidence on the company
    cp = company.properties()
    assert cp.get("steuernummer") == "204/5189/1009" and "address" in cp
    # provenance: the account's iban evidence was produced by the 'iban' sensor
    assert "iban" in proof.processes(acct)


def test_two_documents_same_company_accumulate_into_one_entity():
    g = SemanticGraph()
    r = IdentityResolver(g)
    ingest_document(g, r, source="inv001", sender="Acme GmbH",
                    entities_rec=_rec(address=["Hauptstr. 1, 50667 Köln"]))
    ingest_document(g, r, source="inv002", sender="Acme GmbH",
                    entities_rec=_rec(iban=[{"iban": "DE89370400440532013000"}],
                                      ids=[("STEUERNUMMER", "204/5189/1009")]))
    assert g.entity_count(EntityType.COMPANY) == 1      # ONE company across both docs
    c = g.entities_of(EntityType.COMPANY)[0]
    assert proof.sources(c) == {"inv001", "inv002"}     # evidence from both documents
    # the bank account from doc 2 is owned by the same company
    accts = g.entities_of(EntityType.BANK_ACCOUNT)
    assert len(accts) == 1
    assert any(x.predicate == RelationType.BELONGS_TO and x.object_id == c.id
               for x in g.relations_of(accts[0].id))


def test_no_duplicate_relations_on_reingest():
    g = SemanticGraph()
    r = IdentityResolver(g)
    rec = _rec(iban=[{"iban": "DE89370400440532013000"}])
    ingest_document(g, r, source="inv001", sender="Acme GmbH", entities_rec=rec)
    ingest_document(g, r, source="inv001", sender="Acme GmbH", entities_rec=rec)
    acct = g.entities_of(EntityType.BANK_ACCOUNT)[0]
    belongs = [x for x in g.relations_of(acct.id) if x.predicate == RelationType.BELONGS_TO]
    assert len(belongs) == 1                            # not duplicated


if __name__ == "__main__":
    test_ingest_builds_document_company_and_bank_account(); print("PASS ingest")
    test_two_documents_same_company_accumulate_into_one_entity(); print("PASS accumulate")
    test_no_duplicate_relations_on_reingest(); print("PASS dedupe")
    print("\nAll tests passed.")
