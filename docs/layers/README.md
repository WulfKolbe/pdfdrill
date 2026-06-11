# The PDFDRILL layer tower — documentation index

The toolchain is one stratified stack, L0–L8. **Each layer has exactly one
canonical document in this directory** — that file is the single home for that
layer's structure, modules, invariants, and open work.

## Parallel-work contract

These documents exist so several layers can be worked on **in parallel without
interference**:

1. When working on layer N, edit **only** `L<N>-*.md` (plus code/tests).
2. Anything that concerns the *relations between* layers — support/abstraction
   maps, the uniform schema, split recovery, level skipping, metrics — goes in
   [`TOWER.md`](TOWER.md), never in a layer file.
3. `CLAUDE.md` (repo root) keeps only operational instructions and a pointer
   here; do not duplicate layer documentation into it.
4. This index stays a table of one-liners. If your edit to README.md is longer
   than one row, it belongs in a layer file.

## The layers

| Layer | Doc | One-liner | Status |
|---|---|---|---|
| **L0** | [L0-container.md](L0-container.md) | PDF container / digital-native channel: pdfinfo, fonts, image records, annotations, XMP/attachments — exact, ~free, pre-render | implemented |
| **L1** | [L1-raster.md](L1-raster.md) | Raster/pixel: page bitmaps + derived primitives (blobs, rules, QR payloads, glyph-image font id) | implemented |
| **L2** | [L2-glyph.md](L2-glyph.md) | Glyph: one record per character (codepoint, font, baseline, bbox) from pdfplumber chars ∥ tesseract boxes | implemented |
| **L3** | [L3-text-lines.md](L3-text-lines.md) | Word/line strings: the shared 12-column TSV schema, line grouping, `pdf_lines` Stream + per-line `_geom` | implemented |
| **L4** | [L4-layout-regions.md](L4-layout-regions.md) | Layout regions: typed rects (MathPix shape) + role classifiers (margin/block/continuity) + learned elements. **Splits originate here** | implemented |
| **L5** | [L5-docobjects.md](L5-docobjects.md) | Typed document objects: `Document`/`DocObject`/`Realization`/`Alignment`, the ~16 object types, in-place mutators | implemented |
| **L6** | [L6-expression-syntax.md](L6-expression-syntax.md) | Expression syntax inside non-prose objects: LaTeX math, span-aware table cells, list nesting, citation keys, sentence graphs | partial |
| **L7** | [L7-semantic-graph.md](L7-semantic-graph.md) | Semantic graph: evidence-backed entities/relations, identity resolution, grounding sublayers G1–G4, concepts, the compiler | implemented |
| **L8** | [L8-ontology.md](L8-ontology.md) | Ontology/theory: concept grounding, theory modules (sTeX/MMT), document-class schemas, obligations/affordances | mostly planned |

## Cross-cutting documents

- [`TOWER.md`](TOWER.md) — **the unifying structure**: the stratified anchored
  graph (support γ down / abstraction α up), the uniform `node/support/edge`
  schema, split recovery, level-skipping evidence, and the metric functions
  over the tower.
- [`../DATA-STRUCTURES-2026-06-09.md`](../DATA-STRUCTURES-2026-06-09.md) —
  historical snapshot of the day the L7 grounding sublayers (G1–G4) landed.
- [`../superpowers/specs/`](../superpowers/specs/) — per-feature design specs
  (e.g. the span-aware tables design, an L6 component).

## Numbering note

An earlier informal numbering used 0/2/3/4/5 for what are now L1/L2/L3/L4/L5;
L0 (the container) was inserted because the "exclude on pdfinfo level"
efficiency lives there, and it is the layer the old list skipped.
