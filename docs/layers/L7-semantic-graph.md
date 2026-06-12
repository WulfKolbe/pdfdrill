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

## Bundles, observations, gaps (the sheaf-plan adoption, 2026-06-12)

- **`semantic/bundles.py`** — the per-entity GLOBAL SECTION: `bundle(graph,
  id)` assembles `{canonical, aliases, mentions (G3, doc order, dual-
  positioned), claims (evidence rows + provenance), linked (per predicate),
  consistent}`. **Derived, never a second writable store** (a stored bundle
  is a cached join that drifts). `all_bundles(graph)` feeds the projections.
- **Observation = Evidence** (decision record): "pass X asserted Y about node
  Z" is the existing `Evidence` row; the G4 view now materializes it as an
  indexed **`observation` table** (one row per evidence record) plus
  **`bundle`/`bundle_member` tables** via `load_view(graph, bundles=…)` — a
  query hit on any alias surfaces the whole bundle. No new primitive.
- **`semantic/gaps.py`** (`pdfdrill gaps <pdf|md>`) — "cohomology as a
  linter": where the compiler validates what IS there, this reports what is
  MISSING, as diagnostics with locations: `acronym_undefined` (used ≥2×,
  never expanded — producer half: `concepts.undefined_concept_uses`),
  `symbol_undefined` (greek in display math, no notation entry),
  `claim_unsupported` (novelty sentence without citation),
  `citation_unmatched` (trusts the linkers' `cited_reference_id` first).
  Eyeballed per the acceptance test: the thesis reports exactly bibsource's
  7 unlinked citations; restriction maps stay deferred until real gap output
  motivates their semantics.

## Kitems — the knowledge store half of the two-store plan (2026-06-12)

Documents are the axioms; kitems are theorems; the evidence chain is the
proof object. Decision: kitems live **canonically as entities**
(`EntityType.KITEM`, subtype = rule/claim/definition/derivation/reuse_event/
contradiction) — `statement_md`/`stratum`/`valid_at` as properties, the
evidence chain as `Evidence` rows with span grounding `{bibkey, node, range,
role, page}`, kitem_derivation as `DERIVED_FROM` edges. The `kitem`/
`kitem_evidence` SQL tables are **G4 projections** (computed at view time),
never a second writable store.

- `semantic/kitems.py`: `emit_kitem` (content-hash dedup ⇒ re-emitting is a
  **fixpoint no-op**, evidence accumulates), `status_of` — compiler-automatic:
  *proposed* (no grounded span) → *supported* (≥1 span, or all parents
  supported, transitively via DERIVED_FROM) → *accepted* (≥2 INDEPENDENT
  spans in the transitive closure — corroboration) → *disputed* (only a
  CONTRADICTS edge demotes; no LLM promotes). `kitem_tiddlers` emits
  `$Bibkey_KI<serial>` tiddlers with the `khash` drill-down handle.
- **Render-policy contract** (`docops/transclusion_render.py`): the canonical
  paragraph text (transcluded tiddler form) is consumed by strata only through
  named policies — `detranscluded` (natural-language gloss; what `nlp_stanza`
  has always used, implementation now shared) and `typed_gloss`
  (`[FORMULA 12]` / with a semantic lookup `[FORMULA: mass eigenvalue
  relation]` — for transclusion-aware stratum-3 modules).

Next per the build order: stratum monotonicity in BaseModule + the fixpoint
driver; then the vertical slice (stratum-4 claim extractor + rulebook
projector on 2004.05631).

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
