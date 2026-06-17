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
    from . import transformation as _trans
    _snap = _trans.snapshot(graph)

    # Key by content_hash too (not just doc_id) so the Document dedups across runs
    # — doc_id alone doesn't survive the resolver's reindex (strong/soft keys only),
    # which would otherwise re-mint the Document and cascade duplicate root edges.
    from .layers import content_identity as _ci
    _dh = _ci.content_hash(f"doc|{source}")
    doc = resolver.resolve(EntityType.DOCUMENT,
                           keys=[("content_hash", _dh), ("doc_id", source)],
                           evidence=[Evidence(source, "doc_id", source, "pdfdrill"),
                                     Evidence(source, "content_hash", _dh, "pdfdrill", confidence=1.0)])

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
    # group this whole invocation under one content-addressed Transformation,
    # stamping its tid into the grounding of every evidence/edge it just emitted.
    _trans.record_batch(graph, "ingest_document", _snap, source_ids=[doc.id])
    return doc


# ---------------------------------------------------------------------------
# Scientific docmodel -> graph ingest (the structural tree + occurrence-bearing
# items, wired through the composable layers). Additive: runs alongside the
# commercial ingest above; everything lives on the same SemanticGraph.
# ---------------------------------------------------------------------------

def ingest_docmodel(graph: SemanticGraph, resolver: IdentityResolver, doc,
                    bibkey: str, source: Optional[str] = None) -> dict:
    """Map a docmodel `Document` into the semantic graph:

      * the chapter/section CONTAINS tree, ordered by L1 (`ordering`),
      * occurrence-bearing items (Equation/Formula -> FORMULA, Table -> TABLE,
        Picture/Diagram -> IMAGE, Reference -> CITATION) deduped by L2 content
        identity, and
      * each item's dual-positioned occurrence via L3 (`occurrence`): PDF
        {page,bbox} from the docmodel region + the containing section node +
        `path` (the section number). In-text Citations become further
        occurrences of their Reference (`cited_reference_id`).

    Idempotent: entities dedup on re-run (content_hash / bibkey / doc_id), the
    CONTAINS tree is `has_relation`-guarded, and an occurrence is not re-added at
    the same (item, node, page, role). Returns a counts dict.
    """
    from .layers import ordering, content_identity, occurrence
    from . import fracidx

    source = source or bibkey
    CONTAINS, DERIVED_FROM = RelationType.CONTAINS, RelationType.DERIVED_FROM
    objs = doc.objects
    by_flow = lambda os: sorted(os, key=lambda o: o.props.get("flow_index") or 0)

    def resolve_content(etype, subtype, key_text, **props):
        h = content_identity.content_hash(key_text)
        ev = [Evidence(source, "content_hash", h, "docmodel", confidence=1.0)]
        for k, v in props.items():
            if v not in (None, "", []):
                ev.append(Evidence(source, k, str(v), "docmodel"))
        e = resolver.resolve(etype, keys=[("content_hash", h)], evidence=ev)
        if subtype and not e.subtype:
            e.subtype = subtype
        return e

    def pdf_pos(item):
        page = item.props.get("page")
        if page is None:
            return None
        d = {"page": int(page)}
        reg = item.props.get("region")
        if isinstance(reg, dict) and "top_left_x" in reg:
            x0, y0 = reg["top_left_x"], reg["top_left_y"]
            d["bbox"] = [x0, y0, x0 + reg.get("width", 0), y0 + reg.get("height", 0)]
        return d

    def occ_exists(item_id, node_id, page, role):
        for r in graph.relations_of(item_id, RelationType.REFERENCES):
            g = r.grounding or {}
            if (g.get("layer") == "occurrence" and r.object_id == node_id
                    and g.get("role") == role
                    and (g.get("pdf") or {}).get("page") == page):
                return True
        return False

    cur = {"k": None}
    def next_ord():
        cur["k"] = fracidx.key_after(cur["k"])
        return cur["k"]

    counts = {"sections": 0, "equations": 0, "formulas": 0, "tables": 0,
              "figures": 0, "references": 0, "citations": 0, "occurrences": 0}
    from . import transformation as _trans
    _snap = _trans.snapshot(graph)

    # --- Document root entity ---
    # Keyed by BOTH doc_id (so it unifies with the commercial document within a
    # run) AND content_hash (so it dedups across runs — doc_id alone doesn't
    # survive the resolver's reindex, which only re-registers strong/soft keys).
    dh = content_identity.content_hash(f"doc|{source}")
    root = resolver.resolve(EntityType.DOCUMENT, keys=[("doc_id", source), ("content_hash", dh)],
        evidence=[
            Evidence(source, "title", str(doc.meta.get("title") or bibkey), "docmodel"),
            Evidence(source, "bibkey", bibkey, "docmodel"),
            Evidence(source, "content_hash", dh, "docmodel", confidence=1.0)])
    if not root.subtype:
        root.subtype = "paper"

    # --- Structural tree: sections (CONCEPT) joined by ordered CONTAINS (L1) ---
    sec_node: dict[str, str] = {}
    sections = by_flow([o for o in objs.values() if o.type == "Section"])
    for s in sections:
        e = resolve_content(EntityType.CONCEPT, "section",
                            f"{bibkey}|sec|{s.props.get('section_number','')}|{s.props.get('caption','')}",
                            caption=s.props.get("caption"),
                            section_number=s.props.get("section_number"),
                            level=s.props.get("level"))
        sec_node[s.id] = e.id
        counts["sections"] += 1
    for s in sections:
        child = sec_node[s.id]
        parent_obj = objs.get(s.parent) if getattr(s, "parent", None) else None
        parent = (sec_node.get(s.parent) if (parent_obj and parent_obj.type == "Section")
                  else root.id)
        if not graph.has_relation(parent, CONTAINS, child):
            ordering.append_child(graph, parent, CONTAINS, child, produced_by="docmodel")

    def node_path(item):
        ps = item.props.get("parent_section")
        secobj = objs.get(ps)
        return sec_node.get(ps, root.id), (secobj.props.get("section_number", "") if secobj else "")

    def record(item, entity, role="definition"):
        node, path = node_path(item)
        p = pdf_pos(item)
        page = p["page"] if p else None
        if occ_exists(entity.id, node, page, role):
            return
        fn = occurrence.define if role == "definition" else occurrence.add_occurrence
        fn(graph, entity.id, node, pdf=p, path=path, doc_ord=next_ord(), produced_by="docmodel")
        counts["occurrences"] += 1

    # --- Items 4-8: math / tables / figures, deduped by content identity (L2) ---
    for it in by_flow([o for o in objs.values()
                       if o.type in ("Equation", "Formula", "Table", "Picture", "Diagram")]):
        if it.type == "Equation":
            latex = it.props.get("latex", "")
            if not latex:
                continue
            e = content_identity.resolve_formula(resolver, latex, source,
                                                 produced_by="docmodel")
            if not e.subtype:
                e.subtype = "equation"
            num = it.props.get("equation_number") or it.props.get("refnum")
            if num:
                e.attach(Evidence(source, "number", str(num), "eqnums"))
            counts["equations"] += 1
        elif it.type == "Formula":
            latex = it.props.get("latex", "")
            if not latex:
                continue
            e = content_identity.resolve_formula(resolver, latex, source,
                                                 produced_by="docmodel")
            if not e.subtype:
                e.subtype = "inline"
            counts["formulas"] += 1
        elif it.type == "Table":
            e = resolve_content(EntityType.TABLE, "table",
                                it.props.get("raw_text") or it.props.get("latex_code") or it.id)
            counts["tables"] += 1
        else:  # Picture / Diagram -> figure (item 7), + external source (item 8)
            kt = (it.props.get("caption") or it.props.get("url")
                  or it.props.get("latex_code") or it.id)
            e = resolve_content(EntityType.IMAGE, "figure", f"fig|{kt}",
                                caption=it.props.get("caption"), label=it.props.get("refnum"))
            counts["figures"] += 1
            src_ref = it.props.get("url") or it.props.get("embedded_image_id")
            if src_ref:
                se = resolve_content(EntityType.IMAGE, "image_source", f"src|{src_ref}",
                                     path=src_ref)
                graph.relate_once(e.id, DERIVED_FROM, se.id, produced_by="docmodel")
        record(it, e, role="definition")

    # --- Item 9: bib entries (CITATION/bibentry) + citation occurrences ---
    ref_node: dict[str, str] = {}
    for ref in objs.values():
        if ref.type != "Reference":
            continue
        ck = ref.props.get("citekey") or ref.id
        # content_hash (on the citekey) is the strong key that dedups across runs;
        # bibkey/title/year are attached as queryable properties.
        e = resolve_content(EntityType.CITATION, "bibentry", f"bib|{ck}",
                            bibkey=ck, title=ref.props.get("title"),
                            year=ref.props.get("year"))
        ref_node[ref.id] = e.id
        counts["references"] += 1
        page = ref.props.get("page")
        if not occ_exists(e.id, root.id, page, "definition"):
            occurrence.define(graph, e.id, root.id,
                              pdf=({"page": int(page)} if page else None),
                              path="Bibliography", doc_ord=next_ord(), produced_by="bib")
            counts["occurrences"] += 1
    for cit in objs.values():
        if cit.type != "Citation":
            continue
        target = ref_node.get(cit.props.get("cited_reference_id"))
        if not target:
            continue
        page = cit.props.get("page")
        if not occ_exists(target, root.id, page, "reference"):
            occurrence.add_occurrence(graph, target, root.id,
                                      pdf=({"page": int(page)} if page else None),
                                      path="", doc_ord=next_ord(), produced_by="cite")
            counts["occurrences"] += 1
            counts["citations"] += 1

    # --- Named concepts (acronyms / glossary-notation terms): one CONCEPT entity
    # per concept with the decl/use split — the input the sTeX projector needs. ---
    from . import concepts as _concepts

    def _occ_node_path(section_id):
        secobj = objs.get(section_id)
        return (sec_node.get(section_id, root.id),
                secobj.props.get("section_number", "") if secobj else "")

    counts["concepts"] = 0
    for rec in _concepts.concept_records(doc):
        e = resolve_content(EntityType.CONCEPT, rec["kind"], f"concept|{rec['name']}",
                            name=rec["name"], expansion=rec.get("expansion"))
        node, path = _occ_node_path(rec["define"].get("section_id"))
        page = rec["define"].get("page")
        if not occ_exists(e.id, node, page, "definition"):
            occurrence.define(graph, e.id, node, pdf=({"page": int(page)} if page else None),
                              path=path, doc_ord=next_ord(), produced_by="concepts")
            counts["occurrences"] += 1
        for occ in rec["occurrences"]:
            node, path = _occ_node_path(occ.get("section_id"))
            page = occ.get("page")
            if not occ_exists(e.id, node, page, "reference"):
                occurrence.add_occurrence(graph, e.id, node,
                                          pdf=({"page": int(page)} if page else None),
                                          path=path, doc_ord=next_ord(), produced_by="concepts")
                counts["occurrences"] += 1
        counts["concepts"] += 1

    _trans.record_batch(graph, "ingest_docmodel", _snap, source_ids=[root.id])
    return counts
