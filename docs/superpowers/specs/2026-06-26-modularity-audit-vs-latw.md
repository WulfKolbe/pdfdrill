# Modularity audit — PDFDRILL builders vs the LATW TypeScript scanners

**Status:** PLAN (not yet executed). Triggered by the 2110.11150 bug where the
symbol `$f$` (used 20×) produced 20 separate `_FO` tiddlers — impossible in the
LATW modular design, where `FormulaScanner.processMathExpressions` dedups by
content (`getKeyForFormula`) and reuses one tiddler key.

## Why the bug happened (the structural lesson)

PDFDRILL has TWO model-build paths with DIFFERENT structure:

- **MathPix / OCR path** — a real module pipeline (`src/docmodel/modules/*`,
  loaded from `config.json` by `procOrder`). Each object type has its own
  scanner. `FormulaProcessor` **already dedups** (`self._dedupe`, one object +
  many realizations). This path was correct.
- **LaTeX-source path** — `latex_source.build_source_model`, a **single
  monolithic function** that inlines everything. It re-implemented inline-formula
  extraction WITHOUT the dedup that the modular path has — so the same content
  became N objects. Fixed 2026-06-26 (content-keyed `formula_titles` map), but
  the root cause is that the monolith duplicates logic the modules already own.

**Thesis:** every capability that exists as a `docmodel` module should have ONE
implementation that BOTH paths call. The source path should be a set of scanners
over the `.tex`, not a parallel monolith. This audit enumerates the divergences.

## Reference: LATW scanners (`~/MX/LATW/src/latw/`)

```
BibliographyModule  DocumentHeaderModule  ErrorRecoveryModule
CenteredElementScanner  EnvironmentCleaner  EnvironmentWrapperScanner
ComplexFormulaScanner  FootnoteAnchorScanner  FormulaScanner
GraphicsScanner  InlineElementScanner  InputScanner  LatexEnvironmentAnalyzer
LineMacroScanner  MacroScanner  MarginnoteScanner  MathMacroScanner
ParagraphProcessor  ParagraphScanner  PreambleScanner  ReferenceScanner
SectionScanner  TableScanner  TikzScanner
```

## Audit checklist (per capability: LATW module → PDFDRILL homes → divergence)

| Capability | LATW | PDFDRILL MathPix module | PDFDRILL source (`latex_source`) | Divergence to check |
|---|---|---|---|---|
| Inline/display formula + **dedup** | FormulaScanner | `modules/formula.py` (dedups ✓) | `build_source_model` (**now** dedups) | ✅ closed 2026-06-26; verify both use the SAME content key + display flag |
| Complex/multiline formula | ComplexFormulaScanner | EquationProcessor | `extract_display_equations` | does source handle align/gather/cases line-splitting like the module? |
| Sectioning | SectionScanner | HeaderProcessor | `extract_sections` (+`\appendix`, 2026-06-26) | level map parity; `subsubsection` (fixed); appendix on MathPix path is overlay-only |
| Macros / math macros | MacroScanner, MathMacroScanner, LineMacroScanner | — (preamble) | `collect_macros`/`expand_macros` | source-only; MathPix path has no macro expansion (expects MathPix-expanded LaTeX) |
| Preamble | PreambleScanner | — | `split_preamble`/`standalone_preamble` | source-only |
| Graphics / TikZ | GraphicsScanner, TikzScanner | DiagramProcessor/PictureProcessor | `extract_graphics` | env list parity (`tikzcd`, `tabularx`, `longtable`); caption capture |
| Tables | TableScanner | TableProcessor (`table_structure`) | `extract_graphics` (tabular) | source path has NO span-aware cells — big gap |
| References / bibliography | ReferenceScanner, BibliographyModule | `bibliography.parse_bibliography` | `build_bibliography_from_source` | three+ parsers; consolidate (see ReferenceScanner.ts) |
| Citations | (inline) | CitationProcessor | `extract_citations`/`_transclude_cites` | numeric vs alpha vs author-year linking parity |
| Footnotes | FootnoteAnchorScanner | FootnoteProcessor | `extract_footnote_paragraphs` (heading_cleanup) | source path coverage |
| Margin/side notes | MarginnoteScanner | SidenoteProcessor + `geometry_columns` | — | source path has none |
| Paragraphs | ParagraphScanner, ParagraphProcessor | ParagraphProcessor | `_prose_chunks` | block-splitting parity |
| Input expansion | InputScanner | n/a | `expand_inputs` | ✓ (multi-file `\input`, fixed earlier) |
| Environment cleanup/wrap | EnvironmentCleaner, EnvironmentWrapperScanner | (various) | `_clean_prose` | leaked `\setlength` etc. → LTX (done); audit completeness |
| Error recovery | ErrorRecoveryModule | — | truncation tolerance (markdown_source) | no general recovery in source path |

## Plan of work (later)

1. **Extract shared scanners.** Pull the dedup-bearing logic (formula, citation,
   section) into pure functions both paths import — kill the duplication that let
   this bug exist. Candidate: a `latex_scan/` package mirroring `modules/` so the
   source path becomes a thin pipeline, not a monolith.
2. **Parity test matrix.** One fixture `.tex` exercised through BOTH paths
   (where a PDF exists) asserting equal object counts per type + equal dedup
   (distinct == total for repeated symbols). A regression net for every row above.
3. **Close the named gaps first** (highest value): span-aware tables on the
   source path; margin/side notes; complex-formula line splitting.
4. **Integrity gate everywhere.** `tiddler_integrity` (dangling/orphan) should run
   in tests for every build path, not just MathPix — it would have caught a
   dedup regression as 0 orphan but the per-object explosion needs a distinct-vs-
   total formula assertion (added 2026-06-26 in `test_latexbook.py`).

## Done in this pass

- `build_source_model` dedups inline formulas by expanded-LaTeX content key
  (`formula_titles`), matching `FormulaProcessor`/`FormulaScanner`. 2110.11150:
  465 → 273 Formula objects, `f` 20→1, integrity 0 dangling-FO / 0 orphan.
  Test: `tests/test_latexbook.py::test_build_source_model_dedupes_repeated_inline_formula`.
