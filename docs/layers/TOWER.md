# The tower — unifying structure over L0–L8

This document owns everything that concerns the **relations between** layers.
Per-layer content lives in the layer files ([index](README.md)).

The one-sentence summary: PDFDRILL has been building a single structure all
along — **a stratified standoff graph in which upward maps are lossy
claim-producers, downward maps are exact ordered supports, splits are
multi-fragment supports, identities are level-canonical hashes, and metrics
are weighted paths** — and the abstraction step is not new machinery but
unifying `Realization`, `Alignment`, `Evidence.source`, and `grounding` into
one `support` relation with a `level` tag on every node.

## The pattern: a stratified anchored graph (tower of quotients)

Each level Lₙ is a set of typed nodes with (a) an intra-level structure
(order, adjacency, tree, graph — varies per level) and (b) a level-canonical
identity function. Between adjacent levels there are exactly two maps, and
they are **not inverses**:

### Support (downward, γ) — exact and total

Every node at Lₙ has an *ordered list of selectors* into Lₙ₋₁ (or into base
media for L1). A selector = `(target node or media, range/region, ord, role)`.
Crucially the list may have length > 1 and the targets need not be contiguous
or even on the same page — **a split element is simply a node whose support
has more than one fragment.**

- `Realization` already IS this for L5→L3/L4.
- G3's `{pdf, path}` is this for L7→(L1, L5) — note it is a *double* support,
  one selector per coordinate system.
- The generalization: make support uniform from L2 up to L8.

### Abstraction (upward, α) — partial, lossy, evidence-producing

A map that *proposes* Lₙ₊₁ nodes from Lₙ patterns. Every producer in the repo
is an α: line-grouping (L3→L4), block detectors and `tsv_gcn` (L4→L5), the
math assembler (L5→L6), `ingest_docmodel`/Schwartz-Hearst (L5/L6→L7), schema
filling (L7→L8). The quantitative layer (2026-07-02) adds two α maps —
SO.QUANT.EXTRACT (Formula/Equation latex + prose → typed quantity records,
L5/L6→L6) and SO.MEAS.BIND (transcluded quantities → concept-bound
measurements, L6→L7) — and two γ-checker families: VER.* (arithmetic
recompute of derivations) and PHY.* (bounds/conversion/conservation/
monotonicity/uncertainty), both wired into `compiler.compile()` as
`check_quantities` (a refuted derivation is a critical warning; the outcome
lands as `arith` evidence on the QUANTITY node).

**α is lossy and unreliable; γ is exact and total.** This asymmetry is the
formal content of "retrieval searches high, import populates low": queries run
against the abstract level and are *verified* by following γ — which is
literally what `compiler.py`'s grounding check does today. (In
program-analysis terms this is the abstract-interpretation discipline: α/γ as
a Galois connection, with the compiler checking soundness; the theory's main
demand is that **γ(α(x)) must cover x**.)

## Design inspirations that match this shape

- **Standoff-annotation architectures** (UIMA CAS over an immutable
  subject-of-analysis; ISO LAF/GrAF "graphs of annotations over regions of
  base data"; W3C Web Annotation composable selectors): many typed layers over
  one base, linked by selectors. Their lesson: **base media are immutable and
  everything above L1 is standoff**, so layers can be recomputed
  independently.
- **Kythe**: inter-level links should pass through **anchor nodes** rather
  than coupling elements directly, so re-running a producer invalidates
  anchors, not identities — exactly what `docmodel`'s `Anchor` anticipates.
- **Scope graphs / stack graphs**: the model for the L6→L7 promotion —
  resolving a symbol use to its declaration is path-finding through scope
  nodes; glossary/notation sections ARE the scope nodes, and per-document
  subgraphs compose file-incrementally (what makes multi-document tractable).
- **Multilayer-network formalism**: intra-layer edge sets plus typed
  inter-layer couplings, with path/centrality definitions traversing both —
  ready-made graph metrics over exactly this object.

## Minimal concrete schema (additive — mostly a relabeling of G4)

```
node(id, level, type, subtype, canon_hash, props)        -- ALL levels, one table
support(node_id, frag_ord, target_id | media_ref,
        selector,            -- bbox | char-range | stream-range | tree-path
        axis,                -- 'pdf' | 'logical' | 'stream'
        role)                -- 'body' | 'continuation' | 'definition' | ...
edge(subject, predicate, object, ord, role, confidence,
     produced_by, level_from, level_to, grounding)
```

Existing structures embed **without loss**:

| Existing idiom | Tower form |
|---|---|
| Stream/Anchor | the L3 base order |
| `Realization` rows | `support` rows with `axis='stream'` |
| `Alignment` | a same-level edge with `predicate=kind` |
| `SemanticGraph` relations | level-7 intra-edges |
| G3 occurrences | (7→5, 7→1) support pairs |
| `content_hash` | `canon_hash` where the level defines a canonical form: pixel hash at L1, normalized string at L3, canonical LaTeX at L6, moniker `bibkey+hash` at L7/8 |

The two genuinely new commitments: **every node carries `level`**, and
**`support` is one uniform relation** instead of four idioms.

## Split recovery

A split is *detected* as a well-formedness violation at level n and *repaired*
as a re-segmentation at level n−k, recorded as **added support fragments —
never as text mutation**. The energy that drives the repair is
level-specific:

| Split kind | Level | Repair energy | Status |
|---|---|---|---|
| hyphenated word | L5 | dictionary membership | implemented (`dehyphenate`, `spellqc`) |
| cut equation | L6 | bracket/environment balance + MathPix-render QC score | verification half implemented (`compare_math`) |
| cut table | L6 | column-count and header consistency | open |
| cut list | L6 | marker-sequence continuation (`marker_family`) | partially implemented (`blocks`) |
| cross-page footnote | L5/L4 | footnote-mark ↔ body pairing + `continuity.py` margin tokens ("Fortsetzung Seite 3" is an explicit, printed *support pointer*) | detection implemented |

The repaired object keeps fragments with `role='continuation'`, so **the split
history remains queryable** — important because the repair itself is a
confidence-bearing claim. MathPix's column detection is, in these terms, one
fixed α that cuts support where it shouldn't; owning the support relation
means the stack can overrule it.

## Level skipping

The adjacent-level pairs are the default, not a law: `edge.level_from/level_to`
admits **(1→8)** — a decoded GiroCode populating the invoice frame — and
**(0→8)** — embedded XML populating the classification. This is what makes the
pdfinfo-level exclusion legitimate rather than a hack: an L8 query answered
entirely by L0-supported nodes never triggers rendering or OCR. The compiler's
only job is that *whatever* path was taken, **the support chains bottom out in
base media**.

## Metric functions over the tower

Three scopes; this is where the tower connects to the conceptual-spaces
program ([L8](L8-ontology.md)).

### Within a level — native metrics

| Levels | Metric |
|---|---|
| L1–L4 | Euclidean / IoU over bboxes |
| L3–L5 | edit distance over canonical strings |
| L6 | tree-edit / path-set similarity over operator trees (Tangent/Approach0 family) |
| L7 | graph distance + embedding cosine over entities |
| L8 | conceptual-space distances (Gärdenfors quality dimensions — the *intended* metric, everything below supplies coordinates) |

### Across levels — transported metrics

The support relation transports metrics: **pull down** a level-n metric as a
set distance over supports (Hausdorff over fragment bboxes answers "are these
two L7 occurrences physically adjacent?"), or **push up** a level-(n−1) metric
as a quotient metric ("how far apart are two concepts, measured by the minimum
distance between their occurrence sets"). Formally the whole tower is one
weighted directed graph and any cost assignment makes path length a
(Lawvere-style) metric; practically **every distance query compiles to the
same G4 SQL shape** — joins on `support` and `edge` with an aggregate.

### Between documents

A soft assignment cost between their L7/L8 node sets under identity
constraints — a generalization of what `continuity_scorer.py` + `segment.py`
already do for scanned mail (signature match + sequence consistency = a
two-term document metric). The same functional with formula content-hashes and
concept monikers as the matchable atoms gives "how close are these two papers"
for free.

## Open work (tower-level)

- The uniform `node/support/edge` tables (the two new commitments) as an
  additive projection alongside G4. *(Partial: the G4 view now also
  materializes `observation`, `bundle`/`bundle_member`, and
  `kitem`/`kitem_evidence` projections — kitem evidence rows are support-shaped
  `{bibkey, node, range, role}`; the single uniform relation is still open.)*
- Systematic split repair recorded as `role='continuation'` support fragments
  (per-kind energies in the table above).
- Cross-level metric queries as canned G4 SQL.
- The L7→L8 fixpoint is in place (`semantic/fixpoint.py`: stratified passes,
  content-hash quiescence); extending it downward (re-running α producers on
  repair) is open.
