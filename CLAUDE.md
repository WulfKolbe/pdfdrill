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
the accessibility requirement for the Claude.ai web chatbot).

**Install / dependencies.** `pyproject.toml` declares the package (entry point
`pdfdrill = pdfdrill.cli:main`; packages found under `src/`); `pip install -e .`
puts the `pdfdrill` console script on PATH. Core deps are `pdfplumber>=0.11`
and `pydantic>=2.0` (also in `requirements.txt`); the **system** prerequisite
is `poppler-utils` (not pip-installable). `pydantic` is imported at top level
in `context.py`, so the `md`/`drill`/`page` engine path fails without it even
though the docmodel/docops offline path doesn't need it — keep it declared.
Optional `[pix2tex]` extra pulls Pillow+pix2tex (PyTorch; off the live path).

Packages live under `src/`, so the import root is `src`:

```bash
# convenience wrapper (sets PYTHONPATH=src for you)
./pdfdrill size  paper.pdf
./pdfdrill urls  paper.pdf

# or explicitly
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
PYTHONPATH=src python3 -m docmodel.main --bib KEY --lines X.lines.json
PYTHONPATH=src python3 -m docops.main   --in KEY.docmodel.json --out-dir ./out
```

### Batch a whole folder offline (no MathPix/Perplexity)

`pdfdrill folder <dir>` builds the full structure for every `<name>.pdf` that
already has a sibling `<name>.lines.json` — running all state levels (model,
geometry, eqnums, lists, algorithms, annotate, bibliography, score) and
loading `<name>.bib` into the References if present. PDFs without a lines.json
are skipped (no upload). Verified on `data/` (2312.11532 → full model incl. 24
author-year cites, 2 algorithms; the 2605 copy lacking a lines.json skipped).

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
- Bullet handling: the PDF's `•` (U+2022) is normalized to `-` by MathPix; the
  `ListProcessor` marker set covers both. `_split_bullets` also splits a line
  on **mid-line strong-bullet glyphs** (`•‣◦▪●○`) so OCR that merges several
  bullets onto one line (no linefeed) still yields separate `ListItem`s.
- **Geometry y-position re-split** (`blocks.resplit_list_items_by_geometry`,
  run by `pdfdrill lists`): when a list item's MathPix region is **taller than
  ~1.5x the page line-spacing** AND its y-band covers ≥2 bulleted `pdf_lines`,
  the OCR merged several visual lines with no linefeed (and no glyph to split
  on) — we rewrite the item to the first visual line and add one `ListItem`
  (provenance `geometry_resplit`) per remaining line, taking text + indent
  from each pdf_line. The **height gate is essential**: without it a normal
  one-line region's band bleeds into the next line via `eps` and duplicates
  it (this produced 18 false splits on 2605 before the gate). With the gate,
  2605 correctly yields **0 re-splits** (it has no genuine merges); verified to
  recover real merges on a synthetic tall-region case. Tests:
  `tests/test_blocks.py`.
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

Equation-number matching (fixed): `EquationProcessor` pairs each `math`/
`equation` line with the `equation_number` line on the **same page whose
region y-center is closest** (greedy nearest-pair, each number used once) — NOT
a ±N stream-index window. MathPix groups all of a page's math lines first and
its equation_number lines separately, so the old window left 12/13 equations
of arXiv 2312.11532 unnumbered when running `pdfdrill model` alone (incl. eq
(9), the per-document likelihood). Now `model` alone numbers all 13 (2605:
239/239 unchanged). This matters because the structural path is offline — a
user without a MathPix key still gets correct equation numbers from an existing
`lines.json`. Tests: `tests/test_eqnum_match.py`.

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

`pdfdrill latexbook <book.tex>` is the one-shot source-only pipeline (no PDF,
no MathPix): build the model from `.tex` (inline `\input`, resolve preamble +
local `.sty` macros, extract sections/equations/TikZ/tables), **auto-render
TikZ + tables to SVG** (`latex→dvisvgm`), and emit the KaTeX formula report
with SVGs embedded — all in one call. `--no-svg` skips rendering; it also
degrades cleanly (clear message) when `latex`/`dvisvgm` are absent. Verified
on the graphbook: 128 sections, 343 equations, 118 macros, **18/18** TikZ/
tables → SVG, one command.

LaTeX-source upper layer (`src/pdfdrill/latex_source.py`, `pdfdrill latex`):

- For arXiv we usually have both the PDF (→ MathPix `lines.json`) and the
  author's LaTeX (e-print `.tgz`). `pdfdrill latex <pdf> [--tex P]` reads the
  `.tex`/`.tgz` (inlining `\input`/`\include`, stripping comments), splits the
  preamble, parses macros (`\newcommand`/`\renewcommand`/`\def`/
  `\DeclareMathOperator`), extracts display equations, and attaches each to the
  closest MathPix `Equation` (normalized-LaTeX similarity ≥0.55) as a
  `provenance="tex"` `latex_candidate` — the **gold** reference vs OCR, a new
  `compare` column. Inspired by the BUN/TS LATW pipeline in `~/MX/LATW`.
- **Two LaTeX forms per element**: `latex_original` (verbatim author code, may
  use preamble macros) and `latex` (preamble-**expanded** via a bounded
  fixpoint, self-contained). Needed because TikZ/operator macros only compile
  after expansion — the basis for the future `latex → DVI → dvisvgm` SVG step
  (TikZ + tables can't render in KaTeX; SVG embeds fine in HTML). The expanded
  + `standalone` preamble is stored on `doc.meta["latex_preamble"]`. Verified
  on arXiv 2312.11532: 47 macros, 13/16 source equations matched; eq (9)
  carries the author's `\label{eq:likelihood}` original+expanded LaTeX.
- `latex`, `pdflatex`, `dvisvgm`, `dvips` are present in this sandbox (only
  `pdf2svg` is missing), so the SVG projector is feasible here next.

Full-page links: in `report` and `compare`, each equation crop `<img>` is
wrapped in an `<a target="_blank">` to the **full page image** it was cropped
from — `docmodel.mathpix.page_url()` strips the region query from the crop URL
(same base image = the whole page). The page link stays a live CDN URL even
under `--embed` (crop inlined, page click-through live). Verified on
2312.11532: 13 crops → 13 page links; eq (9) → its page-3 image.

Self-contained HTML (`--embed`): `compare`, `report`, and `tiddlers` accept
`--embed`, which base64-inlines every MathPix CDN crop at emit time
(`docops.projectors.common.embed_image`, cached, graceful URL fallback). The
output then has no live-CDN dependency — best for the Claude.ai preview, which
may not load remote images. Verified: `report --embed` on 2312.11532 → 13
data-URIs, 0 remaining cdn URLs.

TikZ/table SVG (`src/pdfdrill/svg.py`, `pdfdrill svg`): KaTeX can't render TikZ
pictures or full LaTeX tables, but SVG embeds in HTML. `compile_to_svg` wraps
each `Diagram`/`Table`'s `latex_code` in the document's expanded `standalone`
preamble (`class=report` so book/chapter counters exist) and runs
`latex -interaction=nonstopmode … && dvisvgm -n --exact-bbox …`, with
`TEXINPUTS` pointed at the source folder + its `style/` so a project's local
`\usepackage{mystyle}`/`tkz-*` resolve. `pdfdrill svg <pdf|tex>` attaches the
SVG to each object (`props["svg"]` + a `provenance="dvisvgm"` realization); the
formula report grows a "TikZ & Tables" section embedding the SVG inline.
Degrades gracefully when latex/dvisvgm are absent (`tools_available()`).
Verified on the graphbook: **18/18** graphics rendered (7 TikZ + 11 tables, 0
failures). `array` is excluded from graphics extraction (it's math-mode,
KaTeX-rendered inside its equation — not a standalone table). The `\[…\]`
display-math extractor no longer mis-splits `\\[4pt]` row-spacing in
align/cases. `latex/pdflatex/dvisvgm/dvips` present here (`pdf2svg` missing).
Tests: `tests/test_svg.py`, `tests/test_latexbook.py`.

Still to do: deepen the self-learning loop (auto-tune from accumulated flags);
math-expression / document-structure / citation graphs queried like Pyre/Pysa
over the persisted `model.docmodel.json` (the between-call memory).
