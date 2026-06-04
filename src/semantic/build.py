"""
Phase B — evidence producers / graph builder.

Turns one document's existing pdfdrill extractor output into Evidence fed through
the IdentityResolver. The extractors are SENSORS; this module never mints an
entity except via the resolver, and every observation it forwards keeps its
producing-sensor name as provenance.

Attribution rules here are deliberately conservative (and labelled with their
confidence), because robust sender-vs-recipient attribution needs the block-role
classifier (Phase C). Today:
  * the sender (segment.sender_of) → a Company/Authority; Document `issued_by` it
  * recipient persons (NER) → Person; Document `sent_to` them
  * each IBAN → a BankAccount (iban identity); `belongs_to` the sender
  * BIC/bank → evidence on the bank account
  * Steuer-/Kassen-/Aktenzeichen, address, email, phone → evidence on the sender
    company (the letterhead owner); Document-level when no sender is known
Cross-document accumulation is the resolver's job: pass the SAME graph+resolver
across documents and one Company gathers evidence from all of them.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .entity import Entity, EntityType
from .evidence import Evidence
from .graph import SemanticGraph
from .identity import IdentityResolver
from .relation import RelationType

# id-type → the property/key name used for the company-level evidence
_ID_PROP = {"STEUERNUMMER": "steuernummer", "KASSENZEICHEN": "kassenzeichen",
            "AKTENZEICHEN": "aktenzeichen", "INVOICE_NO": "invoice_number",
            "CUSTOMER_NO": "customer_number"}


def ingest_document(graph: SemanticGraph, resolver: IdentityResolver, *,
                    source: str, sender: Optional[str] = None,
                    persons: Iterable[str] = (), entities_rec: Optional[dict] = None,
                    recipient_name: Optional[str] = None,
                    recipient_rec: Optional[dict] = None,
                    page_text: str = "", authority: bool = False) -> Entity:
    """Ingest one document's extractor output into the graph. Returns the
    Document entity. `entities_rec` is the sender-region dict the `entities`
    command produces ({iban,bic,address,ids}). `recipient_name`/`recipient_rec`
    carry Phase-C-attributed recipient evidence (the recipient's address belongs
    to the recipient PERSON, never the sender company)."""
    rec = entities_rec or {}

    doc = resolver.resolve(EntityType.DOCUMENT, keys=[("doc_id", source)],
                           evidence=[Evidence(source, "doc_id", source, "pdfdrill")])

    company: Optional[Entity] = None
    if sender:
        company = resolver.resolve(
            EntityType.AUTHORITY if authority else EntityType.COMPANY,
            keys=[("name", sender)],
            evidence=[Evidence(source, "name", sender, "segment", confidence=0.8)])
        graph.relate_once(doc.id, RelationType.ISSUED_BY, company.id,
                          produced_by="segment", confidence=0.8)

    # Recipient (Phase-C attribution): address → the recipient Person.
    recipients = list(persons)
    if recipient_name:
        recipients = [recipient_name] + [p for p in recipients if p != recipient_name]
    for idx, person in enumerate(recipients):
        if not person:
            continue
        p = resolver.resolve(EntityType.PERSON, keys=[("name", person)],
                             evidence=[Evidence(source, "name", person, "ner", confidence=0.7)])
        graph.relate_once(doc.id, RelationType.SENT_TO, p.id,
                          produced_by="ner", confidence=0.6)
        if idx == 0 and recipient_rec:
            for addr in recipient_rec.get("address", []):
                p.attach(Evidence(source, "address", str(addr), "german_address",
                                  confidence=0.7))

    # IBAN → BankAccount (strong identity), owned by the sender company.
    accounts: list[Entity] = []
    for ib in rec.get("iban", []):
        iban = ib.get("iban") if isinstance(ib, dict) else ib
        if not iban:
            continue
        ev = [Evidence(source, "iban", iban, "iban", confidence=1.0)]
        for k in ("bic", "blz", "konto", "bank"):
            v = ib.get(k) if isinstance(ib, dict) else None
            if v:
                ev.append(Evidence(source, k, str(v), "iban", confidence=0.9))
        acct = resolver.resolve(EntityType.BANK_ACCOUNT, keys=[("iban", iban)], evidence=ev)
        accounts.append(acct)
        if company is not None:
            graph.relate_once(acct.id, RelationType.BELONGS_TO, company.id,
                              produced_by="iban", confidence=0.6)
        else:
            # No Agent owner known → the document only CONTAINS the account
            # (ownership unknown). belongs_to would be a type violation.
            graph.relate_once(doc.id, RelationType.CONTAINS, acct.id,
                              produced_by="iban", confidence=0.3)

    # Page-level BICs identify the bank account; attach to the single account
    # when unambiguous, else fall back to the company/document.
    target = company or doc
    for bic in rec.get("bic", []):
        (accounts[0] if len(accounts) == 1 else target).attach(
            Evidence(source, "bic", str(bic), "bic", confidence=0.8))
    for addr in rec.get("address", []):
        target.attach(Evidence(source, "address", str(addr), "german_address", confidence=0.7))
    for typ, val in rec.get("ids", []):
        prop = _ID_PROP.get(str(typ), str(typ).lower())
        target.attach(Evidence(source, prop, str(val), "extract_ids", confidence=0.8))
        if target is doc:
            continue
    return doc
