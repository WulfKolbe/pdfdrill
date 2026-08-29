# Props table

**Generated — do not edit.** `python3 tools/propstable.py` rebuilds it from
`src/docmodel/corpus_props.json` (a walk of the corpus) and
`src/docmodel/props_code.json` (`tools/propscan.py` over `src/**/*.py`).

Two checks in `docmodel.prop_contract` hold it, the same pair that holds the
type contract: every prop in the corpus must appear here with a reader or an
explicit reason (`table_violations`), and every prop here must occur in the
corpus (`table_not_in_corpus`).

> **Read this before writing anything that reads a prop.** The recurring
> failure is not a missing prop, it is a prop that exists, is written, and is
> read by nothing — `subtype` on 1,239,021 lines, `list_item` in 882
> documents. A reader column of `—` with a reason beside it is not a gap to
> fill blindly; it is a fact somebody measured.

## The pairs — a wrong choice here compiles silently

| pair | which to use |
|---|---|
| `latex` / `latex_original` | `latex` and `latex_code` are macro-EXPANDED; `latex_original` keeps the author's macros. Renderers compile the expanded one and need no author preamble to resolve macros (289). |
| `latex_pretail` / `trailing_punct` | `trailing_punct` is punctuation printed after the maths, set BESIDE it (025). `latex_pretail` is maths belonging to the following prose. Neither goes back into `latex`. |
| `latex_refined` | a VERIFIED refinement in a twin prop; `latex` is never overwritten (232). Reading `latex` alone ignores every accepted repair (233). |

## Every prop

118 props over 26 object types, from 1350 model.docmodel.json under ~/pdfdrill-library.

| prop | objects | on types | written by | read by |
|---|---:|---|---|---|
| `bibkey` | 2,130,740 | 24 types | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `pdfdrill/blocks.py`, `pdfdrill/commands.py`, `pdfdrill/heading_cleanup.py` +1 |
| `text` | 1,230,496 | 6 types | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `docops/mutators/dehyphenate.py`, `docops/mutators/promote_cleaned.py`, `docops/projectors/beamer.py` +15 |
| `flow_index` | 1,146,347 | 17 types | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `docmodel/modules/document_flow.py`, `docmodel/modules/document_structure.py`, `docops/projectors/common.py` +17 |
| `parent_section` | 1,102,145 | 14 types | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `docmodel/modules/document_structure.py`, `docops/projectors/latex_pipeline.py`, `docops/projectors/scikgtex.py` +10 |
| `page` | 1,099,528 | 18 types | pdfdrill model, pdfdrill links, pdfdrill bibliography, pdfdrill clean, pdfdrill injectlatex | `docops/projectors/comparison_html.py`, `docops/projectors/formula_report.py`, `docops/projectors/tiddlywiki.py` +11 |
| `next_in_flow` | 1,041,723 | 12 types | pdfdrill model | `docmodel/modules/document_flow.py` |
| `prev_in_flow` | 1,041,717 | 12 types | pdfdrill model | `docmodel/modules/document_flow.py` |
| `latex` | 643,364 | Equation, Formula | pdfdrill model, pdfdrill injectlatex | `docops/projectors/comparison_html.py`, `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py` +15 |
| `display` | 523,358 | Formula | pdfdrill model, pdfdrill injectlatex | `docops/projectors/tiddlywiki.py` |
| `from_line_index` | 303,318 | Paragraph | pdfdrill model | **—** provenance: which lines.json rows built this Paragraph. Written for traceability, consulted by hand. (mentioned in 1 file) |
| `num_lines` | 303,318 | Paragraph | pdfdrill model | **—** provenance: how many source lines the Paragraph spans. (mentioned in 1 file) |
| `paragraph_index` | 303,318 | Paragraph | pdfdrill model | **—** provenance: the Paragraph's ordinal, written for traceability. (mentioned in 1 file) |
| `to_line_index` | 303,318 | Paragraph | pdfdrill model | **—** provenance: as above, the last row. (mentioned in 1 file) |
| `kind` | 295,305 | 6 types | pdfdrill model, pdfdrill links, pdfdrill clean, pdfdrill injectlatex | `docops/projectors/formula_report.py`, `docops/projectors/tiddlywiki.py`, `pdfdrill/annotations.py` +3 |
| `region` | 220,008 | 13 types | pdfdrill model, pdfdrill clean | `docmodel/modules/table.py`, `docops/projectors/tiddlywiki.py`, `mathgold/floor.py` +6 |
| `image_id` | 202,933 | Diagram, Equation, Page | pdfdrill model | `docops/projectors/tiddlywiki.py` |
| `refnum` | 171,259 | 6 types | pdfdrill model, pdfdrill clean | `docops/projectors/common.py`, `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py` +6 |
| `cdn_url` | 136,967 | Diagram, Equation | pdfdrill model | `docmodel/modules/diagram.py`, `docmodel/modules/equation.py`, `docops/projectors/comparison_html.py` +5 |
| `latex_raw` | 112,066 | Equation | pdfdrill model | **—** GAP: the maths BEFORE normalisation, 112,066 objects. Kept so a normalisation defect is recoverable, and nothing has ever recovered one. (mentioned in 2 files) |
| `refnum_anchor` | 99,814 | Equation | pdfdrill model | `pdfdrill/eqnums.py` |
| `confidence` | 98,556 | Equation | pdfdrill model | `docops/projectors/tiddlywiki.py`, `pdfdrill/refine.py` |
| `confidence_rate` | 98,556 | Equation | pdfdrill model | `docops/projectors/tiddlywiki.py` |
| `content` | 76,396 | Footnote, ListItem, Sidenote | pdfdrill model, pdfdrill clean | `docops/projectors/distill_reader.py`, `docops/projectors/latex.py`, `docops/projectors/scikgtex.py` +7 |
| `page_height` | 72,722 | Page | pdfdrill model | **—** geometry: page dimensions in MathPix pixels; the crop path uses region and image_id instead. (mentioned in 10 files) |
| `page_number` | 72,722 | Page | pdfdrill model | `docops/projectors/tiddlywiki.py`, `pdfdrill/annotations.py`, `pdfdrill/commands.py` +1 |
| `page_width` | 72,722 | Page | pdfdrill model | **—** geometry: page width in MathPix pixels; the crop path uses region and image_id instead. (mentioned in 9 files) |
| `is_blank` | 65,966 | Page | pdfdrill model | `docops/projectors/tiddlywiki.py` |
| `languages_detected` | 65,966 | Page | pdfdrill model | **—** GAP: MathPix's script detection, 65,966 pages. Nothing consults it, including the routing that decides a vision lane. (mentioned in 1 file) |
| `citekey` | 65,189 | Citation, Reference | pdfdrill model, pdfdrill links, pdfdrill bibliography, pdfdrill injectlatex | `docops/projectors/distill_reader.py`, `docops/projectors/latex_pipeline.py`, `docops/projectors/scikgtex.py` +6 |
| `line_index` | 62,329 | ListItem, Section | pdfdrill model | `pdfdrill/blocks.py`, `pdfdrill/commands.py` |
| `caption` | 59,291 | 4 types | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `docops/projectors/beamer.py`, `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py` +14 |
| `list_index` | 53,285 | ListItem | pdfdrill model | **—** provenance: the item's ordinal, written by ListProcessor. (mentioned in 1 file) |
| `marker` | 53,285 | ListItem | pdfdrill model | `docops/nlp_stanza.py`, `docops/projectors/latex.py`, `docops/projectors/tiddlywiki.py` +2 |
| `added_by` | 46,709 | 9 types | pdfdrill bibliography, pdfdrill clean, pdfdrill injectlatex | `docops/projectors/distill_reader.py`, `pdfdrill/commands.py` |
| `latex_original` | 41,665 | 4 types | pdfdrill injectlatex | `docops/projectors/llm_compact.py`, `docops/projectors/tiddlywiki.py`, `mathlayer/annotate.py` +2 |
| `latex_code` | 29,571 | Diagram, LtxCommand, Table | pdfdrill model, pdfdrill injectlatex | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/llm_text.py` +3 |
| `number` | 26,546 | 4 types | pdfdrill bibliography, pdfdrill injectlatex | `docops/projectors/distill_reader.py`, `docops/projectors/latex_pipeline.py`, `docops/projectors/tiddlywiki.py` +2 |
| `raw_text` | 26,156 | Reference, Table | pdfdrill bibliography | `docops/projectors/distill_reader.py`, `docops/projectors/llm_text.py`, `docops/projectors/tiddlywiki.py` +2 |
| `code` | 24,901 | Diagram | pdfdrill model | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/llm_text.py` +1 |
| `language` | 24,901 | Diagram | pdfdrill model | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/llm_text.py` +1 |
| `subtype` | 24,901 | Diagram | pdfdrill model | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/llm_text.py` +1 |
| `style` | 22,120 | Citation | pdfdrill bibliography, pdfdrill injectlatex | **—** GAP: a Section's detected heading style, 22,120 objects. 259 set levels from font_size and never looked at this. (mentioned in 4 files) |
| `from_line_type` | 17,343 | Picture | pdfdrill model | `docops/projectors/tiddlywiki.py` |
| `url` | 17,343 | Picture | pdfdrill model | `docops/projectors/tiddlywiki.py`, `semantic/build.py` |
| `author` | 17,319 | Citation, Reference | pdfdrill bibliography, pdfdrill refine | `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py` |
| `year` | 17,319 | Citation, Reference | pdfdrill bibliography | `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py`, `semantic/build.py` |
| `level` | 15,846 | Section | pdfdrill model, pdfdrill clean, pdfdrill injectlatex | `docmodel/modules/document_structure.py`, `docops/projectors/beamer.py`, `docops/projectors/distill_reader.py` +3 |
| `entry_type` | 14,987 | Reference | pdfdrill bibliography | `docops/projectors/tiddlywiki.py` |
| `ref_source` | 14,974 | Reference | pdfdrill bibliography | **—** provenance: where a Reference came from. (mentioned in 3 files) |
| `label` | 13,461 | 4 types | pdfdrill bibliography, pdfdrill injectlatex | `docops/projectors/tiddlywiki.py`, `pdfdrill/bibliography.py`, `pdfdrill/commands.py` |
| `section_number` | 13,027 | Section | pdfdrill model | `docmodel/modules/document_structure.py`, `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py` +1 |
| `mathpix_text` | 11,119 | Table | pdfdrill model | `docmodel/modules/table.py`, `pdfdrill/commands.py` |
| `cells` | 10,874 | Table | — | `docops/projectors/distill_reader.py` |
| `columns` | 10,874 | Table | — | `docops/projectors/distill_reader.py` |
| `header_rows` | 10,874 | Table | — | `docops/projectors/distill_reader.py` |
| `n_cols` | 10,874 | Table | — | `docops/projectors/distill_reader.py` |
| `n_rows` | 10,874 | Table | — | `docops/projectors/distill_reader.py` |
| `numeric` | 10,695 | Citation | pdfdrill bibliography | **—** GAP: whether a table cell holds a number, 10,695 cells. No projector formats on it. (mentioned in 1 file) |
| `env` | 10,638 | 4 types | pdfdrill injectlatex | `pdfdrill/commands.py` |
| `title` | 9,904 | 5 types | pdfdrill clean, pdfdrill injectlatex | `docops/projectors/distill_reader.py`, `docops/projectors/llm_text.py`, `docops/projectors/okf.py` +5 |
| `cmd` | 9,044 | Section | pdfdrill model | `docops/projectors/tiddlywiki.py` |
| `numbered` | 7,940 | Equation | pdfdrill injectlatex | **—** redundant: equation_number is non-empty exactly when this is true. (mentioned in 4 files) |
| `anchor_marker` | 7,239 | Footnote | pdfdrill model, pdfdrill clean | `docops/projectors/tiddlywiki.py` |
| `next_sibling` | 7,034 | Section | pdfdrill model | `docmodel/modules/document_structure.py` |
| `prev_sibling` | 7,034 | Section | pdfdrill model | `docmodel/modules/document_structure.py` |
| `heading_residual_cleaned` | 6,692 | Paragraph | pdfdrill clean | `docops/projectors/tiddlywiki.py`, `pdfdrill/heading_cleanup.py` |
| `equation_number` | 6,667 | Equation | — | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/llm_compact.py` +3 |
| `is_appendix` | 3,832 | Section | pdfdrill clean, pdfdrill injectlatex | `docops/projectors/tiddlywiki.py`, `pdfdrill/heading_cleanup.py`, `pdfdrill/latex_source.py` |
| `detected_by` | 3,391 | ListItem | pdfdrill model | **—** provenance: typed vs lexical list detection (248), written to make the 248 change auditable. (mentioned in 1 file) |
| `bibtex` | 1,955 | Reference | pdfdrill bibliography | `docops/projectors/latex_pipeline.py`, `docops/projectors/tiddlywiki.py`, `pdfdrill/bibliography.py` +1 |
| `statement` | 1,889 | Proof, Theorem | pdfdrill injectlatex | `docops/projectors/tiddlywiki.py`, `pdfdrill/lean_export.py` |
| `text_source` | 1,760 | Paragraph | pdfdrill clean | **—** the text BEFORE translation. Read by `has_translation` through a tuple of prose keys, not by name — and a rebuild reverts it (275). (mentioned in 3 files) |
| `printed_title` | 1,458 | Theorem | pdfdrill injectlatex | `docops/projectors/tiddlywiki.py` |
| `starred` | 1,458 | Theorem | pdfdrill injectlatex | **—** provenance: whether the sectioning command was starred. (mentioned in 1 file) |
| `edit_source` | 1,400 | Equation, Formula | — | `pdfdrill/commands.py` |
| `latex_prepunct` | 1,400 | Equation, Formula | — | `pdfdrill/commands.py` |
| `trailing_punct` | 1,400 | Equation, Formula | — | `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py` |
| `first_section_id` | 1,346 | Document | pdfdrill model | **—** summary: written on the Document object; consumers walk the flow instead. (mentioned in 2 files) |
| `total_pages` | 1,346 | Document | pdfdrill model | **—** summary: a count written on the Document object; consumers walk the flow and count for themselves. (mentioned in 4 files) |
| `total_paragraphs` | 1,346 | Document | pdfdrill model | **—** summary: a Paragraph count on the Document object; consumers count the objects instead. (mentioned in 1 file) |
| `total_sections` | 1,346 | Document | pdfdrill model | **—** summary: a Section count on the Document object; consumers count the objects instead. (mentioned in 1 file) |
| `eq_label` | 960 | Equation | — | `pdfdrill/commands.py` |
| `env_mismatch` | 790 | Equation, Formula | — | `pdfdrill/env_balance.py` |
| `depth` | 611 | AlgorithmStep | pdfdrill injectlatex | `pdfdrill/commands.py` |
| `name` | 431 | Proof | pdfdrill injectlatex | `docops/projectors/okf.py` |
| `of_label` | 431 | Proof | pdfdrill injectlatex | **—** provenance: the label a Proof proves; proof_of carries the id that is actually used. (mentioned in 1 file) |
| `proof_id` | 430 | Theorem | pdfdrill injectlatex | `docops/projectors/tiddlywiki.py` |
| `proof_of` | 430 | Proof | pdfdrill injectlatex | `docops/projectors/tiddlywiki.py`, `pdfdrill/latex_source.py` |
| `content_source` | 362 | Footnote, ListItem, Sidenote | — | **—** the content BEFORE translation, for objects whose body is `content`. Same tuple-membership access as text_source. (mentioned in 1 file) |
| `spoken` | 333 | Equation, Formula | — | `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py` |
| `spoken_by` | 333 | Equation, Formula | — | `pdfdrill/commands.py` |
| `anchor_text` | 254 | Link | pdfdrill links | **—** GAP: a Link's visible text, 254 objects. `links` reports URLs; nothing reads the anchor. (mentioned in 3 files) |
| `context` | 254 | Link | pdfdrill links | **—** GAP: the prose surrounding a Link, 254 objects. Recorded when the link was found and never read back. (mentioned in 5 files) |
| `dest_name` | 254 | Link | pdfdrill links | `pdfdrill/annotations.py` |
| `dest_page` | 254 | Link | pdfdrill links | `pdfdrill/annotations.py` |
| `uri` | 254 | Link | pdfdrill links | **—** GAP: the Link's target. The `links` command reads the annotation layer directly rather than these objects. (mentioned in 3 files) |
| `latex_expanded_by` | 241 | Equation, Formula | — | `pdfdrill/commands.py` |
| `macros_unresolved` | 241 | Equation, Formula | — | `pdfdrill/commands.py` |
| `score` | 184 | Equation | — | `docops/projectors/comparison_html.py`, `pdfdrill/commands.py` |
| `entries` | 154 | Toc | pdfdrill model | `pdfdrill/commands.py` |
| `bibfetched` | 86 | Reference | — | `pdfdrill/commands.py` |
| `citations` | 86 | Reference | — | `docops/projectors/tiddlywiki.py`, `pdfdrill/commands.py` |
| `caption_source` | 80 | Diagram, Picture, Section | — | **—** the caption BEFORE translation. Tuple-membership access. (mentioned in 1 file) |
| `latex_fragment` | 51 | MathTail | — | **—** GAP: a partial maths value carried for reassembly, 51 objects. No reassembly pass exists. (mentioned in 1 file) |
| `position` | 51 | MathTail | — | **—** GAP: positional hint recorded with a fragment. (mentioned in 2 files) |
| `source_object` | 51 | MathTail | — | **—** provenance: the object a derived value came from. (mentioned in 1 file) |
| `latex_pretail` | 47 | Equation, Formula | — | `pdfdrill/commands.py` |
| `latex_overlaid` | 44 | Table | — | `pdfdrill/commands.py` |
| `page_before_repair` | 34 | Section | pdfdrill clean | **—** provenance: a Section's page before heading_cleanup moved it. Written with setdefault, so the scan sees no reader. (mentioned in 1 file) |
| `latex_refined` | 31 | Equation, Formula | — | **—** READ THROUGH A CONSTANT: refine.REFINED_FIELD. The `--prefer-refined` projection reads it (233); a name-literal scan cannot see that. (mentioned in 3 files) |
| `indent_norm` | 21 | List | — | **—** GAP: normalised ListItem indentation, 21 objects. (mentioned in 2 files) |
| `list_type` | 21 | List | — | **—** GAP: ordered vs unordered, 21 objects. No projector distinguishes them. (mentioned in 1 file) |
| `page_side` | 15 | Page | — | `pdfdrill/commands.py` |
| `page_side_confidence` | 15 | Page | — | `pdfdrill/commands.py` |
| `svg_error` | 10 | Table | — | `docops/projectors/formula_report.py`, `pdfdrill/commands.py` |
| `svg` | 9 | Diagram, Table | — | `docops/projectors/distill_reader.py`, `docops/projectors/formula_report.py`, `docops/projectors/tiddlywiki.py` +1 |
| `svg_ratio` | 9 | Diagram, Table | — | `pdfdrill/commands.py` |
| `spoken_suspect` | 1 | Formula | — | `pdfdrill/commands.py` |

## Object types

| type | objects | props |
|---|---:|---:|
| `TableCell` | 743,994 | 4 |
| `Formula` | 523,358 | 20 |
| `Paragraph` | 329,776 | 16 |
| `TableRow` | 155,015 | 4 |
| `Equation` | 120,006 | 32 |
| `Page` | 72,722 | 10 |
| `ListItem` | 53,285 | 13 |
| `Citation` | 50,202 | 10 |
| `Diagram` | 25,286 | 22 |
| `Picture` | 17,343 | 13 |
| `Sidenote` | 15,872 | 9 |
| `Section` | 15,846 | 21 |
| `Reference` | 14,987 | 12 |
| `Table` | 11,980 | 23 |
| `Footnote` | 7,239 | 12 |
| `LtxCommand` | 3,430 | 4 |
| `Theorem` | 1,458 | 12 |
| `Document` | 1,346 | 5 |
| `Abstract` | 1,049 | 8 |
| `AlgorithmStep` | 611 | 6 |
| `Proof` | 431 | 7 |
| `Link` | 254 | 7 |
| `Toc` | 154 | 6 |
| `MathTail` | 51 | 7 |
| `Algorithm` | 48 | 7 |
| `List` | 21 | 3 |
