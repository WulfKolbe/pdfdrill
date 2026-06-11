# L6 — Expression-syntax level (the math-compiler front end)

Status: **partial** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

The *internal* structure of non-prose L5 objects.

## Structure per object kind

| Object | L6 structure | Modules |
|---|---|---|
| Equation/Formula | `latex` (+ `latex_original` vs preamble-**expanded** form), `refnum`, `cdn_url`; canonical form = `canonicalize_latex` + `content_hash` | `math_assembler.py`, `latex_source.py`, `eqnums.py` (equation numbers fused from geometry), `compare_math.py` |
| Table | span-aware row/cell structure: `cells = [{row, col, row_span, col_span, text, region?}]` + findable `columns` names | `table_structure.py` (+ design spec `../superpowers/specs/2026-06-10-span-aware-tables-design.md`) |
| List | recursive nesting tree (marker families, indent levels, geometry re-split) | `blocks.py` |
| Citation/Reference | citekeys, resolved BibTeX fields | `bibliography.py`, `reference_detector.py`, gold `.bbl`/`.bib` ingest |
| Sentence (prose) | dependency graphs, entities | Stanza via `docops/nlp_stanza.py` |

## The verification loop (L6↔L1)

`compare_math.py` aligns the LaTeX reading against the MathPix-rendered crop
(snip/tex QC scores) — the abstract claim is verified against base media,
exactly the TOWER's "queries run high, verify by following γ" discipline.
`scoring.py` adds corroboration (≥2 independent readings agreeing clears a
low-confidence flag).

## The hard-won negative result (the bridge to L7)

**The raw LaTeX AST is useless** because L6 syntax has no binding structure:
`\psi` in section 2 and `\psi` in appendix B are the same AST leaf but
different symbols. What IS useful — the LaTeX lists (acronym, glossary,
notation, nomenclature, symbol list, index) — is precisely the missing
**symbol table**: declaration sites with scopes. That observation is the
bridge to [L7](L7-semantic-graph.md): `concepts.py` realizes the
declaration/use split in the graph, and a symbol is only meaningful as
*(theory, name)* — never as a bare token (see [L8](L8-ontology.md)).

## Inter-layer notes

- Level-canonical identity: `canonicalize_latex` (collapse cosmetic spacing,
  `\left/\right`, single-token braces) → `content_hash` — the L6 entry in the
  TOWER's `canon_hash` column.
- Native metric: tree-edit / path-set similarity over operator trees (the
  Tangent/Approach0 family) — not yet implemented; edit distance over
  canonical strings is the working approximation (`scoring.normalize_latex`).
- Split energy at this level: bracket/environment balance + the render QC
  score for cut equations; column-count/header consistency for cut tables;
  marker-sequence continuation for cut lists.

## Open work

- Operator-tree metric (Tangent-style) over canonical LaTeX.
- Cut-equation/table/list repair driven by the level energies above
  (detection exists; systematic repair via added support fragments does not).
- BibTeX micro-grammar to separate title/journal/volume on heuristic
  References.
