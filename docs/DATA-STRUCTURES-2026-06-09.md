# Data structures added 2026-06-09

> **Historical snapshot** (the day G1–G4 landed). The living documentation is
> the layer tower: [`docs/layers/`](layers/README.md), esp.
> [`L7-semantic-graph.md`](layers/L7-semantic-graph.md) for what grew on top
> (bundles, gaps, kitems, fixpoint, rulebook).

A single day's work added the **composable semantic-graph layer stack** plus two
**graph→LaTeX projectors**. Everything is *additive*: it rides inside existing
types (mostly the open `Relation.grounding` dict) with **zero schema change** to
`graph.py`/`entity.py`/`relation.py`/`identity.py`/`evidence.py`, and nothing on
the docmodel/docops live path was modified.

Commits: `11ff667` (layers) → `3bf3f60` (Phase 2 ingest) → `a0a64b2` (concepts)
→ `ec366bb` (stex) → `292544e` / `aebfa61` (scikgtex).

---

## 1. `fracidx` — fractional order keys (`src/semantic/fracidx.py`)

A pure-stdlib port of rocicorp/fractional-indexing (CC0). **Order keys are plain
strings**; lexicographic string comparison *is* logical order, so they sort in
`sorted()`, SQL `ORDER BY`, and TiddlyWiki filters with no special handling.

- **Shape:** a base-62 string over `DIGITS = 0-9A-Za-z`.
- **Invariant:** to place an item *between* two neighbours you mint **one** new
  key from their two keys — **no other row changes** (the "insert without
  re-org" requirement).
- **API:** `key_between(a, b)`, `key_after(a)`, `key_before(b)`,
  `n_keys_between(a, b, n)` (`None` = open end). Fuzz-tested.

## 2. The four graph layers (`src/semantic/layers/`)

Each capability the graph lacked, expressed as a **discriminator inside
`Relation.grounding`** (an open dict) rather than a new field/enum — so it is
removable and promotable later by moving one key to a real field.

### L1 — ordering (`ordering.py`)  → `grounding["ord"]`
Sibling order that survives insertion. A relation with no `ord` sorts first
(empty string) and can be back-filled.
- `append_child` / `insert_child(after=, before=)` / `ordered_children` /
  `first_occurrence` / `occurrences_in_order` / `move`.
- Insert-between adds **exactly one** edge.

### L2 — content identity (`content_identity.py`)  → strong key `"content_hash"`
Keyless scientific objects (FORMULA/TABLE/FIGURE) dedup across re-OCR.
- At **import time** does `identity.STRONG_KEYS.add("content_hash")` (idempotent)
  — the only touch to the resolver, and it's purely additive.
- `canonicalize_latex(latex)` (drop `\left`/`\right` + spacing macros + collapse
  whitespace — the one corpus-specific knob) → `content_hash(latex)` =
  `blake2b(…, digest_size=16)` hex.
- `resolve_formula(resolver, latex, source, …)` emits two `Evidence` rows
  (`latex`, `content_hash`) and routes through the **existing** resolver keyed by
  `[("content_hash", h)]` → same equation hashes identically → merges.

### L3 — occurrence, dual-positioned (`occurrence.py`)  → `grounding["layer"]="occurrence"`
Each occurrence-bearing item (numbered/loose equation, table, figure, external
source, bib entry, symbol/index term) records WHERE it occurs in **both
coordinate systems** at once, on the `REFERENCES` carrier predicate:
- `grounding["pdf"] = {"page": int, "bbox": [x0,y0,x1,y1]}` — the PDF axis.
- the edge's **object** = the containing structural node; `grounding["path"]` =
  human path (`"I.2.3"`) — the logical axis.
- `grounding["role"]` ∈ `{definition, reference}`; `grounding["ord"]` =
  document-order key (so "first by reading order" = min ord, insertion-order
  independent).
- `define` / `add_occurrence` / `definition` / `occurrences` /
  `further_occurrences`.

### L4 — SQLite read view (`sqlite_view.py`)  → indexed projection of `graph.json`
Decoupled from the Python classes (consumes the **sidecar dict** only), so a
`bun:sqlite` reader on the TiddlyWiki side opens the identical file. Two tables:
- `node(id, type, subtype, props)`
- `edge(subject, predicate, object, ord, layer, role, pdf_page, bbox,
  logical_path, confidence, produced_by, grounding)` — the L3 PDF page + logical
  position are **lifted out of grounding into indexed columns**.
- Indexes: `edge_fwd(subject,predicate,ord)`, `edge_back(object,predicate,ord)`,
  `edge_page(pdf_page)`, `node_type(type)`.
- Queries: `children_in_order`, `occurrences_of`, **`items_on_page(page)`** (the
  PDF axis), **`occurrences_in_node(node_id)`** (the logical axis).

## 3. The concept record (`src/semantic/concepts.py`)

A *named concept* = a term introduced once and referred to many times (the LaTeX
`\acro`/`\newglossaryentry`/`\index` idea), mapped onto the graph's
definition/reference split. `concept_records(doc)` is **pure** (no graph) and
returns, per concept, the dict:

```python
{
  "name": str,                 # "CNN" | "metric tensor" | "psi"
  "kind": "acronym" | "term" | "symbol",
  "expansion": str,            # "Convolutional Neural Network" (acronyms)
  "define": {"page": int, "section_id": str},        # the declaration site
  "occurrences": [ {"page": int, "section_id": str}, ... ],  # the use sites
}
```

- Acronyms via the **Schwartz-Hearst** long-form/short-form algorithm over prose.
- Terms/symbols from **glossary / notation / nomenclature / abbreviation /
  symbol-list / index SECTIONS** (`TERM — definition` entries); a *Notation/
  Symbol* section yields `kind="symbol"`, a *Glossary* one yields `kind="term"`.
- `ingest_docmodel` turns each into a `CONCEPT` entity (subtype = the kind),
  content-hash-deduped, with the L3 dual-positioned definition + reference
  occurrences.

## 4. Phase-2 docmodel→graph ingest (`src/semantic/build.py`)

`ingest_docmodel(graph, resolver, doc, bibkey, source=None)` maps the scientific
docmodel onto the same graph **through the layers** (the structures above are the
storage; this is the producer):
- chapter/section `CONTAINS` tree ordered by **L1**;
- Equation/Formula→FORMULA, Table→TABLE, Picture/Diagram→IMAGE (+`image_source`
  via `DERIVED_FROM`), Reference→CITATION — all **L2** content-hash-deduped;
- each item's **L3** dual-positioned occurrence (PDF `{page,bbox}` from the
  docmodel `region`; logical = the containing section node + `path`);
- in-text Citations (`cited_reference_id`) → further occurrences of their
  Reference; concepts via §3.
- Idempotent: re-run is `has_relation`-guarded (tree) + occurrence-existence
  guarded. The Document root is keyed by `[("content_hash", …), ("doc_id", …)]`.

## 5. Projectors over the graph (LaTeX outputs)

Not data structures themselves, but the **mappings** they materialise are part of
the model:

### `src/semantic/stex.py` — enriched-LaTeX / sTeX
- `project_latex(graph)` — a compilable doc with **all the LaTeX lists** driven
  by the §3 concepts: ACRONYMS (`\newacronym`), GLOSSARY (`\newglossaryentry`),
  TABLE OF SYMBOLS (`type=symbols`), INDEX (`\index`/`\printindex`) — each line
  carrying pdfdrill's PDF-page provenance.
- `project_stex(graph)` — the sTeX form: a `\symdecl` per concept in an
  `smodule`, an `sdefinition` at the definition site, `\symref` at each use.
- lualatex compile-proven.

### `src/docops/projectors/scikgtex.py` — SciKGTeX / ORKG (a docops `BaseProjector`)
`SciKGTeXProjector.project(doc)` → SciKGTeX-annotated LaTeX whose compiled PDF
carries **XMP/RDF in the ORKG vocabulary**. The projection map:
- `\metatitle*`/`\metaauthor*`/`\researchfield*` ← `doc.meta` (arXiv-enriched);
- invisible starred contribution **roles** from docmodel structure — Abstract →
  `\researchproblem*` (P32); a Method/Results/Conclusion **Section caption** →
  `\method*` (P1005) / `\result*` (P1006) / `\conclusion*` (P15419);
- `\contribution*{name}{value}` for numeric **facts** (accuracy/F1/precision/
  recall/p-value/n → ORKG P-ID resolved offline by the package's bundled table);
- **one** `\contribution*{cites}{\uri{doi}{citekey}}` **per DOI** (deduped) so
  each becomes its own `<rdf:Description rdf:about="https://doi.org/…">` with an
  `<rdfs:label>` — N `\uri` in a single annotation collapse to one node, so they
  must be emitted separately.
- Resulting XMP: `orkg:Paper` (hasTitle/hasAuthor/hasResearchField) +
  `ResearchContribution`s. Verified on 576-659-1-PB: 4 roles + **19 DOI nodes**.

---

### Why grounding-dict layers (the design note)

Strong keys live on entities; everything new here is an *edge property*. Putting
it in the already-open `grounding` dict means: no migration of existing
`graph.json` files, old passes that omit a key degrade gracefully (sort first /
treated as absent), and each layer is independently promotable to a first-class
field once it has proven out — without changing any query helper.
