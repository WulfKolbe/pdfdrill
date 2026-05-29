# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**PDFDRILL** is the merge of two predecessor projects into one toolchain whose
purpose is **quality control of PDF→LaTeX OCR**, building toward a
reinforcement / self-learning loop that optimizes the extraction toolchain.

It combines:

1. **`src/pdfdrill/`** — the low-level PDF drill-down toolkit (from *CSPIRY*).
   A flat CLI that returns prose, persists state in a sidecar next to each PDF,
   and wraps the heavy tools (poppler, pdfplumber, pix2tex). This is the entry
   point the Claude.ai web chatbot drives directly, exposed as the `pdfdrill`
   SKILL.
2. **`src/docmodel/`** — the **unified document-object model** (the extended
   *CSPIRZ* `docobject`). A typed `Document` of `DocObject`s with anchor-based
   `Stream`s, `Realization`s across streams, and `Alignment`s between them.
   MathPix `lines.json` is the only known format that lets us compare a LaTeX
   expression against the CDN image MathPix actually rendered — so this model
   is the home of that comparison. Each `Equation`/`Formula` carries `latex`,
   `refnum`, and `cdn_url`.
3. **`src/docops/`** — the operator pipeline over a `Document`: `Mutator`s
   (modify in place) and `Projector`s (emit artifacts — plaintext, LLM-compact
   markdown, TiddlyWiki tiddlers, the comparison table, and the full
   inline+display **formula report** via `pdfdrill report`).

> **Naming:** the unified model package is `docmodel` (renamed from the
> predecessor `docobject`). The on-disk model artifact is still suffixed
> `.docmodel.json`.

## Running

Everything runs in **Python 3** (no Bun/TypeScript on the live path — this was
the accessibility requirement for the Claude.ai web chatbot). Packages live
under `src/`, so the import root is `src`:

```bash
# convenience wrapper (sets PYTHONPATH=src for you)
./pdfdrill size  paper.pdf
./pdfdrill urls  paper.pdf

# or explicitly
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
PYTHONPATH=src python3 -m docmodel.main --bib KEY --lines X.lines.json
PYTHONPATH=src python3 -m docops.main   --in KEY.docmodel.json --out-dir ./out
```

The pdfdrill commands (`size`, `pdfinfo`, `urls`, `dests`, `fonts`,
`fonts_layer`, `images`, `pix2tex`, `abstract`, `toc`, `md`, `page`, `fetch`,
`plan`, `drill`, `status`, `tsv`, `render`) are documented in
`.claude/skills/pdfdrill/SKILL.md`. Each returns prose, not JSON.

### Killer case worth remembering

`pdfdrill links` (~50 ms, pure `pdfinfo -url`) reads the PDF **annotation
layer**, so it surfaces hyperlinks that have **no visible anchor text** and
therefore never appear in any rendered-text stream an LLM reads. On the
NeurIPS submission `2605.12061`, the paper's anonymized source-code release
(`https://anonymous.4open.science/r/Unified-Representation-A9D9/`) is a page-1
link annotation with no visible text — invisible to plain-text extraction and
to MathPix, instant via `links`. Reach for the cheapest sufficient tool:
`links` answers "where is the code?" in ~0.06 s; `urls` re-derives the same
link in ~6 s (it runs pdfplumber over every page to recover anchor text); and
a MathPix/Markdown pass misses annotation-only links entirely. Run the cheap
level 0–1 commands (`size`, `pdfinfo`, `links`, `dests`) before assuming the
rendered text is all there is — and always run against the real PDF, not a
Claude.ai-uploaded Markdown rendering (which drops the annotation layer).

## Tests

```bash
python3 tests/test_basic.py    #  7 tests — docmodel converter
python3 tests/test_docops.py   # 14 tests — docops operators
```

Both are self-contained (they add `src/` to `sys.path`).

## Architecture notes (docmodel)

- **Anchors are opaque identities, not positions.** Inserts/deletes in one
  stream don't invalidate references elsewhere.
- **Source streams are immutable.** Modules *add* objects/realizations/
  alignments; the raw MathPix payload stays recoverable verbatim.
- **Objects are stream-independent.** A `MathExpression` exists once with
  semantic props; its realizations live in whichever streams it surfaces in.
  The `cdn` realization role holds a rendered-image URL with no anchor range.
- Converter modules (`docmodel/modules/`) load from `config.json`
  (`"type": "application/python"`, ordered by `procOrder`). Operators in the
  same config are tagged `"op": "mutator"` / `"op": "projector"`; each loader
  ignores entries it doesn't own.

## Roadmap (decomposed — each phase gets its own spec + plan)

- **Phase 1 — Unified model + capture** *(in progress)*: extend `docmodel`
  with a `Region` type and `provenance`/`score` on `Realization`; add a Python
  `pdfdrill mathpix` command (port of the old `mtestzx.ts` upload/poll/download
  flow, creds from `MATHPIX_APP_ID`/`MATHPIX_APP_KEY` env vars); ingest MathPix
  `lines.json` and pdfdrill's own extraction (pdfplumber chars, detected-math
  LaTeX, pix2tex) as competing provenances region-matched to each equation;
  emit the **three-way comparison HTML table** (LaTeX | KaTeX render | MathPix
  CDN image) as a `docops` projector.
- **Phase 2 — Scoring layer**: per-expression quality metrics turning the
  comparison into numbers (`Realization.score`).
- **Phase 3 — Optimization / self-learning loop**: use Phase-2 scores to tune
  detection heuristics / `latex_map` / OCR-engine choice.

## Credentials

MathPix `app_id`/`app_key` must come from environment variables and must never
be committed. The predecessor `mtestzx.ts` hardcoded them; that file is
git-ignored and is **not** part of this repo.

## Current status

Merged layout + working pdfdrill CLI (verified on `2605.12061`) + passing
suites. The MathPix-only QC path is **end-to-end functional**:

- **`pdfdrill mathpix <pdf>`** — Python port of `mtestzx.ts`, idempotent,
  creds from env or git-ignored `mathpix_creds.py` (`tests/test_mathpix.py`).
- **`pdfdrill model <pdf>`** — builds the unified docmodel `Document` from
  `lines.json` (auto-chains `mathpix`), writes `<pdf>.drill/model.docmodel.json`.
- **`pdfdrill compare <pdf>`** — `ComparisonHtmlProjector` emits
  `<pdf>.drill/compare.html`: per equation, LaTeX | KaTeX render | MathPix CDN
  image (`tests/test_compare.py`). Verified on `2605.12061`: 239 equations.

Test totals: `test_basic` 7, `test_docops` 14, `test_mathpix` 5,
`test_compare` 3.

Competing-provenance OCR for equation crops:

- **`pdfdrill.mathpix_snip`** — small tool over MathPix `POST /v3/text` (Snip).
  Accepts a local image, a `data:` URI, or an image URL (so it can point at a
  self-constructed `cdn.mathpix.com` crop). Returns `latex_styled` / `data[]`
  LaTeX plus per-line `confidence` (a ready-made score signal).
  `python -m pdfdrill.mathpix_snip <image|url>`; tests in `tests/test_snip.py`.
- **`pix2tex` is intentionally NOT used** in the comparison pipeline (PyTorch
  dependency, untested in the claude.ai web sandbox). The other competing
  provenance is the LLM itself, prompted on an equation crop.

The "competing tools" substrate is in place:

- **`docmodel.core.Region`** (MathPix-native rectangle: `top_left_x/y`,
  `width`, `height`, `space`) + **`provenance`/`score`/`region` on
  `Realization`** (round-tripped; unset fields omitted from JSON). See
  `tests/test_model_ext.py`.
- **`pdfdrill snip <pdf> [--limit N] [--force]`** — OCRs each equation's CDN
  crop via MathPix Snip and attaches a `provenance="snip"` `latex_candidate`
  realization (LaTeX + `confidence` → `score`) to the model.
- **`ComparisonHtmlProjector`** now renders one LaTeX+KaTeX column pair per
  competing provenance (MathPix baseline first, then snip/llm), with the
  candidate confidence shown inline. Verified live on `2605.12061`: 12 crops
  snipped (mean confidence 0.90), Snip column present in `compare.html`.

External-reader (LLM / any tool) provenance, network-free:

- **`pdfdrill candidates <pdf> [--provider llm] [--limit N]`** — export a
  manifest (`eq_id`, `refnum`, `page`, `cdn_url`, `mathpix_latex`, empty
  `latex`) for an LLM to fill by looking at each `cdn_url` crop.
- **`pdfdrill ingest <pdf> <json> [--provider P]`** — attach the returned
  `{eq_id, latex}` (manifest or bare list) as `provenance=P` `latex_candidate`
  realizations; `compare` then grows a column for that provenance.
  Tests: `tests/test_candidates.py`.

Cross-level **geometry fusion** substrate (for multi-line block recovery):

- **`pdfdrill geometry <pdf>`** — lifts cheap `pdftotext -tsv` word geometry
  into a `pdf_lines` Stream and fuses it onto `mathpix_lines` by page +
  normalized-y + string match, recorded as `Alignment(kind="geometry")`. Each
  matched line gets a `_geom` dict: normalized margins, baseline y, and
  **indentation relative to the page body-left** + a `sim` trust score.
  `src/pdfdrill/geometry.py`; tests in `tests/test_geometry.py`.
- Layout (indentation, margins, line spacing) is a *different level* than the
  text — block structure (algorithm bodies, itemize/enumerate nesting,
  left/right-aligned equation numbers) is derived from it, not from OCR text.
  `Stream` = a level, `Alignment` = a cross-level fusion edge, `Region` =
  geometry; the persisted `model.docmodel.json` is the complex memory that
  survives between LLM/tool calls.
- Verified on 2605.12061: 2352 pdftotext lines → 3015 MathPix lines carry
  geometry; indentation clusters cleanly into nesting levels (1240 at body
  margin, 483 / 133 / 54 at successive indents).

Block detectors on the substrate (`src/pdfdrill/blocks.py`):

- **`pdfdrill lists <pdf>`** — nests flat `ListItem`s into recursive `List`
  containers. Runs split only on page change, **marker-family change**, or a
  **large** line gap, so checklist items interleaved with answer paragraphs
  stay one list; deeper indent opens a sublist; indent-less items inherit the
  current level. `List` props: `list_type`, `indent_norm`. On 2605.12061:
  163 items → 69 lists (was 99 before the gap-bridging refinement).
- **`pdfdrill algorithms <pdf>`** — MathPix tags algorithm bodies with line
  type `pseudocode` and keeps indentation in `region.top_left_x`, so we group
  per `Algorithm N:` caption and derive an integer `depth` per step
  (if/else/end nesting) — no geometry fusion needed. Adds `Algorithm` +
  `AlgorithmStep` DocObjects. Verified on arXiv 2312.11532: 2 algorithms,
  35 steps, max depth 2, recursive structure recovered.

Link annotations are first-class now:

- **`pdfdrill annotate <pdf>`** (`src/pdfdrill/annotations.py`) — lifts the
  rich `urls` layer into `Link` DocObjects (uri/kind/anchor_text/context + a
  `Region` for the rect, `space="pdf_points"`), using the no-anchor
  Realization pattern. On 2605.12061: 398 Link nodes (7 code/data hosts); the
  page-1 anonymized code URL is now a queryable graph node despite having no
  visible anchor text. Tests: `tests/test_annotations.py`.

**Annotation storage (how a URL is held).** Two layers today:
(1) sidecar — `links` `[{page,url}]` and the richer `urls` layer
`{page,kind,uri,dest_name,dest_page,rect,anchor_text,context}` from
`links_layer.fetch_links`; (2) docmodel — URL-like pointers are a no-anchor
`Realization` (`stream="cdn"`, `props={"url":…}`) plus `props["cdn_url"]` /
`canonical_uri` and a `Region`. Hyperlink **annotations are not yet promoted
into the model** as first-class nodes — a near-term follow-up is a `Link`
DocObject (Region = rect, props = uri/anchor_text/context, Alignment to the
covered text span) feeding the citation/provenance graph.

Phase 2 — scoring (`src/pdfdrill/scoring.py`, `pdfdrill score`):

- Per equation, compares the readings (mathpix vs snip/llm) on a
  *normalized* LaTeX form (light, language-aware canonicalization in the
  comby/loadable-grammar spirit), combines with the snip `confidence`, and
  stores `props["score"]` = {agreement per provenance, mean_agreement,
  snip_confidence, min_signal 0..1, flags}. `compare` shows a score column and
  highlights flagged rows. On 2605.12061: mean agreement 0.992, 9 flagged
  (mostly low snip confidence — surfaced even when LaTeX agrees).
  Tests: `tests/test_scoring.py`.

Cross-reference graph + geometry coverage (done):

- `link_xref_alignments` (in `annotations.py`, run by `pdfdrill annotate`)
  uses a dest-name micro-grammar (`prefix.key`): `cite.<key>` → `Alignment
  (kind="cites")` to the matching Citation object (citation-graph seed);
  any internal link with a `dest_page` → `Alignment(kind="xref")` to that
  Page. 2605.12061: 380 page xrefs (no Citation objects in this model, so 0
  cite edges — mechanism covered by tests). A future ANTLR/comby BibTeX
  grammar fills in the citekey side.
- Geometry fusion now widens coverage: y-tolerance 0.035 + a nearest-line
  fallback (flagged in `_geom["fallback"]`) so every line with a region gets
  layout. 2605.12061 list items: 163/163 carry geometry (was 121/163), which
  lifted list nesting to depth 2.

Phase 3 — closed self-learning loop (done):

- Scoring gained **corroboration**: ≥2 independent readings agreeing ≥0.9 with
  MathPix clears a `low_confidence` flag (consensus outweighs one tool's
  confidence). `normalize_latex` now collapses single-token braces
  (`x^{2}`==`x^2`) so cosmetic differences don't suppress agreement.
- **`pdfdrill escalate <pdf>`** exports only the flagged equations (snapshotting
  their signals) for a second reading; after `ingest`, **`pdfdrill relearn
  <pdf>`** re-scores and reports resolved / improved / still-shaky. The LLM
  (agent or claude.ai web) supplies the readings — no API, no new deps.
- Demonstrated end-to-end on 2605.12061: 9 flagged → escalate → the agent read
  the crops, ingested → **relearn: 7 resolved, 1 still flagged** (the hardest
  multi-line equation, correctly retained). Flagged 9 → 1.
  Tests: `tests/test_escalate.py` + corroboration in `tests/test_scoring.py`.

Equation-number fusion (done):

- **`pdfdrill eqnums <pdf>`** (`src/pdfdrill/eqnums.py`) attaches
  `equation_number` ("(N)") to each display equation — normalizing
  MathPix-supplied numbers and **recovering margin numbers MathPix dropped**
  from the fused `pdf_lines` geometry (right/left-margin numeric token matched
  by page + vertical position; records `Alignment(kind="equation_number")`).
  Auto-chains `model` + `geometry`. 2605.12061: 238 from MathPix, 0 recovered
  (already complete); recovery path covered by `tests/test_eqnums.py`.
- TiddlyWiki: equation tiddlers now emit `equation_number`, a **`FREF`**
  template renders the linked reference, and **in-text "(N)" references in body
  paragraphs are substituted** with `{{<eq>||FREF}}` (TiddlyWiki-mandatory;
  Markdown could opt in for tests). So both the equation and its reference
  transclude: `{{<eq>||FO}} {{<eq>||FREF}}`. 2605.12061: 28 in-text refs
  substituted.

Bibliography (heuristic first cut — `src/pdfdrill/bibliography.py`,
`pdfdrill bibliography`):

- Segments the References section into entries (year/page-range line endings),
  extracts year + author block + a generated `citekey` (surname+year), keeps
  the original text → `Reference` DocObjects. 2605.12061: 57 entries (56 with
  a year); 2312.11532: 18. Tests: `tests/test_bibliography.py`.
- TiddlyWiki emits a bibliographic tiddler per Reference: `kind=reference`,
  fields `citekey/year/author/entry_type`, and **text led by `{{||CIT}}`** (the
  self-reference, so the citekey link shows in front of the entry).
- **Partial** by design: title/journal/volume are NOT separated yet — that
  needs the ANTLR/comby BibTeX grammar, which will enrich `Reference` props
  without changing callers.

Citation↔Reference linking + Markdown refs (done):

- `bibliography.link_citations` adds `cites` edges from in-text `Citation`s to
  their `Reference` — by **reference number** for numeric citations, else by
  exact citekey or surname-prefix (`[Asai]`→`Asai2023`). `pdfdrill
  bibliography` runs it. TiddlyWiki: in-text citations link straight to the
  bibliographic tiddler (by number or citekey; placeholder only when
  unmatched).
- **Numeric citation detection** (`detect_numeric_citations`): scans body text
  for `[N]`, `[N,M]`, `[N–M]` (ranges expanded), keeps only numbers in
  1..#refs (filters intervals like `[0,1]`), and links each to the reference
  with that number. References are numbered from a printed `[N]`/`N.` marker
  or sequentially; the segmenter splits on a numbered-entry start **or** a
  year/page line-ending, so both numbered and author-year bibliographies parse.
- **Author-year citation detection** (`detect_author_year_citations`): scans
  body text for parenthetical `(Author …, YEAR)` groups (split on `;`,
  surnames down to 2 chars like `Wu`), forming `surname+year` citekeys that
  match the reference citekeys → `cites` edges. Verified:
  `(Asai et al., 2023; Wu and Lee, 2024)` → `Asai2023, Wu2024`.
- Both detectors run in `pdfdrill bibliography`; citations are tagged
  `added_by="bibliography"` for clean `--force` re-runs.
- NOTE on the samples: `2312.11532` is author-year text; `2605.12061`'s
  in-text citations live in the **PDF annotation layer** as `cite.<key>` dest
  links (only "(NeurIPS 2026)" is parenthetical in its OCR text), so the
  precise next unlock for `2605` is promoting those `cite.<key>` annotations
  into `Citation`→`Reference` edges (the `annotate`/`link_xref` machinery
  already targets `cite.<key>`; it needs `Citation` nodes keyed by those dests).

Full BibTeX burst: `pdfdrill bibfetch data/2312.11532.pdf` enriched **18/18**
references with full BibTeX + title + citations via Perplexity SONAR.
- Markdown in-text refs: `LLMCompactProjector` gains an opt-in `eq_refs` param
  that rewrites `(N)` → the equation's compact placeholder `[E‹k›]` (off by
  default; for round-trip tests).

BibTeX field enrichment is **LLM-sourced**, not grammar-parsed (printed refs
are truncated):

- **`pdfdrill bibfetch <pdf> [--limit N]`** (`src/pdfdrill/perplexity_client.py`,
  ported from `updateBibentries.ts`) requests a full BibTeX entry per Reference
  from Perplexity SONAR (which searches online for missing fields), parses the
  bibtex block + citations, and stores `bibtex` / `citations` + refined
  `author`/`year`/`title`/`entry_type` on the Reference. Idempotent per ref;
  `--limit` caps API calls. Key from `PERPLEXITY_API_KEY` env / git-ignored
  `perplexity_creds.py`. Verified live on 2312.11532 (2 refs → full
  @inproceedings/@article with online-completed fields + citations).
- TiddlyWiki Reference tiddlers are tagged `reference bibentry`, carry
  `citekey/authors/year/titlefield/entry_type/bibtex/citations`, text led by
  `{{||CIT}}` — compatible with the existing bibentry macros / updateBibentries.

Still to do: deepen the self-learning loop (auto-tune from accumulated flags);
math-expression / document-structure / citation graphs queried like Pyre/Pysa
over the persisted `model.docmodel.json` (the between-call memory).
