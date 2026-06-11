# L7 — Semantic graph level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

The **primary persistent artifact** (`semantic/graph.py`'s own docstring: the
graph is primary, extractors are sensors). One model unifies scientific and
commercial documents because the core predicates are domain-agnostic.

## Nodes

`Entity{id, type, subtype, props, evidence[]}` over the closed `EntityType`
vocabulary:

- agents: PERSON, COMPANY, ORGANIZATION, AUTHORITY, BANK, DEPARTMENT
- documents: DOCUMENT, PAPER
- scientific objects: FORMULA, IMAGE, TABLE, CITATION, CONCEPT
- commercial objects: BANK_ACCOUNT · plus EVENT

**Identity is not assigned, it is resolved**: `IdentityResolver` merges on
STRONG_KEYS (iban, vat, bic, email, tax_id, … and — added by the content-
identity layer — `content_hash`) and SOFT_KEYS (name, title). Every property
arrives as an `Evidence{source, prop, value, produced_by, version, confidence,
grounding}` row carrying its source block — **properties are claims, not
facts**; the entity's value is *derived* (best by confidence, ties→recency).

## Edges

`Relation{subject_id, predicate, object_id, confidence, produced_by, version,
grounding}` over `RelationType`:

- scientific: CITES, DERIVED_FROM, EXPLAINS, CONTAINS, CONTRADICTS,
  IMPLEMENTS, REFERENCES
- commercial: OWNS, SENDER, RECEIVER, REPRESENTED_BY, ACTS_FOR, PUBLISHES,
  BELONGS_TO, ISSUED_BY, SENT_TO, HAS_ATTACHMENT

## The four grounding sublayers (G1–G4)

All ride inside the open `Relation.grounding` dict — zero schema change
(`src/semantic/layers/`, detail snapshot:
[DATA-STRUCTURES-2026-06-09](../DATA-STRUCTURES-2026-06-09.md)):

| G | Module | Mechanism |
|---|---|---|
| **G1 ordering** | `layers/ordering.py` + `fracidx.py` | fractional base-62 keys in `grounding["ord"]`; insert-between mints exactly ONE key |
| **G2 content identity** | `layers/content_identity.py` | `content_hash = blake2b(canonical form)` as a strong key → keyless scientific objects dedup across re-OCR |
| **G3 occurrence** | `layers/occurrence.py` | dual-positioned edges on the REFERENCES carrier: `grounding = {layer:"occurrence", pdf:{page,bbox}, path:"I.2.3", role: definition\|reference, ord}` — every occurrence simultaneously addressed in the PDF and the logical-tree coordinate system |
| **G4 SQLite view** | `layers/sqlite_view.py` | indexed node/edge projection with `ord/layer/role/pdf_page/bbox/logical_path` lifted into columns (the `bun:sqlite` TiddlyWiki bridge) |

## Concepts — the in-graph symbol table

`semantic/concepts.py` realizes the **declaration/use split** the LaTeX AST
lacks (see [L6's negative result](L6-expression-syntax.md)): each named
concept (acronym via Schwartz-Hearst; term/symbol via the LaTeX-list sections)
becomes ONE `CONCEPT` entity with exactly one `role=definition` occurrence and
N `role=reference` occurrences, dual-positioned via G3.

## Validation — the compiler

`semantic/compiler.py` (Phase D) is the deterministic gate:

- relation **type signatures** (subject/object type sets like AGENT);
- **grounding verification** — cited `evidence_text` must literally occur in
  the cited block (an **L7→L3 check**; pdfdrill's edge: it HAS the OCR text);
- dangling-reference detection;
- `DERIVED_FROM` acyclicity (provenance is a DAG);
- functional-relation contradiction flags (two issuers).

## Producers (α into this level)

`build.ingest_document` (commercial: sender/IBAN/BIC/address evidence),
`build.ingest_docmodel` (scientific: section tree by G1, items deduped by G2,
occurrences by G3, concepts), `attribution.py` (region-based sender/recipient),
`geometry_columns` margin confirmation evidence, QR evidence (L1→L7/8).
Projectors out: `stex.py` (enriched LaTeX / sTeX), `render.py`,
`docops/projectors/scikgtex.py` (ORKG XMP).

CLI: `semantic [--store graph.json]` (accumulates **across documents** — one
Company gathers evidence from many), `stex`, `scikgtex`.

## Open work

- Fuzzy soft-key matching (rapidfuzz) — entities merge only on strong evidence
  today.
- Segment-aware ingestion refinements; individual/tradesperson senders.
- Graph→linked-Tiddler projection; the optional GPT-4o page pass validated by
  the compiler.
