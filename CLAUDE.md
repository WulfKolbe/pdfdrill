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
   - **NLP enhancement (`StanzaNlpMutator`)** attaches Stanza per-sentence
     annotations (`tokens`/POS/lemma/deps/`entities`) under `props.nlp` on prose
     objects — Paragraph, Abstract, Section (caption), ListItem (marker folded
     in), Footnote. Pure markup-cleaning + Stanza wrapper live in
     `docops/nlp_stanza.py` (the `stanza_nlp.py` mutator is thin glue). It is an
     **optional, off-by-default** step: Stanza is the `[nlp]` extra
     (`pip install 'pdfdrill[nlp]'` + `stanza.download('en')`), kept out of
     `default_config.json`. Enable via `docops/nlp_config.json`. Distinct from
     `pdfdrill/nodes/stub_nlp.py`, which is the engine-layer regex sentence
     splitter over `DocumentContext` spans, not the docmodel.

> **Naming:** the unified model package is `docmodel` (renamed from the
> predecessor `docobject`). The on-disk model artifact is still suffixed
> `.docmodel.json`.

## The layer tower (L0–L8) — canonical docs in `docs/layers/`

The whole toolchain is one stratified stack: **L0** container/pdfinfo → **L1**
raster → **L2** glyph → **L3** word/line strings → **L4** layout regions
(where splits originate) → **L5** typed DocObjects → **L6** expression syntax
(math/tables/lists) → **L7** semantic graph (G1–G4 grounding sublayers) →
**L8** ontology/theory. Index: `docs/layers/README.md`; the inter-layer
semantics (support γ / abstraction α, the uniform node/support/edge schema,
split recovery, level skipping, metrics): `docs/layers/TOWER.md`.

**Parallel-work contract:** when working on layer N, edit only
`docs/layers/L<N>-*.md` (plus code/tests); cross-layer semantics go to
`TOWER.md`; do NOT duplicate layer documentation into this file — CLAUDE.md
keeps operational instructions only.

## Running

Everything runs in **Python 3** (no Bun/TypeScript on the live path — this was
the accessibility requirement for the Claude.ai web chatbot).

**Install / dependencies.** `pyproject.toml` declares the package (entry point
`pdfdrill = pdfdrill.cli:main`; packages found under `src/`); `pip install -e .`
puts the `pdfdrill` console script on PATH. Core deps are `pdfplumber>=0.11`
and `pydantic>=2.0` (also in `requirements.txt`); the **system** prerequisites
(not pip-installable) are `poppler-utils` (core), `tesseract-ocr` (keyless OCR
route), and the **LaTeX DVI toolchain + dvisvgm** (`latex`/`pdflatex`/`dvips` +
`dvisvgm` with `texlive-pictures`/`texlive-latex-extra`) for the TikZ/table SVG
route. **`bash bootstrap.sh`** installs all of these via `apt-get` (only what's
missing) and then runs the requirement check; **`pdfdrill doctor`** runs that
check anytime — present/missing system tools + Python deps + API keys, plus the
exact `sudo apt-get install …` line to fill any gap. `pydantic` is imported at
top level in `context.py`, so the `md`/`drill`/`page` engine path fails without
it even though the docmodel/docops offline path doesn't need it — keep it
declared. Optional `[pix2tex]` extra pulls Pillow+pix2tex (PyTorch; off the
live path).

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
`plan`, `drill`, `status`, `tsv`, `render`, `nlp`, `ocr`, `vision`,
`embedimages`, `bibsource`, `translate`, `elements`, `rasterize`,
`attachments`, `formfields`, `extractimages`, `tables`, `doctor`) are documented in
`.claude/skills/pdfdrill/SKILL.md`. Each returns prose, not JSON.

## Command-surface single source of truth (`commands.yaml` + skillsync, 2026-06-17)

The ~80 commands used to be described in four hand-maintained, drifting places
(cli.py `HANDLERS` / `--help` / SKILL.md / the external `drillui` TUI). Now a
typed manifest is canonical and everything else is **generated**:
- **`.claude/skills/pdfdrill/commands.yaml`** — the SSOT (80 typed commands;
  per-command `section`/`summary`/`positionals`/`flags`/`network`/`requires`/
  `done_when` + a `help_intro`). `cli.HANDLERS` (now a module-level dict) is the
  ground truth for *which commands exist*; the manifest must match it.
- **`tools/skillsync.py`** — `check` (manifest↔HANDLERS gate) / `render-help`
  (→ `src/pdfdrill/_help_generated.txt`, which `_print_help` prints) /
  `render-skill` (regenerates the tables between `<!--COMMANDS-->` markers, prose
  untouched) / `bundle` (mirror the SKILL folder into `src/pdfdrill/skill/`) /
  `all`. CI `.github/workflows/skill-sync.yml` + `tests/test_skill_sync.py` are
  the drift gate (would have caught the historical `citedrill`/`classify` gap).
- **`pdfdrill skill --emit DIR | --json | --check`** (`skill_cmd.py`, read-only,
  additive) — pdfdrill *contains the SKILL folder completely* (bundled as
  package-data), so in a fresh Claude.ai sandbox it can emit its own SKILL folder
  if `.claude/` is absent. The external `drillui` TUI stays external and consumes
  `pdfdrill skill --json`; it is NOT part of pdfdrill. **Workflow:** edit
  `commands.yaml`, run `python3 tools/skillsync.py all .`, commit.

## Prerequisite state machine (`pdfdrill steps` / `--ensure`, 2026-06-17)

Commands form a dependency chain (analysis cmds need a built `model`;
`bibfetch`/`citedrill` need a `bibliography`). It is now DECLARATIVE: each command
carries `requires:` + `done_when:` in `commands.yaml`, and `src/pdfdrill/
planner.py` resolves, from the current sidecar/artifact state, the ordered
**missing** steps before a target — the machine reacting to a skipped step.
- **`pdfdrill steps <cmd> <pdf>`** shows the chain (what's done, what would run).
- **`pdfdrill <cmd> <pdf> --ensure`** auto-runs the missing prerequisites first,
  then the target (`cli.main` pre-step; handlers are idempotent).
- **Offline-safe by construction:** only `model` (self-bootstraps mathpix-or-OCR
  internally) and `bibliography` (heuristic) are ever auto-inserted; paid/network
  steps (mathpix/bibfetch/vision/translate) are NEVER auto-run — enforced by
  `tests/test_planner.py::test_offline_safe_only`. Verified: `llmtext --ensure`
  on a model-less doc auto-built the model (from lines.json) then ran llmtext.

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

**Scan / OCR-mandatory detection.** `pdfdrill size` determines the text layer
at level 0 via `_probe_text_layer`: a born-digital PDF has extractable text on
page 1 (`pdftotext -l 1`) AND fonts; a scan has neither. Page-1 char count is
the authoritative signal (fonts only corroborate — a stray stamp font on an
image PDF won't flip it to "has text"). `size` sets `text_layer`/`needs_ocr`/
`font_count`/`first_page_chars` and says "NO text layer — scanned, OCR
required" for scans; `cmd_fonts` no longer downgrades that determination.
Verified on `~/Downloads/scans/scan_20260527_204203.pdf` (pdf-lib image, 0
fonts, 0 chars → needs_ocr=True) vs a born-digital paper (32 fonts, 1436
page-1 chars → text_layer=True). Tests: `tests/test_text_layer.py`.

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

## Code listings vs graphics + the `--bibkey` flag

- **Code listings are not graphics.** MathPix wraps source-code listings (e.g.
  Julia ```` ```julia … ``` ````) as `diagram` lines; `DiagramProcessor` now
  detects a fenced-code body (`_extract_code`) and reclassifies it as
  `subtype="code"` with `code`/`language` set and `latex_code`/`cdn_url`
  cleared — so `svg` never feeds it to latex→dvisvgm. `svg.is_latex_graphic`
  hard-guards `compile_to_svg` (skips empty / markdown-fenced / non-graphic
  bodies — only known graphic envs `tikzpicture|tikzcd|tabular|…` or `\tikz`/
  `\draw`-family commands compile), and `cmd_svg` reports *skipped (not a
  graphic)* separately from genuine *failures*. Every projector renders a
  code-diagram as a code block — never an image: tiddlywiki standalone +
  **section-body** transclusion (plain `{{id}}`, not `||DIA`), formula-report
  (`<pre><code>`), plaintext (`[CODE …]`), llm_compact (fenced block). Tests:
  `tests/test_codelisting_bibkey.py`.
- **`--bibkey` on `model`/`tiddlers`.** `pdfdrill model <pdf> --bibkey KEY` (and
  `tiddlers … --bibkey KEY`) set the tiddler-prefix / object namespace / title /
  landing tiddler / artifact filename. The key is persisted in the sidecar AND
  `doc.meta["bibkey"]`, so `report`/`compare`/etc. reuse it without re-passing
  the flag (a `tiddlers --bibkey` override is written back to the model meta
  durably). Precedence: explicit `--bibkey` > sidecar > model meta > filename
  stem. A clean arXiv id (`2004.05631v1`) is preserved as-is; a junky stem
  (`993787212-…`) prints a `--bibkey` tip. Verified on the AKolbe BA thesis:
  `--bibkey kolbe2018hubbard` → titles `kolbe2018hubbard_EQ0001`…, the 6 Julia
  listings render as code (not 6 failed SVGs).

## Multi-document scan triage (`continuity` / `entities` / `segment`)

For a scanned bundle that is several shuffled German documents (the LLM-usability
test on `ocrtest.pdf`), three commands let an LLM solve it from prose alone, with
**zero external tools**:

- **`pdfdrill continuity <pdf>`** (`continuity.py`) — full-page OCR including the
  MARGINS (where MathPix's content crop drops "Seite N von M" / "Fortsetzung
  Seite N" / Druck-/Kontrollnummern), classifying each token by margin position.
  Attaches `seq_in_doc`/`doc_total`/`is_continuation`/`control_no` to each `Page`
  (shown by `status`). Cached in the sidecar. ocrtest: 19/45 pages carry a
  marker incl. margin-only ones MathPix loses (the rest are single-page docs).
- **`pdfdrill entities <pdf>`** (`features/extract_iban|bic|german_address|ids`)
  — per page: IBAN (built-in mod-97 checksum + DE BLZ/Konto + IBAN-local bank
  name), BIC, German postal address, Steuer-/Kassen-/Aktenzeichen. No
  schwifty/stdnum. ocrtest: 16/17 IBANs valid, recipient address + Kassenzeichen
  recovered.
- **`pdfdrill segment <pdf>`** (`segment.py`) — partition into ordered documents:
  group pages by a stable signature (admin id by VALUE, type-agnostic; else
  sender/letterhead), order each group by its continuity number (so duplex/
  shuffle is irrelevant), flag duplicate copies. ocrtest: the three senders
  (Finanzamt / Burkhardt Kundendienst GmbH / Stadt Köln) come out as separate
  page-ordered docs with dups flagged.

Target LLM flow: `continuity` → `segment` → `entities`, answering the triage
task from prose. Tests: `tests/test_continuity.py`, `tests/test_entities.py`,
`tests/test_segment.py`.

## Recto/verso page sides (`pdfdrill pageside` — book left/right annotation)

Column indices in OCR output are LAYOUT positions, not semantic roles: on a
book with marginal side notes, **verso (left) page: col 0 = side notes / col 1
= body; recto (right): col 0 = body / col 1 = side notes** — so footnote/
side-note search needs the page side first. `src/pdfdrill/rectoverso.py`
(vendored from the user's prototype, extended) fuses three per-page signals by
confidence-weighted vote — printed page-number PARITY (odd=recto; roman
front-matter numerals parsed too), page-number X POSITION (numbers sit on the
OUTER edge), narrow-side-note-COLUMN asymmetry — plus the **sequence-
alternation post-pass** (book pages alternate; the best-supported phase fills
abstaining pages and overrules isolated weak contradictions, visibly:
`signals["alternation"]`, original kept as `before_alternation`). **Abstains
honestly without anchors** — a slide deck gets 21×unknown, never invented
sides. `pdfdrill pageside <pdf>` classifies from the lines.json and attaches
`page_side`/`page_side_confidence` to each model `Page` (continuity pattern).
Verified: the 2004.05631 thesis → 135/135 pages sided, strictly alternating,
mean conf 0.80 (115 position / 56 parity / 62 column votes, 19
alternation-filled). A sibling FRONT/BACK annotation for scanned duplex is
planned on the same fusion shape. Tests: `tests/test_rectoverso.py` (10).

## PDF-reading parity (`rasterize`/`attachments`/`formfields`/`extractimages`/`tables`)

Parity with the Claude.ai **`pdf-reading` skill** (its `SKILL.md` lives in the
TiddlyWiki export `~/MX/claudestatic/wiki-static.html#skill/pdf-reading`), but
**file-based**: every result lands in the sidecar (page images, extracted
attachments/images, form-field + table JSON), not in an LLM context window.
Pure helpers + tool wrappers live in `src/pdfdrill/pdf_reading.py`; each
degrades gracefully (clear message, no raise) when its tool/lib is absent.

The skill's tools were *already* covered by PDFDRILL for inventory (`pdfinfo`/
`size`), fonts (`fonts`/`fonts_layer`), text (`page` uses `pdftotext -layout`),
image **metadata** (`images`/`embedimages`), and scan→OCR (`size`→`ocr`). These
five commands close the remaining gaps:

- **`pdfdrill rasterize <pdf> [--pages N|N-M|all] [--dpi 150] [--fmt png|jpeg]`**
  — the skill's core **visual-inspection** op (`pdftoppm`): render page(s) to
  images in the sidecar (`rasterize/`) and return their paths so the driving LLM
  **Reads the image** (text extraction is blind to charts/equations/multi-column
  layout/forms). ~1,600 tokens per 150-DPI page — rasterize only what matters.
  (Distinct from `render`, which is pandoc→PDF.)
- **`pdfdrill attachments <pdf> [--extract]`** — embedded **file attachments**
  (`pdfdetach -list`, pypdf document-level fallback): spreadsheets/data files in
  reports/portfolios/PDF-A-3, invisible to text & MathPix (same spirit as the
  annotation-only-link "killer case"). `--extract` → `attachments/`.
- **`pdfdrill formfields <pdf>`** — interactive **AcroForm** field values (pypdf
  `get_fields`): name/value/type/options for text/checkbox/radio/dropdown.
  Relevant to German Formulare/government docs. Flat/scanned forms have no
  fields → `rasterize` and read visually.
- **`pdfdrill extractimages <pdf> [--pages N-M] [--all-formats]`** — extract
  embedded raster image **bytes** to files (`pdfimages -png`/`-all`); tiny/empty
  images (masks/decorative) filtered by size (≥1 KB). Vector charts are page
  operators, not image objects — they won't appear (`rasterize` for those).
  Complements `images`/`embedimages` (metadata only).
- **`pdfdrill tables <pdf> [--pages N-M]`** — **keyless offline** table
  extraction (pdfplumber, **span-aware** via `find_tables`) → `tables.json` +
  `tables.md` + **`tables.html`** (the QA projection); the no-MathPix/no-vision
  table path. See the span-aware table section below.

## Span-aware table cells (`table_structure.py` — a value covers a RANGE)

A table is NOT a naive matrix: a header like `BiomedicalDatasets` lives once in
its top-left (anchor) slot and **covers a range of columns**; a row-group label
(`Classical`) covers a range of rows. The naive matrix stored the value in the
leftmost cell with `''` placeholders in the covered slots — losing the layout
structure that carries meaning. Spec:
`docs/superpowers/specs/2026-06-10-span-aware-tables-design.md`.

- **The cell shape** (`src/pdfdrill/table_structure.py`, pure):
  `{"row","col","row_span","col_span","text","region"?}` — covered slots are
  NOT stored (HTML's table model). Stored on the `Table` DocObject as
  `props["cells"]` + `n_rows`/`n_cols`/`columns`/`header_rows`; same keys per
  entry in `tables.json`. **`columns`** = one clean, linefeed-free name per
  column (stacked header cells joined top→bottom, a rowspan'd cell once,
  `xxx-\nyyy`→`xxx-yyy`) so a column is **findable by name** later — e.g.
  `columns.index("SciAD MaF1")`. Header rows = row 0 through the first all-leaf
  row after the span-bearing rows.
- **Both sources fill the same shape:** MathPix cells already carry
  `cell_row`/`cell_column`/`cell_row_span`/`cell_col_span` — `TableProcessor`
  now keeps them (and `_CELL_TYPES` includes **`table_spanning_cell`**, which
  was missing — every spanning cell, the structurally most important ones, used
  to be silently dropped). The keyless pdfplumber route reconstructs spans from
  `find_tables()` cell rects (a rect covering k grid columns ⇒ `col_span=k`).
- **QA projection:** `pdfdrill tables` writes **`tables.html`** — one real
  `<table>` per table, spans rendered natively (`rowspan`/`colspan`), header
  rows as `<th>` with the flattened column name as tooltip, caption = page +
  dims + spanning-cell count + `check()` overlap/overflow warnings.
  `tables.md`/`rows` keep the naive-grid shape for compatibility (`grid()`).
- **Two-strategy extraction with quality gates** (found by QA on the
  2410.21169v5 survey, whose tables.html was 15 empty grids): the lattice
  (`lines`) pass **drops grids with <2 filled cells** (`table_has_text`) —
  they're figure frames (nested boxes in architecture diagrams), reported as
  a "skipped N empty lattice grid(s)" note, never silently. On a page with a
  **table caption** but no usable lattice table (booktabs tables have no
  vertical rules), the **`text` strategy** is tried, accepted only via
  `plausible_text_table` (≥3×3, ≥40% filled) so prose never becomes a 70×1
  "table". Caption regex tolerates pdfplumber's space-collapsing
  (`Table2.`/`Tabelle 3:`). Each entry records its `strategy`. On
  2410.21169v5: 15 artifacts skipped, Table 2 (p23, 64×9 `Model|Data|Param|
  Overall↑…`) recovered via text fallback; Table 1 (p5, caption + prose page)
  is honestly absent — its text-strategy read fails the plausibility gate
  (rasterize for those).
- Verified on `~/Downloads/p2530-pereira.pdf` (3 multi-level benchmark tables):
  `BiomedicalDatasets–Avg.` colspan 6, corner header rowspan 3, `Classical`
  rowspan 6, columns like `"BiomedicalDatasets–Avg. Acronym F1"`; ocrtest
  re-model keeps **67 spanning cells** (was 0). Honest caveat: on a scanned
  FORM (not a data table) nearly every row spans, so header detection runs deep
  and column names degrade — visible in tables.html, which is what QA is for.
  Tests: `tests/test_table_structure.py` (producers, headers, html, grid,
  check, TableProcessor wiring) + `tests/test_pdf_reading.py`
  (`\multicolumn`/`\multirow` pdflatex fixture round-trip, tables_to_html).

`pypdf>=4.0` is now a core dep (form fields + attachment fallback). Verified
end-to-end on built fixtures: rasterize → page-1.png; a bordered tabular → a
3×3 markdown table; a hyperref `\TextField`/`\CheckBox` AcroForm → 3 fields
(`city='Köln'`, `paid=/Yes` options `[/Yes,/Off]`); a `pdfattach`-embedded CSV →
listed + extracted; a real-content image → `img-000.png` (a solid-colour logo
correctly filtered as sub-1KB). Tests: `tests/test_pdf_reading.py` (pure page-
spec/pdfdetach/markdown helpers + graceful no-form/no-table + pypdf-built-PDF
rasterize/attachments round-trips).

## Ordered-stack segmentation (`pdfdrill ordered` — gap scoring + tracking codes)

For a straight scan whose page order is preserved (NAPS2 etc.), segment by
scoring each adjacent-page GAP. `src/pdfdrill/continuity_scorer.py` (vendored
from a reviewed prototype) fuses weighted, **abstaining** signals — page-number
reset, embedding/BoW dissimilarity, entity (sender/doc#/date) change,
header/footer distance, letterhead — and cuts where the boundary score crosses
`--threshold`. Complements (does NOT replace) `pdfdrill segment`, which groups a
SHUFFLED bundle by signature value.

- **Two-level via Deutsche Post DataMatrix tracking codes.** `qrscan` decodes the
  franking codes; pages sharing a trailing **batch id** (`same_mailing`, longest
  common suffix ≥12) form a HARD outer **mailing** (one envelope); the soft
  scorer refines letter-vs-enclosure INSIDE it. A different batch on an adjacent
  page is a hard boundary.
- **Commercial provenance → BibTeX.** A commercial document is a sender↔receiver
  contract: the **sender is the publisher** (its employees are the authors), and
  the **receiver is a NEW explicit field** (the audience a journal name leaves
  implicit). `to_bibtex` projects each document to a BibTeX-like record with
  `publisher`/`institution` = sender and a non-standard `receiver` field;
  it round-trips back into the document.
- **`pdfdrill ordered <pdf> [--threshold 0.5]`** builds `PageFeatures` from
  per-PHYSICAL-page tesseract OCR (full German page text; drops blank duplex
  backsides) + `sender_of` (bank names rejected — the GiroCode creditor supplies
  the issuer) + `detect_recipient` + the QR/tracking codes, runs the scorer, and
  emits documents + mailings + per-gap **explainability** (why each cut/keep, for
  the LLM).
- **`pdfdrill autosegment <pdf>` — the auto-selector.** `detect_acquisition_mode`
  decides ORDERED vs SHUFFLED from per-page signatures (admin-id value else
  sender) in physical order: each document a CONTIGUOUS run → ordered; a
  signature that recurs after a different one interleaves between its occurrences
  → shuffled. It then routes — ordered → `_run_ordered` (gap scorer), shuffled →
  `cmd_segment` (signature grouping) — and reports the decision + interleave
  fraction. Verified: AOK → ordered (interleave 0.0); the scattered three-sender
  ocrtest shape → shuffled.
- **Two fixes over the prototype** (both TDD'd): #1 a LEADING separator's QR
  payload now names the first document; #3 a bare `N/M` is read as a page number
  only in header/footer bands, never from body prose (`1/2 Tasse` is not a page).
- Verified on the real AOK duplex scan: blanks 1/3/5 dropped → mailing `M1=[2,4,6]`
  (tracking codes), doc `[2,4]` = Mahnung (publisher **AOK Rheinland/Hamburg**,
  from the GiroCode), doc `[6]` = the Auflistung statement — your two-level model,
  reproduced. **Honest caveat:** feeding the scorer the MathPix *logical* model
  instead of per-physical-page OCR over-segments (fragmented page text collapses
  BoW cosine); the per-page-OCR path is the correct input. Tests:
  `tests/test_continuity_scorer.py`.

## Visual font id for scanned input (`pdfdrill fontid` — torch-free ONNX)

A scanned PDF has no font layer, so `fonts`/`fonts_layer` (pdffonts) return
nothing. `pdfdrill fontid` recovers a font *visually*: render OCR text-line crops
and classify them with the storia/font-classify ONNX model, **torch-free** —
onnxruntime + numpy + cv2 + PIL + yaml only (NO torch/timm/huggingface_hub; the
three preprocessing ops are reimplemented pure numpy/cv2 in
`src/pdfdrill/font_classify.py`). The ~61 MB model + config are fetched on demand
to `$FONT_CLASSIFY_DIR`/`~/.cache/pdfdrill` via `net.urlopen` (graceful when
blocked). Votes across crops; reports the dominant font + agreement + mean
confidence.

**Font is a property of each text FIELD, not one document vote.** A heading, body,
and fine-print are different faces — collapsing the page to a single "dominant"
font is the wrong model. `cmd_fontid` classifies WORD crops and votes **within
each OCR block** (`font_classify.field_fonts` groups `(page, block)` and aggregates
per group), emitting one font per field with its own vote-share / confidence /
bbox / text sample, plus a distinct-fonts summary. Evidence shape:
`{"fields":[…], "distinct":{font:count}, "categories":{cat:count}}`. Demonstrated
on a two-font page (mono heading + sans body): the heading and body come back as
**separate fields with separate fonts**, each carrying its own confidence. Pages
are capped to the first 3 when none are requested and clamped to the real page
count (so a 175-page scan isn't fully rasterized, and pdftoppm is never asked for
a non-existent page).

**CATEGORY is the robust signal; the exact face is a low-confidence hint.** On an
out-of-class scanned face (Arial/Helvetica/Computer-Modern aren't Google-Fonts
classes) the exact-face vote is noise — but the model's scattered guesses are all
the SAME category. So each field also carries a `category` (sans-serif / serif /
monospace / handwriting / display) voted from each word's top-1-font category, and
`cmd_fontid` LEADS with it (`field≈sans-serif (4/4); face≈Varta (conf 0.58)`) plus
a document verdict (`predominantly sans-serif (5/5 fields)`). `font_classify.
category_of(name)` reads the bundled `font_categories.json` (3473 classes → 90%
resolved: 81% from the google/fonts tag CSV's `/Sans /Serif /Slab /Monospace
/Script` facets, the rest by base-family token + name keyword; built once offline
by `tools/build_font_categories.py`, committed so runtime needs no network).
**This is the fix that makes fontid useful on scanned standard-font mail:** the
real allocr.pdf energy invoice went from "5 random wrong Google-Fonts names" to
"**predominantly sans-serif, 5/5 fields, 3/3–4/4 category agreement**" — TRUE and
useful, while the face stays an honest low-confidence guess. Honest caveat: the
category is only as good as the model's top-1 (a face the model mis-sees — e.g. a
FiraCode heading read as a geometric sans at 0.92 — carries that error into the
category). Tests: `tests/test_font_classify.py` (`category_of`, robust field-
category vote where exact-face agreement is 1/3).

**WORD-level crops (why per-word, not per-line).** A word's ~5:1 aspect fills the
model's square ResizeWithPad box; a full LINE's ~20:1 strip gets shrunk to a thin
band and degrades discrimination. `cmd_fontid` classifies tesseract word boxes
(≥5 alpha chars, ≥40 px wide). Word crops took a page rendered in
Roboto-MediumItalic from **wrong** (line crops → `Sarabun-SemiBoldItalic`,
75%/0.75) to **right** (word crops → `Roboto-MediumItalic`, 14/14 = 100%, conf
0.932) — matching the direct-render accuracy.

**HONEST verdict (verified):** on clean / in-class renders the classifier works —
**62% exact top-1, 85% top-3** across 39 Latin in-class system fonts, **0.9–0.99
on distinctive faces**, and the full word-crop pipeline reproduces that (Roboto
page → 100%/0.93). The 3473 classes are **Google-Fonts only** (Arial/Helvetica =
no clean class; Computer/Latin Modern absent → Tinos/STIX neighbour), so a
**scanned standard-font** doc (AOK: noisy scan + Arial-not-a-class) still classes
poorly and **self-flags** (16% agreement / 0.25 conf, ⚠ LOW-confidence). So:
trustworthy for Google-Fonts/designed PDFs, a flagged weak hint on scanned
standard mail — and it never claims a low-confidence guess as fact. Optional
`[fontid]` extra (onnxruntime + opencv + pyyaml); ~61 MB model fetched on demand.
Tests: `tests/test_font_classify.py`.

## Spellcheck / de-hyphenation QC (`pdfdrill spellqc`, on-demand hunspell)

Repair line-break hyphenation in the transcluded paragraph text: a `left-/right`
wrap is an ARTIFACT iff the *joined* word is real (`Versiche-/rung`→`Versicherung`),
a real COMPOUND iff the *hyphenated* form is (`well-/known`), else REVIEW (neither
is a word — an OCR fragment to fix). `src/pdfdrill/spellqc.py` decides with
hunspell, loaded **on demand for the document language** (auto-detected via the
`extract_language` feature).

- **Multi-backend, sandbox-aware:** spylls (pure-Python Hunspell — reads .aff/.dic,
  no C build/binding; best for affix-compounding languages) → enchant (pyenchant
  → libhunspell; used where it has the language, e.g. en_US here) → a pure-Python
  **.dic word-set floor** (no deps, works offline). Dictionaries are discovered on
  disk (`/usr/share/hunspell`, texstudio, flatpak, a repo `dicts/`,
  `$HUNSPELL_DICT_DIR`). When the dict is weak/absent, `classify` falls back to the
  proven soft-break heuristic — so German (whose productive compounding means many
  valid joined words aren't in the stem list) still de-hyphenates correctly: a
  strong affix-aware dict makes "neither valid" a genuine `review`; a weak/absent
  one leans `join`. (Distinct from `pyphen`, which computes where hyphens MAY go.)
- **`pdfdrill spellqc <pdf> [--lang de|en]`** runs the QC over the model's
  paragraph text and reports join/keep/**REVIEW** counts + the review fragments.
  Verified: AOK (MathPix, already de-hyphenated) → none; an English paper →
  `Expan-sion`/`architec-ture`/`dif-ference`→joined (enchant-confirmed); German
  `Versiche-/rung`→`Versicherung` (heuristic, dic-set missed the affixed form),
  `Bei-/trag`→`Beitrag` (dic-confirmed). Optional `[spell]` extra (pyenchant +
  spylls). Tests: `tests/test_spellqc.py`.

## QR / barcode confirmation (`pdfdrill qr`, integrated into `semantic`)

Codes carry data the text layer can't: a **GiroCode/EPC** payment QR encodes the
creditor name, IBAN, amount and payment reference; **Data Matrix** franking marks
carry page-incrementing routing numbers (a continuity signal). `src/pdfdrill/
qrscan.py` rasterizes with the existing pdftoppm (no PyMuPDF needed) and decodes
with **zxing-cpp** (`[qr]` extra), degrading cleanly when absent. `parse_epc`
turns a `BCD…` QR into structured SEPA fields; `_result_to_dict` is binary-safe
(base64 for non-text codes).

- **`pdfdrill qr <pdf> [--pages N-M] [--dpi 300] [--formats QRCode,DataMatrix]`**
  — reports every code (format / content / page / EPC fields) into the sidecar
  (`qr_codes`).
- **Integrated into `pdfdrill semantic`**: QR/barcodes become confirmation
  markers, and a GiroCode supplies the **issuer the OCR text omits** — it
  resolves the creditor as an `Organization`, links `Document issued_by` it and
  `BankAccount belongs_to` it, and attaches `qr_creditor`/`qr_iban`/`qr_amount`/
  `qr_reference` as 0.95-confidence evidence. Verified on the AOK dunning letter:
  the issuer **AOK Rheinland/Hamburg** (missed by `sender_of`) is recovered from
  the GiroCode, the IBAN `DE24…` confirmed, the Versichertennummer `D990775288`
  captured. Tests: `tests/test_qrscan.py` (EPC parser + binary-safe normalize).

## Layout-element layer (`pdfdrill elements` — GNN over word boxes, additive)

The layout analogue of the MathPix→LaTeX layer: just as MathPix isolates each
equation as a LaTeX expression, a **geometric-attention GNN** isolates each
structured **layout element** (postal **address**, **BOM line item**) from the
page's word geometry, gives it a **content-addressed identity** (blake3, or
sha256 fallback), and emits it as a TiddlyWiki tiddler (`<bibkey>_AD/BM_<serial>`)
with data fields, a normalised **`geo-projection`**, and a learned 48-dim
**`projection`** embedding (for tw2graph / pgvector). Purely additive — it never
touches the docmodel/docops pipeline; the result is dropped into the sidecar as
a **`layout` layer** + a sibling `<bibkey>.elements.tiddlers.json`.

- **`src/pdfdrill/tsv_gcn.py`** — the vendored, self-contained **pure-NumPy**
  model (no PyTorch): per-word features (`FEAT_DIM`) + `EDGE_DIM=12` *relative*
  edge features (dx/dy/|dx|/|dy|/distance/same-line/is-right/is-below/is-self/
  h-v overlap/bias); a learned vector scores edges and a **per-target softmax**
  turns scores into attention, so three identically-formatted numbers separate
  into qty / unit-price / line-total *by column*. `gradcheck` validates the
  backward pass (≤1e-5) before any training is trusted. Its own CLI trains and
  runs the model: `python -m pdfdrill.tsv_gcn {gradcheck,synth,label,train,
  predict,crosscheck,tiddlers}`. Two public entry points drive everything:
  `crosscheck(tsv_path, model_path)` → reconciled addresses (GNN ∩ optional
  `extract_addresses` heuristic, tagged `gnn+heuristic`/`gnn-only`/
  `heuristic-only`) and `emit_tiddlers(tsv_path, model_path, bibkey, source)` →
  the tiddler array.
- **`src/pdfdrill/layout_elements.py`** — the thin glue: renders the pages
  (`pdftoppm`) and OCRs each to a single **combined TSV with page numbers
  patched to the real page** (reusing the `ocr`/`geometry` tesseract plumbing),
  then calls `crosscheck`/`emit_tiddlers`. Degrades cleanly on every missing
  piece: NumPy absent, OCR tools absent, or **no trained model AND no
  `extract_addresses`** → a clear, actionable message (how to train a model)
  rather than a raise.
- **`src/pdfdrill/extract_addresses.py`** — the vendored **heuristic** address
  finder (the author's sibling module `tsv_gcn` cross-checks against). `tsv_gcn`
  imports only its three **pure-stdlib** symbols — `DEFAULT_POSTCODE` (a German
  PLZ anchor: 5 digits *followed by a city letter*, so it never fires on
  invoice/HRB numbers), `read_tsv` (tesseract TSV → block/line `Segment`s), and
  `find_candidates` (walk upward from each PLZ anchor collecting the address
  block by geometry). libpostal isn't needed to *find* a candidate (the PLZ
  anchor does that), so `_HAVE_EA=True` out of the box and the address path runs
  with **no model and no libpostal**. libpostal (pypostal/`postal`, a CRF parser
  trained on ~1B OSM/OpenAddresses records, built from source into
  `/usr/local/lib` + data in `~/libpostal`) is the *component-parsing* upgrade,
  wired as an enrichment step (next bullet) and used by `extract_addresses`' own
  CLI. **It IS installed in this environment** — verified loading + parsing real
  components.
- **libpostal loader fix (important).** A from-source `make install` leaves
  `libpostal.so` in `/usr/local/lib`, which is **not** on the default linker
  cache unless `ldconfig` ran — so `import postal.parser` fails with
  `libpostal.so.1: cannot open shared object file` even though everything is
  installed. Both `layout_elements._preload_libpostal` and
  `extract_addresses._preload_libpostal_lib` **`ctypes.CDLL(..., RTLD_GLOBAL)`**
  the `.so` (searching `/usr/local/lib`, `/usr/lib`, …) before importing the
  binding, so the real parser loads with **no root, no `ldconfig`, no
  `LD_LIBRARY_PATH`**. `pdfdrill doctor` reports `[OK] libpostal` by actually
  attempting the load (not a bare `find_spec`). Verified: `parse_address`
  returns `house=firma müller gmbh / road=hauptstraße / house_number=42a /
  postcode=50667 / city=köln`.
- **`pdfdrill elements <pdf> [--model M.npz] [--bibkey K] [--source S]
  [--lang deu+eng] [--ppi 300] [--force]`** — writes the `layout` sidecar layer
  (`layout_counts`, per-element title/kind/page/hash/bbox) + the tiddlers file,
  returns prose. **Two routes:** with `--model` the GNN emits addresses *and*
  BOM-line items, each carrying a learned `projection` embedding, and addresses
  are reconciled against the heuristic (tagged gnn+heuristic/gnn-only/
  heuristic-only); **without a model** the vendored `extract_addresses` heuristic
  still finds **addresses** (provenance `heuristic-only`, content hash + bbox, no
  embedding). When **libpostal** (pypostal `postal`) is installed it is
  **auto-used** to parse each heuristic block into clean `road`/`house_number`/
  `postcode`/`city` components (`parsed_by="libpostal"`); it degrades silently to
  the raw block text when absent (`layout_elements._enrich_with_libpostal`).
  **BOM-line items are GNN-only** (no heuristic equivalent) — they need a
  `--model`.
- **Optional `[layout]` extra** (`pip install 'pdfdrill[layout]'`): numpy
  (required, for the GNN) + blake3 (optional — `content_hash` falls back to
  sha256 without it). The heuristic address path is pure-stdlib (no extra
  needed). A trained `.npz` GNN model is **not** shipped — train one with
  `python -m pdfdrill.tsv_gcn synth <dir> -n 24 && python -m pdfdrill.tsv_gcn
  train <dir>/*.tsv --labels-dir <dir> -o model.npz` (synthetic = smoke-test
  quality) or supply a model trained on real labelled pages.
- **Verified end-to-end** on a generated German invoice PDF (render →
  tesseract): **(a) no model** — `extract_addresses` recovers the address
  (`50667 Köln`, heuristic-only) with zero model/libpostal; **(b) synth-trained
  GNN** — the address `Firma Müller GmbH / Hauptstraße 42a / 50667 Köln` isolated
  with components (road/house-number/postcode/city) + 5 BOM-line tiddlers, each
  content-addressed + carrying projections. **Honest caveat (the module's own):**
  a model trained only on *synthetic* pages over-generalizes on a different real
  layout (mislabelled the table header as a second address, split a couple of
  BOM rows); and the heuristic, keyed on tesseract's unstable *block* number,
  can clip a block-fragmented address to its PLZ line. Element *quality* tracks
  the model/training data; production use wants a model trained on real labelled
  pages. The wiring, content-addressing, dual-route, and graceful degradation are
  what's verified. Tests: `tests/test_elements.py` (page-num patch, vendored
  heuristic, no-model heuristic-only path, model path emits content-addressed
  tiddlers with projections, fully-graceful no-source path).

## Feature-extraction layer (`src/features/`, additive — starter)

A NEW, self-contained package that is **purely additive**: extractors take plain
text (`str`) and emit flat `Feature` objects; it never reads PDF/PNG/MathPix/
Markdown specifics and never modifies the pdfdrill/docmodel/docops pipeline.
Built per the "commercial-document extractors" spec (flat data + relations, no
nested objects, named real libraries, no Stanza/heavy-NLP here).

- **Core:** `features.py` (`Feature{id,page_id,type,value,confidence,start,end}`
  + `Feature.create` for a deterministic id), `relations.py`
  (`Relation{source,target,type,weight}`), `feature_registry.py`
  (`FeatureRegistry.register_feature/find_features`), `graph_builder.py`
  (`build_graph(list[Relation]) -> nx.DiGraph`, networkx).
- **Extractors** (each `extract(text, page_id="") -> list[Feature]`):
  regex/no-dep — `extract_email` (EMAIL), `extract_url` (URL), `extract_doi`
  (DOI); library-backed (lazy import, **degrade to [] when the dep is absent**)
  — `extract_dates` (dateparser→DATE), `extract_phone` (phonenumbers→PHONE),
  `extract_price` (price-parser→PRICE), `extract_names` (probablepeople→
  PERSON_NAME), `extract_address` (usaddress→ADDRESS). `match_entities`
  (rapidfuzz) emits `Relation`s (`SAME_AS`, weight=score/100) for OCR-typo /
  invoice-number / company-name dedup.
- **Convenience:** `features.extract_all(text, page_id)` runs every available
  extractor; `features.available_extractors()` reports dep presence; `python -m
  features <file>` dumps features as JSON.
- **Language detection** (`extract_language`): `detect_language(text)` →
  `{lang (ISO-639-1 or 'und'), confidence, engine}` and `language_of(text)` → the
  code. Multi-engine best-first (lingua → langdetect → langid, each lazy) with a
  pure-Python **stopword fallback** so it ALWAYS works offline (no deps); emits a
  `LANGUAGE` Feature and is in `_ALWAYS` (always available). Optional `[lang]`
  extra (lingua + langdetect) upgrades accuracy on short text. Used implicitly by
  `pdfdrill semantic` (header `lang=de`, sidecar `language`). Tests:
  `tests/test_extract_language.py`.
- **Read-only audits:** `python -m features.audit_deps` (per-module
  imports/defines → JSON dependency graph) and `python -m features.audit_nested`
  (nested container annotations/literals → JSON; report only). Neither edits
  source.
- Optional deps in the `[features]` extra (`pip install 'pdfdrill[features]'`);
  networkx + rapidfuzz are present in this env, the rest install on demand.
  Math-paper extractors (CITATION/EQUATION_REF/THEOREM_REF/ARXIV_ID/MSC/… ,
  regex-only) are a **later** step, deliberately not built yet. Tests:
  `tests/test_features.py`. NOT yet wired into the `pdfdrill` CLI (the next step
  would add a thin `pdfdrill features` command + persist Features alongside the
  model).

## Semantic graph layer (`src/semantic/`, the CSP model — graph-first, in progress)

A NEW, additive package implementing the **semantic-compiler** direction: a
domain-agnostic, evidence-backed, typed **entity/relation graph** where **the
graph is the primary artifact and extractors are sensors that emit evidence**.
The inversion from flat extraction: an address/IBAN/VAT is *evidence pointing at
a Company*, not the primary object — the Company is the entity, and it
**accumulates evidence across documents over time** (so a chunk store can't track
identity, but this can). One model unifies scientific (paper/formula/citation/
concept) and commercial (company/person/invoice/bank-account) documents because
`provenance`/`contains`/`derived_from`/`cites` are domain-agnostic. CSP layers:

- **Entity layer** (`entity.py`): `Entity{id, type (EntityType), subtype,
  evidence[]}`; properties are *derived* from accumulated evidence (best value by
  confidence, ties→recency), never set directly. `EntityType` spans both domains
  (person/company/authority/bank/department, paper/document, formula/image/table/
  citation/concept, bank_account, event).
- **Evidence** (`evidence.py`): the Proof-Layer primitive — `Evidence{source,
  prop, value, produced_by, version, confidence, grounding}`. The atomic
  observation a sensor emits.
- **Relation layer** (`relation.py`): `Relation{subject, predicate
  (RelationType), object, confidence, produced_by, version, grounding}`. Predicate
  vocab = the CSP set (cites/derived_from/explains/contains/contradicts/
  implements) + commercial (owns/sender/receiver/represented_by/acts_for/
  publishes/belongs_to/issued_by/sent_to/has_attachment/references).
- **IdentityResolver** (`identity.py`) — the heart: `find_existing_entity` /
  `create_entity` / `attach_evidence`, composed by `resolve(type, keys, evidence)`
  = find-or-create + attach. Strong keys (iban/vat/bic/email/tax_id/…) are indexed
  when attached, so a later document mentioning only the IBAN resolves to the
  company first seen by name. Soft keys (name/title) match on normalised exact for
  now (fuzzy via rapidfuzz is a later refinement — entities merge only on strong
  evidence).
- **SemanticGraph** (`graph.py`): the primary artifact — entities + relations,
  `relate`/`relations_of`/`relations_to`, JSON `to_dict`/`from_dict` (sidecar +
  cross-document persistence; id counters restored on load).
- **Proof layer** (`proof.py`): `created_by`/`processes`/`versions`/`sources`/
  `evidence_supporting`/`explain` — answers why a node exists, what evidence
  supports it, which process+version produced it.

Built **test-first** (`tests/test_semantic_graph.py`, 9 tests): evidence
provenance, evidence→property derivation, cross-document company unification,
address/IBAN-as-evidence-not-entity, strong-key resolution, typed relations with
provenance, the scientific∧commercial unification proof (one graph, same
primitives), proof-layer queries, JSON round-trip. **Decisions** (per the user):
build in `src/semantic/`; **deterministic-primary** (IR from pdfdrill's validated
extractors); the GPT-4o page pass is an **optional gap-filler**, not the source.

**Phase B (done) — evidence producers + `pdfdrill semantic`.** `build.py`
`ingest_document` turns extractor output into Evidence via the resolver: sender→
Company/Authority (doc `issued_by`), IBAN→BankAccount (`belongs_to` company),
BIC/blz/konto/bank→evidence on the account, Steuer-/Kassen-/Aktenzeichen+address→
evidence on the company (conservative, confidence-labelled; refined by Phase C).
`graph.relate_once`/`has_relation` dedupe edges; `identity.reindex()` resumes
accumulation from a loaded graph. **`pdfdrill semantic <pdf> [--store graph.json]`**
persists `<bibkey>.semantic.json`; `--store` accumulates **across documents** (run
over many PDFs → one Company gathers evidence from all). Verified: ocrtest2 → 1
company + 14 bank accounts; adding the front scan to the same store grew it to 18
entities/2 docs with the second sender resolving into the SAME company. Caveat: on
a multi-document bundle all IBANs attach to the single detected sender
(segment-aware ingestion is future). Tests: `tests/test_semantic_build.py`.

**Phase C (done) — block-role classifier.** `blocks.py` `classify_block(text,
bbox)` → header/footer/body/table/signature/stamp/other; content cues override
position (franking→stamp, HRB/USt-ID/Vorstand→footer, "Herrn …"→body recipient,
"bitte wenden"→other). `is_sender_region`/`is_recipient_region` feed attribution.
TDD against the real Provinzial-letter blocks. Tests: `tests/test_semantic_blocks.py`.

**Phase D (done) — the compiler/validator.** `compiler.py` `compile(graph,
blocks=None) → CompileResult{validity, warnings}`: a relation `SIGNATURE_TABLE`
type-check, grounding verification (cited `evidence_text` must occur in the cited
block — pdfdrill's edge: it HAS the OCR text), dangling-reference + `derived_from`
cycle (DAG) + functional-relation contradiction checks. `pdfdrill semantic` runs
it and reports `compiler: valid/invalid` (+ writes `validity`/`warnings` into the
graph JSON). Catches exactly the LLM-test failure modes (type violations,
over-linking, ungrounded edges). Tests: `tests/test_semantic_compiler.py`.

**Segment-aware ingestion + recipient attribution (done).** `cmd_semantic`
partitions a bundle with `segment.segment({}, per_page_entities, page_text)` (no
slow margin OCR) and ingests each segment as its own Document/sender;
`blocks.detect_recipient` routes the recipient address to the recipient Person
(not the sender), and a `_real_sender` guard drops numeric/id "senders". The
compiler caught a real builder bug here (an account `belongs_to` a Document → type
violation); fixed to `Document contains account` when no Agent owner is known.
ocrtest2: 1 company → 20 segmented docs, 4 named companies + 2 Finanzämter +
recipient Person, compiler valid.

**Unified out-of-column geometry (done — `semantic/geometry_columns.py`).** The
ONE place that reasons about content outside the body column, source-independent
(MathPix AND OCR regions are `{top_left_x,top_left_y,width,height}`).
`body_column(regions)` (from the WIDE body lines), `out_of_column(region, body)`
(non-overlap test, indentation not flagged), `classify_margin_item(text)` →
`MarginRole` (continuity / page_number / control_number / label / marginal),
`tag_out_of_column(lines)`. **Closes two gaps the investigation found:** (1) the
OCR path dropped tesseract's column signal — `ocr_lines` now tags margin lines
(MathPix parity); (2) MathPix `type='column'` lines were flattened into role-less
`Sidenote`s. `cmd_semantic` runs an out-of-column pass over the model's per-line
regions (`_page_lines_from_model`) and attaches **control-key + continuity markers
as geometry CONFIRMATION evidence** on the page's Document (a margin "key" is
confirmation, not a footnote; page numbers are captured distinctly from the
physical OCR index, for TOC reconciliation). Verified on ocrtest2: 89
out-of-column markers (continuity / control_number / page_number / label). Tests:
`tests/test_geometry_columns.py`. Caveat: the margin classifier is heuristic
(phone numbers/times can read as control_number); the geometry *detection* is the
robust part.

**Region-based sender/recipient attribution (done — `semantic/attribution.py`).**
`attribute(lines)` classifies each line by its REGION (`classify_block` on the
line bbox, page-height = lowest line bottom) and splits a page into the sender
side (header/footer/stamp) and the body, pulling the recipient out of the body —
so the recipient's address comes from the recipient REGION and lands on the
recipient Person, not the sender. `classify_block` now judges HEADER by the
block's TOP (letterheads start at the top). `cmd_semantic` builds per-line
geometry (`_page_lines_from_model`), attributes company addresses from the
header/footer region and the recipient from the body; sender = region `sender_of`
→ full-text `sender_of` → segment label (region sharpens, never gates, so a
messy-layout sender isn't lost). `detect_recipient` rejects a PLZ-only "name".
Verified on ocrtest2: the recipient-address-on-company leak is FIXED — company
addresses are now the companies' OWN cities (Magdeburg/Dörth/Nürnberg/Löwenberger
Land), not the recipient's Kürten. Tests: `tests/test_semantic_attribution.py`.

**Next:** (E) the optional GPT-4o page pass validated by the compiler; the
docmodel write-back so existing projectors render the graph; detect individual/
tradesperson senders (not just GmbH/AG/authority); refine the margin classifier.

**Composable graph layers (`src/semantic/layers/` + `fracidx.py`, additive — Phase
1 dropped in, NOT yet wired into ingest).** *(Consolidated data-structure summary
of the 2026-06-09 additions — fracidx, the four layers, the concept record,
Phase-2 ingest, the two projectors — in `docs/DATA-STRUCTURES-2026-06-09.md`.)*
Three capabilities the graph lacked,
each riding inside the existing `Relation.grounding` dict (zero schema change; no
edit to graph/entity/relation/identity/evidence):
- **L1 ordering** (`layers/ordering.py`) — sibling order that survives insertion,
  via a fractional index (`fracidx.py`, a fuzz-tested rocicorp port) in
  `grounding["ord"]`. `append_child`/`insert_child`/`ordered_children`/
  `first_occurrence`. Insert-between adds exactly ONE edge.
- **L2 content identity** (`layers/content_identity.py`) — adds the `content_hash`
  strong key (idempotent `STRONG_KEYS.add` at import) so keyless FORMULA/TABLE/
  FIGURE objects dedup across re-OCR; `resolve_formula` canonicalizes
  (`canonicalize_latex` — the only corpus-specific knob) then routes through the
  existing resolver.
- **L3 occurrences** (`layers/occurrence.py`) — `define`/`add_occurrence` record
  each item's site in BOTH coordinate systems: PDF (`grounding["pdf"]={page,bbox}`)
  and logical (the edge's structural object + `grounding["path"]`), with `role`
  (definition vs reference) and a doc-order `ord`. Carrier predicate `REFERENCES`
  + `grounding["layer"]="occurrence"`.
- **L4 SQLite view** (`layers/sqlite_view.py`) — read-only projection of
  `graph.json` with indexed per-page / per-section queries (the `bun:sqlite`
  TiddlyWiki bridge).
Verified: `tests/test_graph_layers.py` (fracidx fuzz + dedup + insert-between +
dual-position round-trip + SQLite dual-axis).

**Phase 2 — scientific docmodel→graph ingest, wired into `pdfdrill semantic`.**
`build.py` was commercial-only; `ingest_docmodel(graph, resolver, doc, bibkey)`
now maps the docmodel onto the SAME graph through the layers: the chapter/section
`CONTAINS` tree ordered by L1; Equation/Formula→FORMULA, Table→TABLE,
Picture/Diagram→IMAGE(+`image_source` via `DERIVED_FROM`), Reference→CITATION,
all content-hash-deduped (L2); and each item's dual-positioned occurrence (L3) —
PDF `{page,bbox}` from the docmodel `region` + the containing section node +
`path` (section_number); in-text Citations (`cited_reference_id`) become further
occurrences of their Reference. `cmd_semantic` imports `content_identity` BEFORE
`reindex()` (so the `content_hash` strong key is indexed and re-runs dedup, not
double-mint) and the Document root is keyed by doc_id + content_hash. Idempotent:
re-running is `has_relation`-guarded (tree) + occurrence-existence-guarded.
Verified on arXiv 2004.05631 (254 eqs, 63 refs): 1359 FORMULA / 185 IMAGE / 63
CITATION / 57 CONCEPT(section) entities; eq (1.1) → PDF p12 bbox + logical
section node path; most-cited bibentry → 6 occurrences; `items_on_page(12)`→68.
Tests: `tests/test_graph_layers.py::test_ingest_docmodel_idempotent_and_dual_position`.

**Named-concept layer (`src/semantic/concepts.py`) — the sTeX prerequisite.** A
*named concept* is a term introduced once and referred to many times (the LaTeX
`\acro`/`\newacronym`/`\newglossaryentry`/`\index` idea); it maps to the graph's
declaration/use split exactly. Deterministic, no LLM: **acronyms** via the
Schwartz-Hearst long-form/short-form algorithm over prose ("Convolutional Neural
Network (CNN)" → defines CNN; later "CNN" → uses), and **glossary/notation/
nomenclature/abbreviation/symbol-list/index SECTIONS** (each `TERM — definition`
entry). `concept_records(doc)` (pure) returns each concept's `define` site + `[
occurrences ]` located in the docmodel prose (page + containing section);
`ingest_docmodel` turns each into a `CONCEPT` entity (subtype `acronym`/`term`)
deduped by content_hash, with the L3 dual-positioned definition + reference
occurrences — i.e. `\symdecl` + `sdefinition` + `\symref` once the sTeX projector
lands. Verified on arXiv 2510.11170: `LLMs`/`CoT`/`RL`/`KL` extracted with correct
expansions, definition page, and reference counts; idempotent on re-run. Tests:
`tests/test_concepts.py` (Schwartz-Hearst + define-first-then-references + glossary
section).
**LaTeX / sTeX projectors (`src/semantic/stex.py`, `pdfdrill stex`).** The graph's
named-concept layer computed the hard part (one entity per concept + the
definition/reference split), so these *render* it as enriched LaTeX:
- `project_latex(graph)` — a standard compilable document with **all the LaTeX
  lists**: ACRONYMS (`\newacronym`), GLOSSARY (`\newglossaryentry`), TABLE OF
  SYMBOLS (the `symbols` glossary), INDEX (`\index`/`\printindex`) — driven by the
  extracted concepts, each carrying pdfdrill's provenance back-link (PDF pages).
- `project_stex(graph)` — the sTeX form: a `\symdecl` per concept inside an
  `smodule`, an `sdefinition` at the definition site, `\symref` at each reference.
`pdfdrill stex <pdf> [--stex] [--compile]` writes `<bibkey>.glossaries.tex` /
`<bibkey>.stex.tex` and (with `--compile`) runs lualatex (+ makeglossaries +
makeindex). **Compile-proven** with lualatex: the demo + the live EAGer
(2510.11170) projection both build a PDF — the EAGer glossaries PDF shows the
Acronyms list (CoT, LLMs), Index, section structure, and per-concept provenance
lines; the sTeX demo builds via `stex.sty`. Tests: `tests/test_stex.py` (macros +
lualatex compile, gated on tool availability).
**SciKGTeX / ORKG projector (`src/docops/projectors/scikgtex.py`, `pdfdrill
scikgtex`).** A read-only docmodel projector → SciKGTeX-annotated LaTeX whose
compiled PDF carries the paper's contribution metadata as **XMP/RDF in the ORKG
vocabulary** (Christof93/SciKGTeX v3.0.0, LuaLaTeX). Emits `\metatitle*`/
`\metaauthor*`/`\researchfield*` (title/authors from `doc.meta`, enriched from the
sidecar arXiv metadata; field from primary category), the **invisible starred**
contribution roles (v1 heuristic: Abstract → `\researchproblem*` P32; a Method/
Results/Conclusion section → `\method*` P1005 / `\result*` P1006 / `\conclusion*`
P15419 — where unsure, OMIT), `\contribution*{name}{value}` for numeric facts
(accuracy/F1/precision/recall/p-value/n — the package resolves name→ORKG-P-ID
offline via its bundled table), and `\uri{doi}{label}` for Reference DOIs. The
package + `[compatibility]` write the RDF into XMP + a `SciKGMetadata` catalog key.
`pdfdrill scikgtex <pdf> [--compile]` writes `<bibkey>.scikg.tex` and (with
`--compile`, lualatex + the vendored `scikgtex.sty`/`.lua`) the PDF + an
inspectable `xmp_metadata.xml`. **Compile-proven** (synthetic + live EAGer): the
XMP shows `orkg:Paper` (hasTitle/hasAuthor/hasResearchField) + ResearchContributions
with P32/P1005/P1006, `accuracy`→`P18048`, and the DOI as an `rdfs:label`led node.
**Rights/disclaimer in the XMP (2026-06-14).** The projector also embeds a pdfdrill-namespace rights block in the XMP/RDF via SciKGTeX `\newpropertycommand[pdfdrill, http://pdfdrill.org/property/]{name}` + an invisible `\name*{value}` (names must be underscore-free — they become real LaTeX commands): `processedby` (PDFDRILL™), `disclaimer` ("enhanced readability + metadata only; original content not altered"), `liability` ("provided as-is, no liability accepted"), `trademark` ("PDFDRILL is a trademark of Wulf Kolbe, registration pending"). All four are overridable via projector params. Verified in the compiled XMP as `<pdfdrill:disclaimer>`/`<pdfdrill:liability>` etc.
**Subject-classification fold-in (2026-06-16).** When `pdfdrill classify` has run, `cmd_scikgtex` reads the sidecar `classification` and passes the top MSC codes (`code pref`, ≤8) + PhySH concepts (≤6) to the projector as `msc_subjects`/`physh_subjects`; the projector declares two more pdfdrill-namespace properties (`mscsubject`/`physhsubject`) and emits one invisible `\mscsubject*{…}` / `\physhsubject*{…}` per tag, so the compiled PDF's XMP carries the MSC/PhySH subject fingerprint. Verified on cspmath: 8 MSC + 3 PhySH tags in `main.scikg.tex`. Tests: `tests/test_scikgtex.py` (fold-in + no-subjects cases).

`scikgtex.sty`/`.lua` vendored under `tests/fixtures/scikgtex/` (not in the
package). Tests: `tests/test_scikgtex.py` (macros + lualatex compile + XMP RDF
checks, gated). **Out of scope (v2):** an LLM contribution classifier; direct
pikepdf XMP embedding without LaTeX; serializing the occurrence graph into XMP.

**Bundles / observations / gaps (the sheaf-plan items, 2026-06-12).**
`semantic/bundles.py` (per-entity global section, DERIVED — never stored back),
the G4 view's new `observation` + `bundle`/`bundle_member` tables
(`load_view(graph, bundles=…)`; Observation = the existing Evidence row, no new
primitive), and **`pdfdrill gaps <pdf|md>`** (`semantic/gaps.py`) — missing-
information diagnostics: acronym_undefined / symbol_undefined /
claim_unsupported / citation_unmatched (trusts `cited_reference_id` from the
linkers). Producer half: `concepts.undefined_concept_uses`. Verified: thesis →
exactly bibsource's 7 unlinked; yt2tw summary → 4 undeclared greek symbols.
Restriction maps deferred by decision. Details: `docs/layers/L7-semantic-graph.md`.
Tests: `tests/test_semantic_gaps.py`, `tests/test_bundles.py`.

**Kitems + render-policy contract (two-store plan steps 1+2, 2026-06-12).**
`docops/transclusion_render.py` — the stratum contract over canonical
(transcluded) paragraph text: policies `detranscluded` (nl gloss; nlp_stanza
now imports the shared implementation, behavior unchanged) and `typed_gloss`
(`[FORMULA 12]` / `[FORMULA: <caption>]` via a lookup). `semantic/kitems.py` —
knowledge items as ENTITIES (`EntityType.KITEM`): `emit_kitem` (content-hash
dedup = fixpoint no-op), `status_of` (proposed→supported→accepted by span
corroboration, transitive over DERIVED_FROM; disputed only via CONTRADICTS),
`kitem_tiddlers` (`$Bibkey_KI<serial>` + khash). G4 view gains `kitem` +
`kitem_evidence` projection tables (status computed at view time). Details:
`docs/layers/L7-semantic-graph.md`. Tests: `tests/test_transclusion_render.py`
(5), `tests/test_kitems.py` (5). Next: stratum monotonicity + fixpoint driver,
then the vertical slice on 2004.05631.

**Fixpoint + the vertical slice (two-store plan steps 3+4, 2026-06-12).**
`semantic/fixpoint.py` — `run_fixpoint(graph, resolver, [(stratum, pass)])`
loops stratified passes until a round adds no kitem/evidence (quiescence by
content-hash fingerprint; the driver caught and fixed an emit_kitem evidence-
bloat bug) + `check_stratum_order` (warn-only monotonicity).
`semantic/claims.py` — the stratum-4 extractor: claim/definition SENTENCES →
kitems with evidence spans `{bibkey, node, range, role, page}`, statements
rendered through the `detranscluded` policy. `semantic/rulebook.py` +
**`pdfdrill rulebook <pdf|md>`** — accepted/supported kitems → `rulebook.md`,
one statement per line with a `[→k:hash8]` drill-down anchor (+ kitem
tiddlers; below-bar count never hidden). **Vertical slice proven on
2004.05631**: 37 kitems (definitions like Cartesian-closed/density-operator),
anchor → kitem tiddler → span → the p95 model Paragraph; second run = 0 new
(fixpoint no-op). Tests: `tests/test_fixpoint.py` (3),
`tests/test_claims_rulebook.py` (3).

**Reified passes + provenance (2026-06-17).** `produced_by` was a bare string
naming a process with no object behind it and no record of a single invocation.
Three additive layers close that (stdlib-only; `produced_by` stays a string):
- **`semantic/question.py`** — `Question` (frozen): the reusable DEFINITION of a
  pass (`qid`=the produced_by value, `description`, `prompt_version`, `emits_
  entities`/`emits_relations`, `stratum`) + a `REGISTRY` / `register` / `get`.
  Every produced_by the package emits is pre-registered (bib/cite/claims_v1/
  concepts/docmodel/iban/ner/segment + pdfdrill/mathpix/bic/german_address/
  extract_ids + the invocation-level ingest_document/ingest_docmodel).
  `compiler.check_provenance` warns at severity **`info`** (never critical) on an
  unregistered produced_by — so existing graphs stay `valid`. Tests:
  `tests/test_question.py`.
- **`semantic/transformation.py`** — `Transformation`: ONE process invocation as
  a content-addressed node (`tid = content_hash("trans|qid|model|version|" +
  sorted source content-hashes)`, EXCLUDING timestamp/cost/responses → re-running
  the same invocation on the same inputs is a fixpoint no-op). Stored on the
  graph in `transformations: {tid: …}` (NOT as Relations — many→many hyperedges
  would break the binary `SIGNATURE_TABLE`); `record_transformation` idempotent;
  round-trips in the sidecar. `record_batch`/`snapshot` group an invocation's
  evidence/edges and stamp its `tid` into `grounding["trans"]` (setdefault →
  re-run never overwrites). Wired into `build.ingest_document`/`ingest_docmodel`
  and the `claims` kitem pass (`seed=bibkey`; stamping touches only grounding,
  never evidence counts → quiescence preserved). Verified: same doc twice →
  identical transformations; cspmath → 2 transformations, 57 relations + 171
  evidence carry the trans tid, compiler valid. Tests:
  `tests/test_transformation.py`.
- **`semantic/belief.py`** — a derived REPORT COLUMN, never a source of truth:
  conservative weakest-link `belief_min(parents, own)=min(parents)*own`, computed
  lazily over the `derived_from` DAG and exposed only as a `{entity_id: belief}`
  column (never an Entity/Evidence field; never feeds the kitems `status`
  lattice). Prerequisite fix: `Entity.best()` ties now break by deterministic
  content-hash ordering (not recency), so belief is order-independent (verified:
  identical across opposite ingestion orders; leaf 1.0 / mid 0.9 / top 0.72).
  Tests: `tests/test_belief.py`.

**LLM text projection (`pdfdrill llmtext`, 2026-06-13).**
`docops/projectors/llm_text.py` (`LLMTextProjector`) — a flat dump for an LLM:
per unit the tiddler-style TITLE (`<bibkey>_PARA_<NNNN>` / `_EQ<NNNN>_p<NNN>` /
`_FO<NNNN>`) then the content — paragraph TEXT or formula LATEX — in document
order, units separated by a configurable delimiter (default `%%%%`). Two
corpus-quality rules baked in: **a LaTeX paragraph is ONE block** so paragraph
text is split on double line breaks into separate units (`#1`/`#2`-suffixed
titles); **empty/null formulas are skipped** (latex `""`/`null`/`None` = a
CDN-crop-only equation, nothing for the LLM to read). `pdfdrill llmtext
<pdf|md> [--delimiter X] [--no-split]` → `<key>.llm.txt`. Verified on
2312.11532: 262 units (58 paragraphs split out + 151 non-empty formulas), 0
units with an internal double break. Tests: `tests/test_llm_text.py` (5).
**Audit finding (the motivation):** across 25 drilled models, paragraph
merging is pervasive (e.g. 36/58 paragraph tiddlers on 2312.11532 carry an
internal `\n\n` — MathPix returns several LaTeX paragraphs as one block);
the projector splits at consumption time. Transclusion-less paragraphs are NOT
a defect (audited: such paragraphs contain no formula/inline-math reference).
3 corpus formulas have empty latex + a CDN crop (vision/snip candidates). The
model-level paragraph split (a docmodel mutator) is a deeper follow-up — it
must preserve the offset-based transclusion machinery.

**Cleanup + consolidation (tiddler tags, fractal TOC, heading residuals; 2026-06-13).**
Three QC actions:
- **Structural tags for filter performance** (`tiddlywiki.py`): the document
  header + every reference/bibentry tiddler now carry **`bibtex`**; a TikZ
  diagram (latex_code matches tikzpicture/tikzcd/`\draw`/…) carries **`tikz`**
  alongside `diagram` (every type already had its own tag).
- **Structured fractal-index TOC**: the `toc` tiddler is rebuilt as an xref
  index — one row per section = its **fractal index** (`fractal_index(doc)`:
  1 / 2.3 / 2.3.1 from the section tree's levels, distinct from the flat
  `section_number`) + caption + page + a link to the section tiddler
  (`format: fractal_xref`); emitted even when the model has no Toc object.
- **MathPix heading-residual cleanup** (`pdfdrill clean`, `heading_cleanup.py`):
  a Paragraph whose text MathPix merged with a leading `\section*{Title}` is
  stripped to the title alone, recording `kind` (section/subsection/…) +
  `refnum` (lifted leading number, else "") — so semantic analysis sees plain
  text. The tiddler render still shows the WikiText heading (the projector
  rebuilds transclusions from the immutable source stream, separately), while
  `props["text"]` / llmtext / gaps now read clean text. Idempotent. Verified
  on 2004.05631: 57 paragraphs cleaned, llmtext has 0 sectioning commands left,
  header+63 refs `bibtex`-tagged, fractal TOC rows `2.1 [[Stalks|…_H…]] p. 8`.
  Tests: `tests/test_heading_residual.py` (5), `tests/test_tiddler_tags_toc.py`
  (4).

**Image locate / compare (`pdfdrill locate`, `pdfimg_locate.py`; 2026-06-13).**
Vendored the user's `pdfimg_locate.py` (stdlib + pdfplumber, no new deps) — a
rigorous embedded-image locator that reports everything in ONE canonical
coordinate system (points, **top-left origin, y-down — the MathPix lines.json
orientation**): native pixel size + ppi (`pdfimages -list`), the placement
rectangle (pdfplumber content-stream geometry), **full-page detection** (=
"nothing to do") + recurring-**TEMPLATE** (slide background) detection, the PDF
**object number** (the join key into the model), and normalized [0,1] coords
(resolution-independent). `match_against_mathpix_lines` COMPARES each image to
the MathPix region(s) drawn over it (IoU / fraction-inside in normalized space,
so render DPI is irrelevant); `mathpix_only_figures` surfaces figures that exist
ONLY in MathPix output (vector charts; figures inside a scanned full-page
raster) for rasterize+crop. **`pdfdrill locate <pdf>`** reuses the stored
pdfinfo/pdfimages text when present (no re-run), runs the comparison when a
lines.json exists, and stores `image_placements` in the sidecar. Verified:
2004.05631 → 100 images all matched to a MathPix region; ocrtest scan → 45
full-page rasters flagged nothing-to-do. Complements (rigorous coords/IoU) the
existing containment-fusion in `image_model.py`/`embedimages`. Tests:
`tests/test_pdfimg_locate.py` (parsers, IoU/fraction-inside, canonical→MathPix
px, built-PDF round-trip).

**Transclusion materialization + footnote/EQ-title cleanup (`pdfdrill clean`, 2026-06-13).**
Three user-reported residuals, one root cause — `props["text"]` was the RAW
source text while only the tiddler path transcluded:
- **Footnotes** (`heading_cleanup.extract_footnote_paragraphs`): `\footnotetext{
  \({ }^{N}\) …}` that MathPix left as a plain Paragraph (the FootnoteProcessor
  only sees `type=footnote` lines) is lifted into a Footnote object (refnum +
  anchor_marker + content), so it transcludes `{{<fn>||FN}}`; the spent
  paragraph is dropped. 13 lifted on 2004.05631.
- **Materialization** (`heading_cleanup.materialize_transclusions`): the
  TiddlyWiki projector's transcluded paragraph text is written back into
  `props["text"]`, so llmtext/semantic/markdown read `{{<eq>||FO}}` /
  `{{<fn>||FN}}` instead of raw `\(X\)` / footnote markers — matching the
  tiddlers. Idempotent (projector rebuilds from the immutable source stream;
  original kept under `text_source`). 491 paragraphs on 2004.05631 → 0 PARA
  llmtext units with raw inline math.
- **EQ/TAB title**: dropped the `_p<NNN>` page suffix from the tiddler titles
  (`2004.05631v1_EQ0038`, not `…_EQ0038_p029`) — page already lives in the
  `page` FIELD; `llm_text` mirrors the scheme.
`pdfdrill clean` now runs footnote-extraction → heading-residual strip →
materialization. Tests: `tests/test_heading_residual.py` (footnote extraction),
`tests/test_llm_text.py` (EQ title). Suite green.

**Still deferred (roadmap):** index from LaTeX `\index{}` source (rendered-index
OCR is unreliable); graph→linked-Tiddler projection; the reasoning-flow /
abstraction layers.

## Storage-overhead reduction (stage 1 of the tiddler-canonical move)

The `model.docmodel.json` was dominated by the `DehyphenationProcessor`'s derived
streams, which stored **one anchor per CHARACTER** (`{"codepoint":"x"}` keyed by a
14-char opaque anchor → ~50 bytes/char). On 576-659-1-PB that was **1.59 MB of a
3.1 MB file (51%)**, sitting *before* the actual text (key order `meta → streams →
objects`) — the "scroll past 34 MB of offsets to reach the text" problem.

- **Fix (stage 1, done):** the de-hyphenation derived stream now stores **one
  anchor per LINE** holding that line's cleaned text (`{"text": …}`); the
  `dehyphenate` alignment is per-line anyway, so nothing is lost.
  `PromoteCleanedText` reads per-line `text` (per-char `codepoint` kept as a
  fallback for old models). Result: model **3.1 MB → 1.1 MB (−64%)**, the
  de-hyphenation streams **1.59 MB → 53 KB (−97%)**. Tests:
  `tests/test_docops.py::test_dehyphenation_stream_is_per_line_not_per_char`.
- **Direction (stage 2+ — tiddler-canonical, overlay/merge):** make the
  TiddlyWiki tiddler array the canonical, editable store and rebuild the docmodel
  transiently from the persisted `lines.json` for graph ops. Merge as much as
  possible INTO tiddlers (overlay extra fields: lines.json/pdfplumber/OCR page
  records keyed to the page, etc.) or LINK tiddlers (a diagram tiddler links its
  svg tiddler). The offset machinery (the root cause of per-char/line streams)
  retires once text carries materialized `{{…||FO}}` tokens. **Multi-document
  layer:** per-document tiddlers carry a **bibtex-key prefix**; a top **CSP-prefix**
  layer holds a document list + a concept tree, where concepts collect links to
  documents as tiddler titles.

## Born-digital chars→lines converter (`chars_to_lines.py`)

A pdfplumber CHARACTER dump (`pages[].chars[]` with positions/fonts — a
born-digital PDF's text layer) converts to a MathPix-shape `lines.json` so the
PDF is drillable OFFLINE with no MathPix. `chars_to_lines_json` flips each char
from PDF bottom-left to the MathPix top-left origin, groups chars into visual
lines (baseline) then words (x-gaps), and hands the word records to
`ocr_lines.lines_json_from_words` (the proven offline assembler). Verified on
the Heim Massenformel (157 MB char dump → 1.5 MB lines.json, 138 pages / 5415
lines → a 489-object model, zero MathPix). Tests: `tests/test_chars_to_lines.py`.

## Front-matter identifiers (`pdfdrill identifiers`)

A book's ISBN/ISSN/DOI and its publisher/author live on the front matter (title
+ copyright/imprint page). **`pdfdrill identifiers <pdf>`** scans only that
window — pages 1..offset from `booktoc` when the offset is a real boundary
(≥3), else the first `DEFAULT_FRONT=5` pages (capped 20) — so it's cheap and
precise. Loads via the lazy **DocGraph** read path (third read-path command
after `llmtext`/`booktoc`). Runs the checksum-validated `features` extractors
(`extract_isbn` ISBN-10/13 + ISSN, `extract_doi`, `extract_ids` German admin
numbers) + the arXiv id from the sidecar, plus **`identifiers.caps_entities`** —
the "uppercase sequences are NE candidates" idea: an ALL-CAPS run on the title
page (publisher/author/institution) is surfaced as a candidate (roman numerals
+ id labels excluded; multi-word, or a single ≥4-letter word), complementing
`extract_names`/concepts, never asserted as a resolved entity. **Author resolution**: the caps runs are split into names (`split_author_names`) and resolved against the known author list (arXiv metadata) via `match_entities` (`resolve_authors` — rapidfuzz SAME_AS), reporting N/M authors confirmed on the title page (honest on OCR-mashed bylines). Stores
`identifiers` (front_pages + ids + ne_candidates) in the sidecar. Verified:
arXiv paper → ARXIV id + author caps; the Heim book → "NEW WORLDVIEW OF THE
PHYSICIST BURKHARD HEIM" + "DESY". (Our corpus is preprints, so no ISBN fires;
the extractor is unit-proven on real ISBN-10/13/ISSN with checksums.) Tests:
`tests/test_extract_isbn.py` (6), `tests/test_identifiers.py` (5).

## `\appendix` → TOC connection (lettered appendix sections, 2026-06-26)

The TOC analysis now knows where the appendix begins. `latex_source.
find_appendix_pos(body)` locates `\appendix` (or `\begin{appendices}`);
`extract_sections` flags every following section `is_appendix`, and
`build_source_model` carries the flag onto the Section objects. **"If LaTeX is
available it must be used":** `latex_source.mark_appendix_from_source(doc,
src_dir)` overlays the source `\appendix` onto ANY model — including a
MathPix/OCR model that has no `\appendix` signal — by sequential caption
alignment that is **tail-sticky** (once the boundary is crossed every later
section is appendix, so a large appendix with MathPix caption drift is fully
marked). `cmd_model` auto-runs the overlay whenever the cached arXiv e-print
`texsrc/` is present (idempotent; reports the count + sets the sidecar
`appendix_sections`). `docops.projectors.tiddlywiki.fractal_index` became
appendix-aware: it anchors the index to the MINIMUM section level (so a
`\section`-only paper numbers 1, 2, 3 — not 1.1, 1.2) and renders appendix
top-level sections as LETTERS (A, B, …; subsections A.1) — real LaTeX appendix
numbering, flowing straight into the fractal TOC tiddler. Verified on arXiv
2110.11150 (neurips_2022, large appendix in `\input{appendixtheory}`): 11/26
sections flagged, TOC reads `6 Discussion` → `A Theory` → `A.1 Motivation…`.
`_SECTION_RE` also gained `subsubsection` (was silently unmatched). Tests:
`tests/test_latexbook.py` (appendix flag, build wiring, overlay onto a
MathPix-shaped model with caption drift), `tests/test_tiddler_tags_toc.py`
(letter numbering, min-level anchoring). *Open follow-up (flagged, not built):*
a compression-preserving **JPEG/PNG→EPS** wrapper (Thomas Merz `jpeg2ps`-style
PostScript DCTDecode embedding — ImageMagick `convert` RE-ENCODES and bloats) is
needed when a TikZ/figure `\includegraphics` pulls in a JPG on the
latex→dvips→dvisvgm route; no such tool is installed.

## Root/TOC/section tiddlers adapted to Markdown + `.md`/`.md.meta` export (2026-06-26)

Following the `text/markdown` switch, the BIBKEY (root), TOC and `*_H*` (section)
tiddler bodies — written for WikiText — are now Markdown:
- **TOC** (`*_TOC`): was `"*"*depth` nesting (which is **bold** in Markdown — a
  real bug) + `[[cap|title]]` wikilinks. Now a Markdown nested list (2-space
  indent per fractal level, `-` bullet) with a `<$link to="…">cap</$link>` widget
  (the Markdown plugin renders widgets) — `1`, then indented `1.1`, `1.2`, ….
- **Root** (`_root_body`): `#`/`##` headings, `-` stat list, and a STATIC list of
  `<$link>` widgets to the top-level sections (the old `<$list filter>` + `<<sec>>`
  macro doesn't render under Markdown; the static list is also deterministic). Now
  takes the `title` map.
- **Section** (`_section_body`): `## Subsections` + `-` `<$link>` bullets.
Verified on 2110.11150 (no `**` bold in the TOC; `<$link>` links throughout).

**`.md`/`.md.meta` export — `tools/tiddlers_to_md.py`.** The Claude.ai-sandbox
TiddlyWiki stores each tiddler as a FILE: this minimal stdlib tool reads a
`<bibkey>.tiddlers.json` and writes, under `<out>/<bibkey>/`, one `<title>.md`
(the `text`) + `<title>.md.meta` (the other fields, one `field: value` per line —
identity fields lead, rest sorted). So a SKILL can point at an exact path from the
bibkey-prefixed title (`2110.11150_H19.md`), and the wiki index lists them.
Templates are exported too (so `{{id||TPL}}` resolves). **Code / multi-line fields
are SIDECAR'd as their own CLEAN files (no escaping)** — `lean4`→`.lean`,
`svg_tiddler`→`.svg`, `latex_code`/`latex_original`→`.tex`, `bibtex`→`.bib`, any
other newline-bearing field→`.txt` — and the `.md.meta` points the field at that
filename (the `_canonical_uri` idea at field level). This is the shape the incoming
source-code handling needs (CHATDRILL whole codebases; LaTeX `lstlisting`s —
TiddlyWiki gives a code snippet its own type + file); `--no-sidecar` falls back to
single-line collapse. `export_tiddlers(tiddlers, out, bibkey, sidecar=True)` is
importable; `python3 tools/tiddlers_to_md.py <json> [--out DIR] [--no-sidecar]`.
Verified: 2110.11150 → 369 `.md`+`.md.meta` + 264 sidecars (`.bib`/`.tex`/`.txt`;
`.lean` once `pdfdrill lean` runs). **Deferred (user):** reference-list-driven
per-tiddler features. Tests: `tests/test_tiddlers_to_md.py`,
`tests/test_tiddler_tags_toc.py` (markdown TOC).

## LEAN4 export — STORE then PROJECT (`pdfdrill lean`, 2026-06-26)

The capstone over theorem/proof extraction, built to the user's architecture:
the Lean code is GENERATED by an LLM, STORED on the object + tiddler field, and
the projector assembles `.lean` from the STORED code (because the first
conversion is an expensive LLM call — like `bibfetch` — and a Llama-for-Lean /
AXIOM / LaTeX↔Lean CAS may supply it later; storage makes it a one-time cost).
- **`src/pdfdrill/lean_export.py`** — `generate_lean(doc, drill_dir, …)` (stage 1)
  fills each `Theorem.props["lean4"]` via the keyless **`lean` delegation task**
  (`llm_delegate`: CLI `claude -p` / sandbox handshake, `LEAN_THEOREM_PROMPT`),
  idempotent (skips theorems already carrying `lean4`). `project_lean(doc)`
  (stage 2, pure) assembles `import Mathlib` + `namespace <bibkey>` + per theorem
  a `/-- <printed title>: <LaTeX statement> -/` doc comment then the STORED Lean
  (or a `sorry`/`trivial` stub naming the generator), with the paired proof as a
  `-- proof:` comment. `lean_name` derives a Lean id from the `\label`
  (thm:scaling → `thm_scaling`).
- **`pdfdrill lean <pdf> [--limit N] [--force] [--emit-only]`** (`cmd_lean`) —
  generate→store→persist (`save_model`) then write `<bibkey>.lean`; `--emit-only`
  re-projects from stored without an LLM. Sandbox: defers the prompts and prints
  the agent instruction; re-run ingests + emits. No agent/key → emits the
  sorry-stub file.
- **The TiddlyWiki Theorem/Proof tiddlers carry the stored `lean4` field** (so the
  Lean lives in the wiki next to the statement; re-run `tiddlers` after `lean`).
- Verified on 2110.11150 `--emit-only`: `2110.11150.lean` with 11 theorems (doc
  comment = the real LaTeX statement, `namespace P2110_11150`, proofs as
  comments). Honest: Lean is LLM-sourced — the prose says VERIFY; proofs are
  comments (formalising them is the trained-model's job). Tests: `tests/test_lean.py`
  (name/prompt, project uses-stored-else-stub, lean4 tiddler field, sandbox
  generate→store round-trip). Next: a `proof` generation task; per-section
  theorem numbering; round-trip import of corrected Lean.

## Tiddlers are `text/markdown` now (2026-06-26)

CONTENT tiddlers are emitted as **`text/markdown`** (per the user); the 16 built-in
TEMPLATE tiddlers (FO/PARA/EQBLOCK/…) stay `text/vnd.tiddlywiki` — they are pure
widget machinery (`<$latex>`/`<$link>`/`<div>`). At the single `_t` chokepoint the
type is `text/markdown` and `_to_markdown` converts the only WikiText construct
that clashes with Markdown: HEADINGS (`! `/`!! ` → `# `/`## `, line-anchored so no
clash with math `f''`/`a!`/`//`). The few bold/italic spans we emit are written as
Markdown **at the source** (theorem `**Lemma 2.**`, proof `**Proof.**`, `*bibkey*`,
`*Citation placeholder for*`) — deliberately NOT a global `''`→`**` pass, which
would corrupt math double-primes. Transclusions `{{…||TPL}}` and widgets are kept
verbatim (the TiddlyWiki Markdown plugin renders them). The **FO** template now
wraps the math in a `<$link>` (`<$link><$latex …/></$link>`) so a rendered inline
formula is clickable → its own tiddler. Verified on 2110.11150: 353 markdown /
16 wikitext-template tiddlers, section `# {{!!caption}}`, lemma `**Lemma 1.**`.
Requires the official TiddlyWiki Markdown plugin in the wiki. Tests:
`tests/test_tiddler_tags_toc.py`, `tests/test_docops.py` (type + `#` heading).

## Theorem/proof extraction + paired transclusion + `\ref` resolution (2026-06-26)

The LEAN4-prep payoff: `latex_source.extract_theorems(body, theorem_envs,
newtheorem_decls)` isolates every theorem-like block (`\begin{theorem|lemma|…}`
— the envs `scan_environments` found via `\newtheorem`) and every `\begin{proof}`
in document order. Each theorem → a **`Theorem`** DocObject (kind / printed_title /
bracket `[title]` / `label` / shared-counter `number` / statement); each proof →
a **`Proof`** object PAIRED to its theorem (by the `\ref` in its `[optional]` arg,
else nearest preceding unclaimed theorem). `build_source_model` emits them in
flow order, BLANKS their spans from the prose body so statements don't also
surface as Paragraphs, sets `proof_of`/`proof_id` cross-links, and records
`source_counts.theorems`/`.proofs`. The TiddlyWiki projector emits `_THM`/`_PROOF`
tiddlers (caption = `Lemma 2 (Scaling)`, `label` field, `kind`/`refnum`), the
theorem **transcludes its proof** (`{{…||PROOF}}` + a new `PROOF` template), and
because Theorem objects carry `props["label"]`, `caption_to_wikitext`'s
`label_to_title` now **resolves a section caption's `\ref`** to the theorem.
Verified on arXiv 2110.11150: **11 Theorem + 6 Proof** objects (Paragraphs
94→65, no statement leak), 5 theorems transclude a proof, integrity 0 orphan, and
H19 "Scaling relationship: Proof of Lemma~\ref{thm:scaling}" →
`… Proof of Lemma <$link to="2110.11150_THM0003">thm:scaling</$link>` — the link
the user asked for. **Numbering caveat:** the shared-counter chain is honored
(`lemma`→`theorem`), but the `[section]` reset/prefix is NOT applied (plain
sequential per counter group). Next: per-section numbering (3.1), inline-math in
statements → `{{…||FO}}` dedup (currently kept as raw `$…$`), and a LEAN4
projector over these objects. Tests: `tests/test_theorems.py` (extraction +
numbering + pairing, build emits + no leak, tiddler pairing + caption \ref link).

## Section-caption `\ref` handling + transcluded caption (2026-06-26)

A section heading like `2110.11150_H19` "Scaling relationship: Proof of
Lemma~\ref{thm:scaling}" carried a RAW `\ref` and never showed its own caption.
`tiddlywiki.caption_to_wikitext(caption, label_to_title)` now renders a LaTeX
caption as TiddlyWiki: the `\ref`-family (`\ref`/`\eqref`/`\cref`/`\autoref`/…)
resolves to a `<$link>` when the label is known (the projector builds
`label_to_title` from every object carrying `props["label"]` — equations,
algorithms, …), else shows a readable `(label)`; `\texttt`/`\textbf`/… font
wrappers are unwrapped and `~` ties become spaces. Each Section tiddler now: (a)
leads its **text** with `! {{!!caption}}` (the heading transcludes the caption
field), (b) stores the resolved wikitext in **`caption`**, and (c) preserves the
verbatim LaTeX on **`caption_latex`** (only when the caption carried LaTeX).
`tiddler_integrity` ignores `{{!!field}}`, so this adds 0 dangling. Verified on
2110.11150: H19 → caption `Scaling relationship: Proof of Lemma (thm:scaling)`,
caption_latex the raw `…~\ref{thm:scaling}`, text `! {{!!caption}}`. **The
`thm:scaling` label resolves to a `<$link>` automatically once theorem/proof
objects exist** (the next step — extract `\begin{theorem}`/`proof` blocks as
Theorem/Proof DocObjects with `label`/number, paired and transcluded; the env
census in `doc.meta["environments"]` + this label resolver are the groundwork).
Tests: `tests/test_tiddler_tags_toc.py` (`caption_to_wikitext`, section caption
field + caption_latex).

## Book TOC layer — greppable, printed→PDF page-aligned (`pdfdrill booktoc`)

A book's printed TOC pairs each chapter/section with its PRINTED page number,
which is NOT the PDF page (front matter — title/copyright/TOC/preface — shifts
everything by a constant). `src/pdfdrill/booktoc.py` recovers that **front-
matter offset** without guessing: it matches TOC titles to the model's
`Section` objects (which carry the real PDF page) and takes
`median(section.pdf_page − toc.printed_page)`. A matched entry resolves to its
section's exact PDF page; an unmatched one falls back to `printed_page +
offset`. `parse_toc_entries` dedupes MathPix's triplicate TOC fragments and
lifts a leading section number out of the title.

**`pdfdrill booktoc <pdf>`** writes `<bibkey>.toc.txt` — one line per entry
(`number  title  printed_page  pdf_page  [~=estimated]`) an LLM can **grep by
chapter/section name to get the PDF page directly**, then `pdfdrill page`/
`rasterize` it. Cheap standalone navigation artifact: loads via the lazy
**DocGraph** read path (~0.36s, no full model build) — the next read-path
migration after `llmtext`. Verified: 2004.05631 → offset +0, 38/41 page-exact;
the Heim book → **offset +1** (printed p5 → PDF p6), 34/35 page-exact, 100%
agree. Tests: `tests/test_booktoc.py` (parse/offset-zero/offset-positive/
align/greppable).

## `status` bibliography/BibTeX state + load_docgraph staleness fix (2026-06-26)

`pdfdrill status` now reports the bibliography: the entry COUNT, a per-SOURCE
breakdown (where each BibTeX record came from), how many carry full BibTeX / a
year / linked in-text citations, and a WARNING for any web-enriched entries.
Each `Reference` carries a **`ref_source`** prop set at creation —
`bib` (a `.bib` file, `load_bibtex_file`), `bbl` (a compiled `.bbl`,
`ingest_bbl`), `bibitem` (an inline `\begin{thebibliography}`,
`ingest_bbl(source="bibitem")`), `text` (printed/OCR'd refs parsed
heuristically, `add_reference_objects`) — and `bibfetch` stamps
**`bibfetched=True`** (web/Perplexity-sourced ⇒ may introduce errors).
`commands._format_bibliography_state` (pure) formats the lines;
`_bibliography_status_lines` loads the model (DocGraph) and aggregates. Verified
live: 2104.08926 "16 from inline \bibitem", paper396 "16 from text (OCR/printed,
heuristic)", 2109.04713 "39 from .bbl (compiled)".

**Latent correctness bug fixed along the way:** `model_io.load_docgraph` read the
`.docpack` sidecar with NO mtime guard (unlike `load_model`), so every read-path
command (`status`/`llmtext`/`classify`/…) served STALE data after any command
that saved the canonical `.docmodel.json` via raw `json.dump` (bibliography /
bibfetch / bibsource all do). `load_docgraph` now uses the same `_fresh()` guard
and falls back to the plain model when the sidecar is stale. Tests:
`tests/test_bibliography.py` (ref_source tagging + `_format_bibliography_state`),
`tests/test_model_io.py::test_load_docgraph_ignores_stale_sidecar`.

## Reference-based model storage + lazy read path (docpack / docgraph, 2026-06-14)

Per-call load time matters because an LLM drives `pdfdrill` repeatedly. The
`model.docmodel.json` is large (≈75% is one `{"codepoint":…}` dict + a 14-char
anchor PER CHARACTER of every dehyphenated paragraph / rendered equation), and
`Document.from_dict` stays ~1.9s regardless of file size because it expands
those char dicts. Two vendored, stdlib-only layers (Claude.ai proposal,
reviewed + measured):

- **`src/pdfdrill/docpack.py`** — lossless reference-based compaction: char
  streams → one packed hex-anchor blob + codepoint string; shared intern tables
  (STR/BOX/REG/GEOM/PROF + enums + cross-ref anchors). `unpack(pack(m)) == m`
  (verified). 2004.05631: **52 MB → 15 MB (−71%), 4.4 MB gz (−91%)**; pack
  0.69s, unpack 0.33s.
- **`src/pdfdrill/docgraph.py`** — a lazy, indexed VIEW over the packed model:
  id/type/reverse-link indexes built from the cheap `objects` list; props/text
  de-interned on first access; the 25 MB of char streams are **never expanded**
  unless asked. Loads the thesis in **~0.2s** (vs ~1.9s) at far lower memory.
- **`src/pdfdrill/model_io.py`** — the single chokepoint: `save_model` writes
  the canonical `.docmodel.json` AND the packed `.docpack.json` sidecar in
  sync; `load_model` returns a full `Document` (packed sidecar preferred when
  fresh, mtime-guarded, falls back to legacy); `load_docgraph` is the fast
  read-path. All 15 model reads + 5 model writes in `commands.py` route through
  these.

**Pilot (the hot LLM read): `pdfdrill llmtext` now loads via DocGraph** —
`build_llm_text` is a pure core over anything exposing `.type/.id/.props` (both
`DocObject` and `GraphNode`), so the fast path is byte-identical to the
full-Document path. End-to-end on the 50 MB thesis: **~2s → 0.38s wall, output
identical**.

**Correctness proven ("all projections stay correct"):** every projector
(tiddlers / llm_compact / report / compare / plaintext / llmtext) emits
byte-identical output (timestamp-normalized) whether the model is loaded
canonically or via the docpack round-trip — confirmed live on 2312.11532.
Tests: `tests/test_model_io.py` (round-trip, save/load, stale-sidecar guard,
DocGraph↔Document byte-equality, counts). The `.docpack.json` sidecar lives in
`.drill/` (gitignored). **Next:** migrate the remaining read-only LLM-facing
commands (`status`, `gaps`, `tables`, `rulebook`, lookups) to `load_docgraph`
for the same ~10× load win; mutating/transclusion commands keep the full
`Document` via `load_model`.

## Controlled-vocabulary layer (`src/vocabnet/`, additive — converters only)

A NEW, self-contained, **pure-stdlib** package: one consistent interface over
every controlled vocabulary / thesaurus / classification index feeding pdfdrill
(MSC, DLMF, OntoMathPRO, PhySH, ACM CCS, STW, GND, GermaNet), plus a federation
that **always queries all sources and keeps the misses as signal** (a string
grounded in MSC + PhySH but absent from ACM CCS + STW is math-physics, not CS,
not business). Whatever the native format, a source compiles to the SAME
`Vocabulary` shape and answers the same queries.

- **Core** (`vocab.py`): `Concept{code, pref, labels{lang:[...]}, parent,
  children, related, definition}` + `Vocabulary` — `lookup`/`ancestors`/
  `siblings`/`narrower` (O(len code) hierarchy) and `classify(text,k) ->
  [Hit{scheme,code,pref,score,evidence}]`, an **IDF-scored inverted index** over
  unigrams + adjacent bigrams (prefLabel 1.0, synonyms 0.7, bigrams ×1.3) with
  diacritic folding (`Schr¨odinger`→`schrodinger`). No if/else chain. `compile`
  is the single entry point every adapter ends in; `save`/`load` round-trip.
- **Federation** (`federate.py`): `Federation.load_dir("vocab/compiled/")` →
  `res = fed.classify(text)` with `present`/`absent`/`profile` (dense vector over
  schemes, 0.0 for a miss)/`top`/`fingerprint()` (blake2b over the coverage
  signature)/`to_dict()`. Misses are kept, never dropped.
- **Adapters** (each ends in one `Vocabulary.compile(...)`):
  - `skos.py` (vendored) — SKOS N-Triples + RDF/XML → PhySH, ACM CCS, STW, GND.
  - `sources.msc_from_json` (vendored shim) — the `mscc.py` `msc2020.json`.
  - **`dlmf.py`** (written here) — the **MathPix-Markdown** route (the only
    PDF-route source: DLMF chapter PDF → `pdfdrill md` → here): an ATX heading's
    leading **dotted section number** (`5.2.1`) is the concept code, hierarchy
    follows the dotted prefix (independent of OCR-fragile `#` depth), and the
    prose beneath a heading is folded in as an alt label so `classify` finds a
    section by the function names in its body.
  - **`ontomathpro.py`** (written here) — **OWL 2 Manchester** (`.omn`): a line
    state machine over `Class:` frames, **E-number** codes, multi-lang
    `rdfs:label`/`skos:prefLabel` annotations, `SubClassOf:` → parent (anonymous
    restrictions skipped).
  - **`germanet.py`** (written here) — **GermaNet XML**: a directory (synset
    files + `gn_relations.xml` hypernymy) or a single file (synsets only);
    `<synset>` → code, `<lexUnit><orthForm>` → labels[de], `<paraphrase>` →
    definition, `con_rel has_hyponym/has_hypernym` → parent/children.
- **MSC acquisition (`msc_html.py`).** zbMATH's clean MSC2020 JSON is behind
  Cloudflare + a T&C wall; the **CRAN MSC-2010 HTML** mirror is openly fetchable
  (CC-BY-NC-SA) and structurally compatible (the physics branches 35Q/81/82/83
  are stable). `parse_cran_msc(html)` parses each `CODE Title [See also …]` line,
  strips `[See also]` / `(should also be assigned …)` boilerplate, repairs UTF-8
  mojibake, and derives the hierarchy from the code prefix (81P05→81Pxx→81-XX);
  `sources.load_msc` dispatches `.html`→msc_html, `.json`→the mscc.py shim.
  **Cross-ref vs definition anchors:** CRAN links cross-references with an
  internal-fragment `<a href="#code:41A25">` inside `[See also …]` notes while a
  section header is an external-href `<a href="https://ams.org/…">81-XX</a> Title`;
  the parser strips only the `href="#…"` cross-ref anchors (else a linked code is
  read as a bogus definition whose "title" is the following note text — that lost
  the 81-XX/81Txx/83-XX section headers and produced "see also" fragment titles).
  Verified: CRAN HTML → **6198 MSC concepts** classifying physics correctly
  (nonlinear Schrödinger→35Q55, QFT→81T, general relativity→83C05, Kaluza-Klein
  →83E15). Tests: `tests/test_vocabnet_msc_html.py`.
- **`pdfdrill classify <pdf|md>` (`src/pdfdrill/classify.py`).** Subject-classify
  a drilled document against the federation (fast DocGraph read path; persists
  `classification` in the sidecar). **Segment voting** (each section caption /
  paragraph / equation classified, votes tallied) — robust to document length,
  where a whole-doc blob lets generic words dominate. Precision levers, found
  empirically on the Heim corpus: **strip LaTeX commands** from math
  (`\partial`→"partial", `\right`→"right" otherwise match "Right alternative
  rings"); **require a contentful phrase (bigram) match** (a single shared word
  doesn't vote, and MSC filler bigrams like "in connection with" are excluded);
  **drop catch-all codes** ("None of the above", "General reference"). Leads with
  the **2-digit MSC discipline rollup** (the robust signal) + top fine codes.
  German prose only matches the English MSC labels after `pdfdrill translate`
  (`has_translation` detects the `text_source` marker; the command emits a NOTE
  when the doc looks non-English and untranslated). Verified on Heim's
  Unified-Field-Theory (English): rollup led by **83 Relativity & gravitation**
  (83C45 quantization of the gravitational field, 83C75 space-time
  singularities) + 78 electromagnetic + 70 mechanics. Tests: `tests/test_classify.py`.
- **Multi-source federation (MSC + PhySH).** Any compiled scheme in
  `vocab/compiled/` auto-participates — no code change. **PhySH** (Physics Subject
  Headings, APS, CC-BY) is the physics complement to MSC's math view: download
  `physh.nt.gz` from the `physh-org/PhySH` repo → `skos.py` ingests the N-Triples
  → ~3900 concepts (DOI-UUID codes, readable `prefLabel`s). On the Heim corpus the
  classifier then reports BOTH a math view (MSC: 83 relativity/gravitation, 33
  special functions, 11 number theory) AND a physics view (PhySH: General
  relativity formalism, Large scale structure of the Universe, Equations of state
  of nuclear matter, Singularities in general relativity). `classify` shows the
  MSC rollup + top codes, then each non-MSC scheme's top concepts by vote. ACM
  CCS / GermaNet / DLMF / OntoMathPRO drop in the same way (their stubs).
- **German vocabularies + language routing (STW, GND).** `classify_document`
  routes each vocabulary to the text in ITS language: English schemes (msc/physh)
  classify the translated `text`, **German schemes (stw/gnd) classify the original
  `text_source`** (written by `pdfdrill translate`) — so a German original
  classifies directly, no translation needed. **STW** (ZBW economics thesaurus,
  SKOS via skos.py) and **GND** (DNB subject authority — RDF/XML in the GND
  element set `gndo:`, NOT SKOS, so a dedicated **`gnd.py`** streaming adapter:
  keeps subject-heading types + ≤4-word labels, dropping the work/event/award
  titles GND mis-types as subjects). German function-word bigrams added to the
  classify filler set. **Domain restriction is what makes GND useful:** the raw
  ~169k-term authority is too broad — lexical matching of OCR'd input hits
  off-domain false matches (art motifs, law, prizes). `gnd.load_gnd` therefore
  restricts (by default here) to the **physics/astronomy/math GND Systematik**
  (`gnd-sc` 20 Astronomie / 21 Physics / 28 Mathematics, verified against the
  data) → **~15k concepts**; a physics doc is no longer matched against medicine/
  law/art (`subject_categories=None` keeps the full authority). After the
  restriction, GND classifies the German ORIGINALS directly to real concepts —
  **Einheitliche Feldtheorie, Diracsche Löchertheorie, Übertragung in einer
  Mannigfaltigkeit, System von partiellen Differentialgleichungen,
  Ljapunov-Stabilitätstheorie, Orthonormalsystem**. STW (economics) stays
  off-domain by design (near-absence = "not economics", itself federation
  signal). Tests: `tests/test_vocabnet_gnd.py`.
  - **Language-routing fix — German vocab never classifies a non-German doc
    (2026-06-27).** For an UNTRANSLATED English doc, `de_segs`
    (`prefer_source=True`) falls back to the English `text`, so stw/gnd matched
    English NOISE (arXiv 2603.16021, an AI paper → `COMPASS-Detektor`, German
    economics). `classify_document` now detects the routed text's language
    (`features.extract_language.language_of`, fallback `has_translation`) and
    SKIPS a `lang="de"` vocab unless the text is actually German — so those
    schemes land in `absent`, not as spurious hits. A German original (text or
    `text_source`) still classifies directly. Tests: `tests/test_classify.py`
    (`test_german_vocab_skipped_on_english_document`). Honest caveat (separate,
    unfixed): with NO CS/AI vocabulary loaded (only MSC/PhySH/GND/STW), a CS
    paper still produces lexical NOISE from MSC/PhySH (Matroids/plasmas) — the
    real fix is loading ACM CCS (the adapter exists; the data isn't built).
- **CLI:** `python3 -m vocabnet.sources {list,build <scheme> [path],build all}`.
  `build` defaults its input to the first present file under
  `vocab/sources/<scheme>/` and writes `vocab/compiled/<scheme>.json`.
- **Licence-bound downloads stay OUT of git.** The CONVERTERS (`src/vocabnet/`)
  and a committed `STUB.md` per source (download link + licence + build command)
  + `vocab/README.md` are tracked; `.gitignore` excludes everything under
  `vocab/sources/*/` except `STUB.md`, and all of `vocab/compiled/`. PhySH
  (APS copyright) and GermaNet (signed academic licence) must not be
  redistributed; MSC2020 / STW / GND / ACM CCS / OntoMathPRO are openly
  reusable. **Start with MCS** (`msc2020.json` from `mscc.py` → build).
- Verified end-to-end: MSC fixture → `build msc` → `compiled/msc.json` →
  `Federation.load_dir` → `classify`/`ancestors`/`resolve` round-trip. Tests:
  `tests/test_vocabnet.py` (9 — core/shim/federation + the three new adapters).

## Semantic-compiler FRONT END (`src/semantic/frontend/`, object×format detection — seed)

The detection half of the semantic compiler: general, abstract **object detectors**
that feed the existing `semantic/` graph (the conclusion back end). Built per the
user's architecture — **one module per OBJECT and one per input FORMAT**, with the
detector for a pair living in its own **CELL** module. That granularity is the
point: each cell is the slot where a **LEAN grammar** will later GENERATE the
parser on the fly (LEAN expresses the recursive grammar via a fixed-point/Y-
combinator) and generate+validate the cell's test corpus; the hand parser in each
cell today is the BOOTSTRAP the generated one supersedes without changing callers.
(Named `frontend` not `compiler` to avoid shadowing the existing graph validator
`semantic/compiler.py`.)

- **`contract.py`** — the three registries + ABCs: `FormatModule` (raw→`Surface`),
  `ObjectModule` (canonical `schema()` + `conclude()`), `CellModule`
  (`Surface`→`[DetectedObject]`); `DetectedObject{kind,format,fields,evidence,
  confidence}`. `register_format/object/cell`, `get_*`, `FORMATS/OBJECTS/CELLS`.
- **Driver (`__init__.py`)** — `detect(raw, fmt, kind)` = run the `(kind,fmt)` cell
  over the format's surface; `to_bibtex(obj)` = the object's conclusion.
- **First object — FRONTMATTER** (`objects/frontmatter.py`): the provenance header
  of ANY document. The unification (the user's rule): an `agent` carries a ROLE and
  **author (LaTeX) ≡ sender (letter) ≡ issuer (invoice)** all map to BibTeX
  `author`; a letter's **recipient** is the only genre-specific addition → a new
  `recipient` FIELD (not an address entity per author). Schema: `genre,title,
  agents[{role,name,org?,address?}],date,recipients[],identifiers[],subject`.
- **Formats:** `formats/latex.py` (splits preamble/body + documentclass),
  `formats/text.py` (blank-line blocks for OCR/pdftotext).
- **Cells:** `cells/frontmatter_latex.py` (\title/\author/\date/class→genre),
  `cells/frontmatter_letter.py` (letterhead=sender, recipient block, date).
- Verified: LaTeX (Kingma/Welling) → `@article` author record; German Finanzamt
  letter → `@letter` with **author=sender, recipient as a field**. Tests:
  `tests/test_frontmatter.py` (5). NEXT: more cells (mathpix/arxiv_html/zugferd_xml),
  the LEAN grammar per cell (parser-gen + test oracle), and wiring `conclude()` into
  the `semantic` graph (agents→Person/Org via IdentityResolver; recipient→field or
  optional address node). The scattered detectors it replaces: `sources.
  parse_arxiv_abs_html`, `identifiers.caps_entities`, `page._extract_title`,
  `markdown_source`, `latex_source` title/author.

## docOS — document-set shell (`pdfdrill docos`, `src/pdfdrill/docos.py`, multi-doc — Step 1/5)

A working SET of documents managed like a Unix shell (`cd`, glob `add`/`remove`),
with a strict materialization ladder **L0→L1→L1.5→L2→L3→L4** where each layer
demands the lower ones and higher commands auto-build what's missing — the
SET-level form of pdfdrill's per-doc prerequisite state machine. Most per-doc
pieces already exist (`md`/`booktoc`/`mathir`/`abstract`/`conclusion`/`semantic`/
`combine`/`retrieve`); docOS adds the orchestration the toolchain lacked.

**Step 1 (done) — L0 selector.** `DocosState{folder, documents, saved_sets, level,
materialized}` persisted to `<config>/docos.json` (or `$PDFDRILL_DOCOS_STATE`),
stateful across invocations. Ops: `cd` (rel/abs), `add <glob>` (recursive `**`,
dedup, `.pdf`/`.md` only; a dir → its PDFs), `remove <glob>` (fnmatch path or
basename), `clear`, `save-set`/`load-set` (load demotes level→L0 per spec),
`sets`, `show`. `render_ui` prints the compact, **level-gated** command block
(L1/L1.5 live once a set is loaded; L2+ shown `[requires L<x>]`). `dispatch(state,
line)` routes one command; L1+ verbs (`make`/`extract`/`ensemble`/`synthesize`)
report as *planned* so the shell skeleton is complete and honest. **`pdfdrill
docos [<command line>]`** runs one line + prints the UI; no args → show state.
Verified: `cd data` → `add *.pdf` (8 docs) → `save-set corpus`, UI gates L2+,
state round-trips. Tests: `tests/test_docos.py`.

**Step 2 (done) — L1/L1.5 fan-out.** `make <repr>` runs an existing per-doc
command over the whole set, records per-doc status in `state.materialized`, and
recomputes the level (any make → L1; all four L1.5 summaries ok for all docs →
L1.5, which un-gates L2). Mapping: **L1** md→`cmd_md`, toc→`cmd_booktoc`,
math→`cmd_mathir`, figures→`cmd_embedimages`, refs→`cmd_bibsource`; **L1.5**
abstract→`cmd_abstract`, conclusion→`cmd_conclusion`, claims/contributions→cue-
sentence extractors (`_cue_sentences` over the model prose → sidecar
`docos_claims`/`docos_contributions`; the only new producers — contributions had
none). Each per-doc command auto-builds its own model, so the lower layer
materializes itself. `make`/`status` are now live in `dispatch`; `runner` is
injectable (tested with a fake). `status` shows per-repr ok/total. Verified live:
2-paper set → `make conclusion`/`abstract` 2/2 ok; single doc → all four summaries
→ level **L1.5**, L2 un-gated. Tests: `tests/test_docos.py` (12).
**Plan:** 3 = L2 extract fan-out; 4 = L3 ensemble (reuse `combine`/`retrieve` for
the index + search/stats); 5 = L4 synthesis (review/survey — the heavy, last piece).

## Conclusion retrieval (`pdfdrill conclusion`, `src/pdfdrill/conclusion.py`)

The Abstract states the goal + chosen method, NOT the results — the conclusion is
where the actual (often much narrower) outcome lives. `pdfdrill conclusion <pdf|md>
[--limit N]` finds the conclusion SECTION by a heading heuristic over the Section
captions (the document's own TOC): tiered keywords — STRONG (conclusion/concluding/
fazit/schlussfolgerung) preferred before the References/Appendix boundary, then any
strong, then MEDIUM (summary/discussion/outlook/future work/zusammenfassung/…) —
and returns its paragraphs in `flow_index` order (the flow-range between the
conclusion heading and the next section; `parent_section` for source models). No
named conclusion → the final MAIN-body paragraphs (excluding the References/Appendix
region). Fast DocGraph read path; pure helpers take any `.type`/`.props` object.
Output leads with the section name + a caveat that the stated conclusion may
overstate scope vs. the actual examples/code. Verified: 2312.11532 → “Conclusion
and Future Remark”; 2606.16905 → “Conclusion and Future Work” (whose text —
“an initial validation of the 'one model fits all' premise” — is markedly narrower
than its broad abstract). Tests: `tests/test_conclusion.py` (4 — strong-before-
appendix, flow-range paragraphs, medium-near-end, final-paragraph fallback).

## Canonical math layer (`src/mathlayer/`, SymPy seed — step 1)

The first step toward a **canonical CSP math layer**: one tree per FO/EQ
expression from which every target is later generated (SymPy, Lean4, FriCAS,
Mathematica, SMT-LIB, GraphRAG). The value is the SINGLE tree, not SymPy itself —
SymPy is merely the first backend and the canonical anchor (its `srepr`).

- **`parse.py`** — LaTeX→SymPy via the IMPORTED `latex2sympy2_extended` library
  (optional `[math]` extra; not vendored). Lazy + graceful: missing lib or an
  unparseable string → None, never raises (`available()`/`to_sympy()`).
- **`canonical.py`** — `CanonicalMath{latex, srepr, sympy, role, srepr_raw, error,
  expr}` + `from_latex()`. latex2sympy returns a structure-preserving tree, but
  SymPy auto-evaluates on reconstruction, so the canonical IR is the **evaluated
  normal form** — a stable fixpoint that round-trips via `sympy.sympify(srepr)`;
  the structure-preserving parse is kept as `srepr_raw` (provenance). `role` =
  `relation` (an EQ with `=` → `Equality`) vs `expression` (an FO) vs `unparsed`.
- **`backends.py`** — projections off the SAME tree: `sympy_srepr`/`sympy_str`/
  `mathematica`/`smtlib` render today (SymPy's own printers); `PLANNED =
  (lean4, fricas, graphrag)` raise a self-naming `NotImplementedError`. Add a real
  backend by moving its name into `_RENDERERS` — no caller change (all via
  `render(expr, target)` / `render_all`).
- **`annotate.py`** — the FO/EQ integration: `annotate_object(obj)` parses
  `obj.props["latex"]` (types `Formula`/`Equation`) and stores `props["math"]`
  (ir/srepr/srepr_raw/sympy/role/error/renderings/targets_planned); duck-typed so
  it works on a Document or a docgraph node. `annotate_document(doc)` → counts.
- **`operators.py`** — OUR operator/symbol-definition layer (a pre-parse LaTeX
  improvement, like adding a TOC/glossary without changing content): `normalize(
  latex, ops)` applies a user operator-definition map (`{r"\gL": "L"}`) then
  collapses font wrappers on a simple-token arg (`\mathcal{L}`→`L`,
  `\mathbb{R}`→`R`). `from_latex(normalize=True)` runs it before parsing and
  records `normalized`.
- **Empirical (expanded vs unexpanded):** the macro-EXPANDED `latex` parses far
  better than the author's macro source — **5/7 vs 1/7** on a representative
  sample (unknown author macros `\gL`/`\R`/`\vx`/`\dd` just fail). So
  `annotate_object` feeds `props["latex"]` (expanded; falls back to
  `latex_original` only if absent) and records `source`. Our operator layer then
  lifts font-wrapped cases (`\mathbb{R}^n` 0→parses; `\mathcal{L}`→clean `L`).
- **`pdfdrill mathir <pdf|md>`** (`cmd_mathir`, registered) — loads the full
  model, annotates every FO/EQ, and **persists `props["math"]`** via
  `save_model`. Verified live on 2312.11532: **151 FO/EQ, 84 parsed (56%), 12
  relations**, persisted. Reports parse rate + available/planned backends.
- **Honest caveat:** latex2sympy is tuned for answer/competition math, so
  research LaTeX parses imperfectly (it lowercases symbols `R`→`r`, reads `\log`
  as log10, `p(x)` as multiplication; `\to`/set-membership unparsed) — captured
  faithfully (`role="unparsed"`). The fix is OUR operator-definition layer
  (`operators.ops`) growing per corpus, not the parser. NEXT: a first real
  non-SymPy printer (Lean4 or SMT-LIB) off the canonical tree; grow the operator
  map; optional chaining of latex2sympy's own `normalize_latex`. Tests:
  `tests/test_mathlayer.py` (13).

## LaTeX-source citations + cited-subset bibliography (`\cite{}` → Citation, 2026)

The LaTeX-source builder now extracts in-text citations, and `bibsource` builds
THIS paper's bibliography as the **cited subset** of a possibly-larger shared
`.bib` (not all entries):
- **`latex_source.extract_citations` / `extract_citation_occurrences`** — pick
  EVERY `\cite`-family command (BibTeX `\cite/\citep/\citet/…`, biblatex
  `\parencite/\textcite/\autocite/…`, with `[..]` opt-args), ordered keys.
- **`build_source_model`** creates one **Citation** per `\cite{}` key, anchored in
  a `source_cites` stream (a linkable surface), `added_by="latex"`; counted in
  `source_counts["citations"]`.
- **`bibliography.load_bibtex_file(doc, bibtext, restrict=set)`** — `restrict` to
  the cited keys ingests only those entries (a shared db → the paper's biblio),
  and CREATED References now get a `references` surface so they LINK.
- **`cmd_bibsource`** gathers the cited keys from the Citation objects and passes
  `restrict=cited` (no citations → ingest all, backward-compatible), then
  `link_citations`. Verified live on 2606.16905 (`\bibliography{biblio}`, 107-entry
  shared db): rebuilt model → **137 Citations**; bibsource → **104 References (the
  cited subset)** + **137/137 citations linked**. Tests: `tests/test_bibsource.py`
  (extract variants, restrict-to-cited + surface, builder extracts citations).
- **`bibliography.build_bibliography_from_source(doc, dir)`** — the reusable core
  (discover named bib → ingest cited subset → link), shared by `cmd_bibsource` and
  the **citation PASS**: when a model has Citations but NO References, `CitationPass`
  auto-discovers the source bib (`doc.meta["latex_source_dir"]` or `<pdf>.drill/
  texsrc`) and builds the bibliography itself, so `pdfdrill enhance` does it in one
  step. Verified: fresh 2606.16905 model (137 Citations, 0 Refs) → `enhance --only
  citation` → 104 Refs (cited subset) + 137/137 linked. Idempotent (skips when Refs
  exist or cites edges already present). Test: `tests/test_passes.py::test_citation_
  pass_builds_bibliography_from_source`.

## Uniform enhancement pass pipeline (`src/passes/`, `pdfdrill enhance`)

The general form of ChatGPT's linear `IR → math → citation → glossary → … →
Enhanced IR`: an ordered, dependency-aware sequence of idempotent PASSES over the
L5 Document (the IR), decoupled from input format (multi-format acquisition feeds
it) and output backend (any projector consumes the result). A pass mutates the
Document in place and returns a `PassResult`; the driver loads once, runs, saves
once — passes never touch the sidecar/CLI.

- **`base.py`** — `EnhancementPass{name, requires, applies(), run()}`,
  `PassContext{doc, pdf, sidecar, options}`, `PassResult{name, status, changed,
  summary, stats}`, the `REGISTRY` + `register_pass`, `order()` (topological by
  `requires`, deterministic, cycle-safe), `run_pipeline(ctx, only=, skip=)`. A
  pass runs only if every in-pool dependency `ran`; n/a / skipped / errored passes
  don't satisfy deps (dependents skip); one pass failing never aborts the run.
- **`builtin.py`** — the named ordered slots. FULLY WIRED: **frontmatter**
  (→ BibTeX provenance record, below), **math** (`mathlayer.annotate_document`),
  **citation** (`bibliography.link_citations`), **concepts** (glossary+acronym via
  `semantic.concepts.concept_records`). Honest reporting slots: **abstract**, **toc**
  (Section count — links-bearing injection is the open wiring). Planned n/a:
  **index** (requires concepts), **summary** (requires math+citation+concepts) —
  so coverage AND gaps are visible, never silently missing.
- **frontmatter → BibTeX (wired):** the FrontmatterPass treats the **Document IR
  as an input format** for the `semantic/frontend` FrontMatter object — a new
  `formats/docmodel.py` + `cells/frontmatter_docmodel.py` (title/authors/date from
  meta; arXiv id from meta or an arXiv-shaped bibkey; DOI). The pass first
  enriches `doc.meta` from the sidecar's **cached** `arxiv_title`/`arxiv_authors`/
  `source_arxiv_id` (offline — never fetches), runs the cell, concludes via
  `to_bibtex`, and persists `doc.meta['bibtex']` + `['frontmatter']`. Verified
  live on 2312.11532 → `@article{2312.11532, author="YoungJoon Yoo and Jongwon
  Choi", title="Topic-VQ-VAE…", arxiv=2312.11532}`. Tests: `tests/test_frontmatter.py`
  (docmodel cell→bibtex), `tests/test_passes.py` (pass writes bibtex; sidecar
  offline enrichment).
- **`pdfdrill enhance <pdf|md> [--only a,b] [--skip a,b]`** (`cmd_enhance`) — loads
  the model once, runs the pipeline, persists once, prints a per-pass ✓/·/—/✗
  report. Verified live on 2312.11532: 5 ran, 3 changed (citation 12 linked,
  concepts 28, math 84/151), frontmatter/index/summary honestly n/a.
- Adds the passes ChatGPT omits but we want (frontmatter/abstract/summary) and
  keeps multi-format-in / multi-target-out. NEXT: wire frontmatter→BibTeX
  provenance (semantic/frontend), the TOC-inject-with-links pass (reuse
  `booktoc`'s page map), the `\index` pass, and summaries. Tests:
  `tests/test_passes.py` (6).

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

## Sandbox network accessibility

The four outbound routes (`mathpix`/`model`, `snip`, `vision`, `bibfetch`) call
out via urllib through the shared **`src/pdfdrill/net.py`** wrapper. When a host
is blocked/unreachable in a locked-down sandbox (connection-level
`URLError`/`OSError`/timeout, or an egress-proxy `403/407/502` with a block-hint
body), `net.urlopen` raises a typed **`NetworkBlocked`** carrying a clear,
host-named message ("Network access to api.openai.com appears blocked … enable
it in your sandbox/network settings … offline routes need no network") instead
of a stack trace; genuine HTTP statuses from the host (401 auth, 429 rate)
propagate unchanged. The commands surface it gracefully: `mathpix` returns the
message (and `model` then falls back to tesseract `ocr`); `snip`/`vision`/
`bibfetch` abort the batch on the first block and return the message rather than
hammering N items. Tests: `tests/test_net.py`.

## Ask-the-document chat proxy (`retrieve`/`chatlog` + `tools/drillui_chat.py`, 2026-06-17)

A Headroom-style proxy: a question is enriched with pdfdrill context, sent to an
LLM via the keyless `claude -p` fallback, and the Q&A is stored in pdfdrill's own
structures. The conversational proxy stays **external** (never imports pdfdrill);
pdfdrill grows the two primitives it shells out to (additive, read-mostly):
- **`pdfdrill retrieve <pdf> "<q>" [--k N] [--json]`** (`retrieve.py`) — the
  question→context TRANSFORMATION: an ephemeral per-doc IDF index scores the
  drilled units (paragraphs/sections/formula-LaTeX/concepts; reuses
  `classify._strip_latex` so a formula matches on identifiers not `\cmd`s) and
  returns the top-k, each tagged by object id. `build_prompt` wraps them in a
  cite-by-id, answer-only-from-context prompt — the one place the transformation
  lives (the future-SKILL seed). `--json` returns `{question,units,prompt,title,
  subjects}` (subjects from a prior `classify`). Fast DocGraph read path.
- **`pdfdrill chatlog <pdf> --question … --answer … --units id,id [--model M]`** —
  stores the turn in pdfdrill's shapes: a `chat.jsonl` transcript line AND the
  answer as a **KITEM** in the semantic graph (statement = the Q&A, evidence =
  the cited units' spans, grouped under a `Transformation(qid="ask", model=…)`).
  The answer's honesty `status` follows the kitem lattice (≥2 independent cited
  units ⇒ accepted), so a well-grounded answer is first-class + traceable.
- **`tools/drillui_chat.py`** — the external proxy/REPL (stdlib, subprocess-only,
  never imports pdfdrill): per question it shells `pdfdrill retrieve … --json` →
  the enriched prompt → `claude -p … --output-format json` (the same fallback
  trick) → `pdfdrill chatlog …`. One-shot (`-q`) or a REPL with rolling history;
  `--src src` for a dev checkout, `--model`/`--k`/`--no-store` flags.
- **Verified live** on the cspmath monograph: "why no single global metric?" →
  `retrieve` surfaced *Remark 1.5 (Why not one metric…)* + the quality-domain
  definition; `claude -p` answered grounded in 6 cited unit ids (incommensurable
  domains, triangle-inequality failure; geodesic/quasi-metric recovery, Prop
  1.2); stored as an `accepted` kitem. Tests: `tests/test_retrieve.py` (5),
  `tests/test_chat.py` (4). Temporary until the transformation becomes a SKILL.

## Batched CLI delegation transport (amortize the Claude Code startup tax, 2026-06-18)

Measured cost of the CLI delegation path (`detect_runtime()==cli` → `claude -p`):
**one page ≈ 188K tokens / ~$0.87 (opus)** even though the real work (page image +
prompt + answer) is only ~6K tokens — the other ~182K is the Claude Code harness
(system prompt + tool defs) being re-instantiated *per subprocess* (cache_creation
78K + cache_read 103K, every call). One-subprocess-per-page paid that tax N times
(a 22-page doc ≈ 4.1M tokens, ~$19). Levers: `PDFDRILL_DELEGATE_MODEL=haiku`
(~$0.14/page, 6.4× cheaper) and the **sandbox** path (no subprocess — the agent
reads each page inline in its existing session, ~5K tokens/page, no $).

**Fix — batched transport (`llm_delegate._run_cli_all`/`_run_cli_batch`).** In the
CLI runtime, `delegate_batch` now groups same-kind IMAGE tasks (`vision`/`page_md`/
`eq_ocr`) and sends each chunk of ≤`_CLI_BATCH_MAX` (10) pages in ONE `claude -p`
call — all page paths in a single prompt, the model returning one JSON object
mapping each page to its result, paid the harness tax ONCE per chunk. So 23 pages
→ 3 calls, not 23 (~3×190K instead of 23×188K). Robustness: pages are keyed by
SHORT ordinal ids (`img1`,`img2`,…) mapped back by position — a model echoes those
reliably, where repeating 32-char hex task_ids as JSON keys failed (measured 0/3 →
3/3 after the switch); `_parse_batch_object` tolerates leading prose; any page the
batch drops is retried as a single call; a 1-page chunk uses the plain path. Text
tasks (bibtex/links) still run one-by-one. **`_MATHPIX_TIP`** (and code comments at
the transport) note that **MathPix does page→LaTeX OCR natively, much faster and
cheaper than per-page LLM OCR — https://mathpix.com/pricing/all** — surfaced in the
`visionocr`/`remath` prose. Tests: `tests/test_cli_batch.py` (one-call batching,
chunking at 10, missing-id single retry, 1-task-not-batched).

## Keyless agent-delegated equation OCR — `pdfdrill visionocr` + the math-bearing gate (2026-06-18)

The silent failure: on a math PDF with no MathPix key, `cmd_model` falls back to
tesseract, which **cannot type display equations** (`EquationProcessor` finds 0),
yet `model` reported a clean build — 100% of the mathematics dropped with no
signal. Two additive fixes (keyless, reuse existing layers, no new deps):

- **The gate (`mathqc.is_math_bearing` + `cmd_model`).** `is_math_bearing(pdf, sc)`
  returns `(True, reason)` when ANY cheap/offline signal fires: math fonts
  (`font_image_layers` CMEX/CMMI/CMSY/MSAM/MSBM/Symbol…), an `equation.*` named
  dest (`pdfinfo -dests`), or a cached md-display-math / geometry-eqnum signal.
  After a build, if the lines.json `source` is `tesseract` AND 0 Equations AND
  `is_math_bearing`, `cmd_model` sets the **`NEEDS_VISION_OCR`** fact and returns
  an INSTRUCTING prose (not "success"): runtime `cli`/`sandbox` → "run `pdfdrill
  visionocr`"; runtime `none` → a WARNING that the math was not captured. The
  MathPix path and non-math docs are byte-for-byte unchanged (gate keys on
  source==tesseract + 0 eq + math-bearing). `Sidecar.remove_fact` added (the
  `facts` property returns a copy, so `.discard` never persisted).
- **`pdfdrill visionocr <pdf>` (`cmd_visionocr`).** The keyless route to
  first-class Equation nodes, mirroring `candidates`/`ingest`. Default: rasterize
  every page (≥200 DPI) and delegate each to the running Claude agent via
  `llm_delegate` (new **`eq_ocr`** task kind + `openai_vision.EQ_OCR_PROMPT`) —
  one request per page, visible in `pdfdrill llm --show`, manifest written to the
  sidecar. The agent returns a JSON array of `{page, number, latex, kind}`
  (LaTeX with `_{}`/`^{}`/`\frac` preserved, `[]` for a math-free page, never
  fabricated; `llm_delegate._parse_eq_ocr` is tolerant). `--ingest <json>` folds a
  supplied records file directly. `_fold_eq_records_into_lines_json` appends
  `equation` + paired `equation_number` lines (each number at its equation's
  `top_left_y` so `EquationProcessor._match_equation_numbers` pairs them by
  page+y), **preserving the tesseract prose**, then rebuilds `model`+`eqnums` and
  clears `NEEDS_VISION_OCR`. CLI answers synchronously; the sandbox defers and a
  re-run ingests. `doctor` now lists the three math-OCR routes (MathPix /
  delegated visionocr / tesseract-prose-only) in preference order. SKILL carries
  the DECISION RULE (math-bearing + no key + agent ⇒ visionocr) + ANTI-PATTERN
  (never present a 0-equation tesseract model as complete; don't hand-roll a
  flattened pseudo-lines.json). Distinct from `remath` (whole-page Markdown
  rebuild); `visionocr` is surgical — keep prose, inject structured equations.
  Tests: `tests/test_visionocr.py` (prompt+parser, fold→refnum, gate
  sets/​warns/​skips, full sandbox per-page round-trip).

## drillui terminal trio (`tools/drillui_*`, browser ask-the-document UI, 2026-06-18)

Three co-located files in `tools/` (full guide: `tools/DRILLUI.md`), distinct
roles — the shared `drillui_` prefix caused real confusion:
- **`drillui_chat.py`** — the BRAIN (Python REPL over one doc: `retrieve` →
  `claude -p` → `chatlog`; also runs pdfdrill subcommands on the doc by name).
  Self-locates pdfdrill from `../src`.
- **`drillui_bridge.ts`** — the BRIDGE (Bun): spawns ONE `drillui_chat.py <doc>`
  per WebSocket, pipes stdin/stdout, serves the HTML + `/artifact` (files
  pdfdrill writes) + `/open` (host browser). Pure plumbing. Resolves the .py as
  its sibling → **zero-config**: `bun tools/drillui_bridge.ts data/x.pdf`.
- **`drillui_term.html`** — the UI (xterm.js terminal + retrieval rail + Outputs
  panel). Owns the visible prompt.

**The command model (fixes "open url called the LLM"):** the browser decides
FIRST — `open <url|file>` / `lhelp` / `^L` are LOCAL (handled in
`drillui_term.html::handleLocal`, a new window via `/artifact` or the URL
directly, NEVER forwarded). Everything else goes to the Python REPL, where a
known pdfdrill command name runs on the doc and anything else is a question.
`promptLoop` calls `handleLocal` BEFORE `ws.send`, so `open` never reaches the
LLM. **Artifact paths resolve doc-relative:** pdfdrill prints report paths
relative to the DOC's folder (`1906.02691.pdf.drill/formula-report.html` for a
doc in `data/`), so the bridge resolves `/artifact` against BOTH its cwd AND the
document's directory (`ART_ROOTS`, existing-file-wins) — fixing the report
"file not found" 404. `open <url>` also always drops a one-click link into the
Outputs panel (URL or file), so a blocked popup still has a real-click fallback.
Test: `tools/test_drillui_bridge.ts` (spawns the real bridge: page serves,
the open-is-local contract holds, `/artifact` serves-under-root + refuses
traversal, `/open` refused when disabled, and a WS `status` round-trip runs on
the doc). Live-verified end-to-end: a real question → grounded retrieval →
`claude -p` → cited answer back in the terminal.

## MCP server — drill results as clickable resources (`tools/pdfdrill_mcp.py`, 2026-06-22)

The "result link doesn't open in chat" fix. drillui's `/artifact?path=…` is a
localhost **bridge** route; opened inside a hosted client (claude.ai) it resolves
against the client host and 404s. MCP is the reachable channel: a tool result
carries the produced files as `resource_link` items + embedded `resource` content,
and the client fetches them via `resources/read` over the MCP connection — no
port, no dead link.
- **`tools/pdfdrill_mcp.py`** — pure-stdlib stdio MCP server (JSON-RPC 2.0 over
  stdin/stdout, NO `mcp` SDK; stdout = protocol, logs → stderr). Tools `drill`
  (shallow|standard|deep via drillbatch), `md`, `tiddlers`, `report`; each runs
  pdfdrill on the resolved doc and returns a text summary + the files as
  resources (text files ≤256 KB embedded inline, larger/binary linked).
  Implements `initialize`/`tools/list`/`tools/call`/`resources/list`/
  `resources/read`. Imports `drillbatch` for `resolve`/`pdfdrill_base`/`run_cmd`/
  `collect_outputs`; self-locates pdfdrill via `REPO_ROOT/src`.
- **`tools/drillbatch.py`** — batch driver (shallow→standard→deep ladder over a
  URL list), `collect_outputs` (the `<pdf>.drill/` openable artifacts), an HTML
  card report, and `--list-outputs` (print every produced file path). Its card
  report links outputs with **`file://` URIs** (open locally) — NOT the
  bridge-only `/artifact` route that 404s in a hosted viewer (the dead-link fix).
- **`tools/MCP.md`** — the guide (claude_desktop_config.json block; local-stdio
  vs the web client needing an HTTP/SSE remote connector).
- **Verified end-to-end in this repo** via a stdlib stdio client:
  `initialize` (proto 2025-06-18) → `tools/list` (drill/md/tiddlers/report) →
  `tools/call md` on a local doc → text + resource_link + embedded 152 KB md →
  `resources/list` → `resources/read` returns the file. Pure-stdlib, so no test
  dep; not in `tests/` (it shells the CLI). Honest limit: stdio fits Claude
  Desktop/Code; the web client uses the HTTP transport below.
- **`tools/pdfdrill_mcp_http.py`** — the **Streamable HTTP** transport (the 2025
  successor to HTTP+SSE) for a claude.ai web custom connector. A SEPARATE entry
  point that **imports `pdfdrill_mcp`** and reuses its `TOOLS`/`RESOURCES` +
  dispatch verbatim (the stdio server the user runs daily is untouched). Pure
  stdlib (`http.server` + threading). One endpoint `/mcp`: POST a JSON-RPC msg →
  response as an SSE `message` event (or `application/json`); GET → heartbeat SSE;
  session id minted on `initialize` (`Mcp-Session-Id`); notifications → 202.
  Optional bearer auth (`--token`/`$PDFDRILL_MCP_TOKEN`), CORS preflight handled.
  TLS terminates at the front (sensorcloud HTTPS / a reverse proxy →
  `http://127.0.0.1:8765`); add a claude.ai connector at `https://<host>/mcp`.
  Verified via a stdlib urllib client: initialize (session via SSE) → tools/list
  → tools/call md → text+resource_link+embedded 152 KB → resources/read; tokenless
  POST → 401; OPTIONS → 204. Guide: `tools/MCP.md`.

## arXiv builds from LaTeX source by default — no slow tesseract OCR (2026-06-20)

`pdfdrill model` on an arXiv doc with no lines.json fell back to **keyless
tesseract OCR of every page** (~60 s for a real paper, and lossy). Working
locally, the FREE e-print LaTeX is the right route. `cmd_model` now, when no
lines.json materialises and the doc is arXiv (`_arxiv_id_for`), builds via
`_build_arxiv_source_model` → `latex_source.build_source_model` (download the
cached `.tgz`, parse) BEFORE the tesseract fallback. Verified: 1906.02691 →
**0.28 s, 938 objects** (444 Formula, 260 Paragraph, 92 Equation, 65 Section, 3
Table, 3 Algorithm) vs ~60 s OCR; 2305.04710 → 0.12 s. Tesseract remains only the
last resort for a NON-arXiv doc with no source. `mathpix --force` still gets the
paid OCR/CDN route. This also realises "a `tiddlers` command needs the model
(from LaTeX) first" — the auto-chained `model` is now the fast source build.

**drillui typo/singular tolerance:** a lone word that closely matches a command
(`tiddler` → `tiddlers`, difflib cutoff 0.8) runs the command instead of being
sent to the LLM as a question (which wasted a slow call and answered nothing).

## LaTeX-source projection parity — prose Paragraphs + inline Formulas (2026-06-20)

The LaTeX-source builder (`latex_source.build_source_model`, used by `latexbook`)
emitted only a SKELETON (Section/Equation/graphic/Algorithm) — no Paragraph, no
inline Formula — so its TiddlyWiki projection had a totally different (far
smaller) tiddler count than the MathPix path (which emits the full 15 object
types incl. Page/Paragraph/Formula). Measured on 2305.04710: source-only 32
tiddlers vs MathPix/OCR 48 (and a real MathPix model is far denser). Closed the
biggest gaps (the user chose "extend the builder directly", not route-via-md):
- `build_source_model` now interleaves, BY SOURCE POSITION, the structural items
  with **prose Paragraphs** (the text between sectioning/float/math blocks;
  `_prose_chunks` blanks structural blocks to equal-length whitespace so prose
  splits at the right offsets) and **inline Formula objects** for each `$…$` /
  `\(…\)`. `extract_display_equations` keeps `pos` now (was popped) so equations
  order correctly too. Section→Paragraph parent linkage tracked.
- **Both LaTeX forms in parallel** (the requirement): every inline Formula (and
  display Equation) stores `latex` = macro-EXPANDED (what TiddlyWiki `<$latex>`/
  KaTeX renders) AND `latex_original` = the author's un-expanded macro source.
  The projector already renders `latex` and keeps `latex_original`.
- Each inline formula is transcluded into its paragraph via a materialized
  `{{<bibkey>_FO{k}||FO}}` marker whose title matches the projector's
  deterministic FO numbering (flow order) — no FOX needed (FOX doesn't run on a
  no-mathpix-surface paragraph), and `tiddler_integrity` confirms 0 dangling /
  0 orphan. Verified on 2305.04710: 32 → 107 tiddlers (35 Paragraph, 40 Formula,
  9 Section, 5 Equation, 2 Table), all 40 FO markers resolve. Tests:
  `tests/test_latex_prose.py`. Still source-only-absent (later phases): Page
  (needs compile/geometry), Citation/Abstract/ListItem/Footnote/Reference.

## Download registry (`pdfdrill-downloads.json`) — URL-keyed, BLAKE3, collision-safe (2026-06-26)

The user's model: the **URL is the identity** (users supply URLs, not filenames),
logged in ONE JSON file. `src/pdfdrill/download_registry.py` writes
`<download_dir>/pdfdrill-downloads.json` — `{url: {filename, hash, algo, bytes,
downloaded_at}}` — recording every generic-URL download's complete URL → local
filename + **BLAKE3** content hash (`algo` records `blake3` if the package is
installed, else `sha256`, so the log never lies; `pip install blake3` upgrades it).
Two payoffs in `sources.resolve_input`: (1) re-resolving a URL is a registry lookup
→ the same local file (true cache by URL, not by guessed filename); (2) two
DIFFERENT papers sharing a basename (`host1/fulltext.pdf` vs `host2/fulltext.pdf`)
get DISTINCT files — the collider is renamed `<stem>-<hash8>.pdf` (`_place_download`)
instead of clobbering, while IDENTICAL content (same hash) de-dups to one file.
This fixes the 172-URL batch loss (106 entries → 100 files, `fulltext.pdf` ×N
overwriting). arXiv stays on its clean canonical `<id>.pdf` (ids already unique).
A download streams to a `.download-tmp` first so it is hashed before placement.
Tests: `tests/test_sources.py::test_url_download_registry_logs_and_survives_collisions`
(registry log, hash-suffixed collider, content de-dup, URL cache hit).

## Config FILE + stable download/drill location + findable artifacts (2026-06-19)

Driven by drillui usage feedback (downloads landing in cwd/`/tmp`; re-drilling;
`.md`/`.json` not clickable; can't find the `.md`):
- **`src/pdfdrill/config.py`** — a config FILE (not CLI flags): `$PDFDRILL_CONFIG`
  → `~/.config/pdfdrill/config.json` → `~/.pdfdrill.json`. Key `download_dir`
  (default `~/Downloads` if present, else cwd). `sources.resolve_input` now
  defaults its download dir to `config.download_dir()` instead of cwd — so URL/
  arXiv downloads AND each doc's `<name>.drill` sidecar land in one **stable**
  place. **`pdfdrill config` / `--init` / `--json` / `--download-dir`**
  (`cmd_config`) shows/creates it. Stable location ⇒ a doc drilled once is
  REUSED (resolve_input reuses the cached PDF; `model`/etc skip when built) —
  "drill once, never again". (`/tmp/tmp*` are temp render dirs from killed runs;
  `vocn*` is not pdfdrill.) Tests: `tests/test_config.py`.
- **`pdfdrill md` now writes a findable, named file** `<bibkey>.md` in the drill
  folder (alongside the `md.md` blob that `fetch` reads) and **reports its path**
  in every return (`_write_named_md`) — no `fetch`/`find` needed.
- **`md` PREFERS the MathPix `<stem>.md` when it exists (2026-06-29).** `cmd_md`
  only served MathPix on a `needs_ocr` (scanned) doc; a born-digital doc always
  took the text-layer ENGINE path even when the user had run `mathpix`. On an old
  report (Berkeley CSD-91-628) that engine flagged nearly every short/2-column
  line as a heading — `## ` on 570/742 lines (+ `(cid:3)` glyph artifacts). Fix:
  `cmd_md` now serves the MathPix `<stem>.md` (`_serve_mathpix_md(scanned=False)`)
  before the engine whenever it exists (whole-doc; page ranges still use the
  engine) — the user ran MathPix, so its markdown is preferred. CSD-91-628: 570 →
  **32** `#` lines (real headings only). The text-layer engine's over-eager
  heading detection on such docs is the deeper, unfixed cause (left as-is — minimal
  change per the user). Tests: `tests/test_tilde_and_md.py`
  (`test_md_prefers_mathpix_md_over_text_layer_engine`).
- **drillui Outputs panel links `.md`/`.json`/`.txt`/`.tex`** too (was html/svg/
  pdf only): `scanArtifacts` regex + bridge MIME extended; the bridge also serves
  the **download dir** (`ART_ROOTS` += config `download_dir`) so `~/Downloads/
  *.drill/*` links resolve. So `report`, `md`, `llmtext`, `tables`, `tiddlers`
  outputs all become clickable.
- **`pdfdrill artifacts <pdf> [--all]`** (`cmd_artifacts`/`_list_artifacts`) lists
  the drill folder's openable OUTPUTS (report.html, `<bibkey>.md`, tiddlers/llm
  `*.json`/`*.txt`, rendered `svg/`) with paths — **the giant model/ir JSON is
  hidden unless `--all`** (>15 MB or a known internal name). **`status` appends
  the same listing**, so running `status` in drillui fills the Outputs panel.
- **drillui `add` reuses, never re-drills** (model is idempotent; dedup if already
  in context) and writes the session combined store to the config download dir
  (via `pdfdrill config --download-dir`), not a scratch cwd.

## Multi-document chat — `pdfdrill combine` → one store, retrieve across all (2026-06-19)

drillui is one-doc-per-session (`drillui_chat.py <doc>`; `cmd_retrieve` over one
model). For multi-document context the chosen design is **merge into one store**:
- **`pdfdrill combine <doc> <doc> … --out FILE`** (`cmd_combine`): each input must
  already be drilled (`model`); it pools every retrievable object (prose/math/
  concepts — `_COMBINE_TYPES`) into one JSON store, namespacing each id as
  `<bibkey>:<id>` so an answer cites which paper. Writes `{is_combined, meta,
  objects}` to `--out` (e.g. `heim.docpack`). Unbuilt inputs are skipped + warned.
- **`cmd_retrieve` accepts a combined store** (`_load_combined_store` detects
  `is_combined`): it retrieves across the pooled nodes (lightweight
  SimpleNamespace nodes — retrieve only needs .type/.id/.props), citing
  `bibkey:id`. So `pdfdrill retrieve heim.docpack "…"` and
  `bun tools/drillui_bridge.ts heim.docpack` chat over all docs at once.
  `cmd_chatlog` already works on any path (transcript + kitem by unit id), so
  storing multi-doc turns needs no change.
The combined store records its member **source paths** (`meta["sources"]`), so a
per-doc metadata command run on the store fans out: **`pdfdrill bibtex
<combined>`** emits a real `@article{…}` for each member (the multi-doc/drillui
case where bare `bibtex` previously hit the store and returned `@misc{unknown}`).
drillui also has an interactive **`add <pdf|url|arxiv-id>`** that drills + re-merges
into a session store live (one repeatable verb; `combine` is its CLI/batch form).
Verified: combine data/1906.02691 + data/2312.11532 → 985 units; "variational
autoencoder" → 1906 units, "diffusion manifold" → the other doc. Honest limit:
the store holds retrievable text only (no streams), so it's for chat/retrieve —
projectors/transclusion still run per original doc. Tests: `tests/test_combine.py`.

## `bibtex` augments from arXiv free metadata (no more `@misc{unknown2023}`, 2026-06-19)

`pdfdrill bibtex` derived the record from the **embedded PDF Info dict only**
(`derive_bibtex(pdfinfo)`), which for an arXiv PDF (and most LaTeX/scanned PDFs)
has no title/author — yielding `@misc{unknown2023}` (`unknown` = no author,
`2023` = the file's creation-date, `misc` = no DOI/arXiv). It never used the
drilled content. Fix (`_augment_bibtex`): after the pdfinfo derive, pull the
**free arXiv abs-page metadata** (title/authors via `sources.fetch_arxiv_metadata`
— cached from a prior `abstract`, else fetched, graceful when blocked) when the
input is an arXiv id/URL (`source_arxiv_id` in the sidecar), set
`entry_type=article` + `arxiv_id`/`url` + year from the id (`_arxiv_year`), and
recompute the citekey; secondary offline fallback = the model's `doc.meta["title"]`.
The placeholder cache is never re-served (`_is_placeholder_bib`). When STILL a
placeholder (non-arXiv, empty metadata, no model) it appends a warning naming the
deep-drill steps (`abstract`/`model`+`bibsource`/`bibfetch`) — answering "bibtex
after only info/size is useless". Verified: arXiv 2305.04710 →
`@article{korfhage2023, …ElasticHash…, author={Korfhage and Mühling and
Freisleben}, year=2023}`. Tests: `tests/test_bibtex.py`.

## Inline-formula de-duplication on the LaTeX-source path (2026-06-26)

The symbol `$f$` used 20× in a paper became **20 separate `_FO` tiddlers** — a
duplication impossible in the modular design. Root cause: the MathPix module
`docmodel/modules/formula.py` (`FormulaProcessor`) ALREADY dedups by content
(`self._dedupe`: one Formula object + many realizations), but the LaTeX-source
builder `latex_source.build_source_model` is a MONOLITH that re-implemented
inline-math extraction WITHOUT that dedup — one Formula object per occurrence.
Fixed by content-keying (`formula_titles[expanded-latex]`) so identical inline
math maps to ONE `_FO` tiddler transcluded everywhere, matching LATW's
`FormulaScanner.processMathExpressions`/`getKeyForFormula` and the MathPix
module. Verified on arXiv 2110.11150 (source-built): **465 → 273 Formula
objects**, `f` 20→1, `f_0` 13→1, `L` 12→1; `tiddler_integrity` 0 dangling-FO /
0 orphan-synthetic. Test: `tests/test_latexbook.py::
test_build_source_model_dedupes_repeated_inline_formula` (distinct-vs-total
assertion — the net a per-object explosion needs, since 0-orphan integrity alone
won't catch it). The broader lesson (the two build paths duplicating logic the
modules own) is the **modularity audit vs the LATW TypeScript scanners**:
`docs/superpowers/specs/2026-06-26-modularity-audit-vs-latw.md` (PLAN — extract
shared scanners so the source path is a pipeline, not a monolith; a both-paths
parity test matrix; named gaps incl. span-aware tables + margin notes on the
source path).

## `_FOX_` synthetic formula tiddlers — content-addressed inline math (reference)

A `<bibkey>_FOX_<sha1[:10]>` tiddler (tag `formula synthetic`) is NOT a defect or
a new feature — it is the projector's catch for **inline math that wraps across
an OCR line boundary** (`\(` on one line, `\)` on the next), which the per-line
`FormulaProcessor` can't number. `tiddlywiki._substitute_residual_inline_math`
finds these residual spans during paragraph transclusion and mints ONE
**content-addressed** tiddler per distinct LaTeX body (sha1 of the canonicalized
LaTeX), reused everywhere that body appears. It is hash-titled (not `_FO0001`
numbered) on purpose: discovered late (text pass, no stable global order) and
**deduped by content** — the same expression always maps to the same FOX title,
which is exactly what makes it a durable transclusion handle. Resolution is a
LOOKUP, never memorization: the FOX tiddler carries the math in its `latex` field
(and now its `caption`), so `{{…_FOX_<hash>||FO}}` resolves by reading that
tiddler. As of 2026-06-19 every formula tiddler (`_FO` and `_FOX`) also sets
`caption` = the LaTeX, so an opaque hash title is self-describing in any listing
/ for an LLM building a title→latex index. Test: `tests/test_docops.py`.

## Document title → `doc.meta["title"]` + tiddler `caption` (2026-06-19)

Tiddler titles ARE bibkey-prefixed (`<bibkey>_PARA_0001`, `_H1`, `_EQ0001`, …)
and the root/document tiddler's title IS the bibkey — which defaults to the
**filename stem** when no `--bibkey` is given, so a batch (`folder`) over messy
filenames yields filename-based tiddler titles (and, after a TiddlyWiki *node*
save, filename-based `<title>.md`/`.md.meta` files — those sidecars are written
by TiddlyWiki, not pdfdrill). Two fixes so the human title is preserved
properly:
- **The PDF path never captured the document title.** `page._extract_title`
  (called from `ingest_lines_json`) now promotes the leading `type:"title"`
  line(s) — resolving MathPix's parent/`children_ids` nesting, skipping a bare
  "Abstract" — into `doc.meta["title"]` (only if unset; the tesseract path has no
  title line → stays empty). This also feeds scikgtex / llm_compact YAML / etc.
- **The document tiddler now carries the human title in `caption`** (TITLE stays
  the bibkey id; heading + `caption` use the title, with the bibkey shown as a
  sub-line). Section tiddlers already put their heading in `caption`. So: `title`
  = stable bibkey id, `caption` = human title — exactly the split needed for a
  node save. To get a clean bibkey instead of a messy stem, pass `--bibkey`
  (single doc); `folder` batch still uses each file's stem. Tests:
  `tests/test_docops.py` (title capture; root title=bibkey/caption=title;
  no-title fallback).

## Keyless arXiv math recovery — `latex` CREATES gold equations; `report` explains an empty result (2026-06-19)

Symptom (arXiv 2305.04710, keyless): `report` → "0 inline formulas + 0 display
equations" with no hint why, even after the user ran `latex` as the `mathpix`
skip-message suggested. Two causes, both fixed:
- **`cmd_latex` only OVERLAID gold equations onto existing Equation slots** (sim
  ≥0.55). A tesseract base has 0 such slots, so every gold equation was
  "unmatched" → nothing rendered. Fix: when there is **no equation scaffold**
  (`scaffold==0`, the keyless case), `latex` now **creates** first-class
  `Equation` objects from the author's gold display equations (`added_by="latex"`,
  expanded+original LaTeX, refnum from `\label`), clears `NEEDS_VISION_OCR`, and
  reports "CREATED N Equation object(s)". Idempotent (force drops `added_by==latex`
  eqs first; overlay skips them). The MathPix path is unchanged (scaffold>0 →
  overlay only, no duplicates). Verified: 2305.04710 → `latex --force` creates 5
  → `report` shows 5 display equations.
- **`report` was silent on an empty result.** Now when `inline==0 && eqs==0` AND
  the doc is math-bearing (or `NEEDS_VISION_OCR` set), it appends WHY (keyless
  tesseract can't type equations) + the recovery routes, arXiv-gold first:
  `pdfdrill latex` (free) / `visionocr` (keyless LLM) / `mathpix --force` (paid).

Honest limit: the gold-source path objectifies DISPLAY equations only; inline
formulas stay 0 on a keyless base (they live in prose, not separately extracted).
For full inline+display fidelity use `mathpix --force` or `visionocr`.

## Stale-model rebuild — projectors/read path honor a newer lines.json (2026-06-18)

Bug (arXiv 2305.04710 "report shows no formulas/tables/images"): the model was
built from a lines.json, then a NEWER lines.json was written (MathPix/OCR re-run,
or a hand-built pseudo-lines.json with the math), but `report`/`tiddlers`/`compare`
and the fast read-path commands only rebuilt the model when it was **absent** —
never when it was merely **stale** — so they silently served the old, math-less
model. Root-caused by mtime: lines.json 17:59 > model 17:56; the lines.json
actually contained 5 `math` + 4 `diagram` + 2 `table` lines that the stale model
lacked. `cmd_model` already rebuilt on stale, but nothing else called it.

Fix: `_stale_or_absent(sc, model_path, lines_path)` (missing OR lines.json newer)
replaces the bare `if not MODEL_BUILT or not model_path.exists()` guard at all 18
projector sites, and `_fresh_docgraph(pdf, sc, model_path)` (rebuild-if-stale then
`load_docgraph`) replaces the 6 read-path loaders (llmtext/mathcheck/classify/
retrieve/identifiers/booktoc) — so a newer lines.json is never silently ignored.
Offline-safe (cmd_model only auto-runs offline steps). Verified: touch the
lines.json, `pdfdrill report` (no --force) auto-rebuilds → 5 equations / 40
formulas / 4 diagrams. Tests: full suite green (test_chat fixture now sets the
MODEL_BUILT fact, as a real build does).

## Formula QC — `pdfdrill mathcheck` (flag FLATTENED formulas, 2026-06-18)

A keyless/visual reconstruction that linearises a 2-D equation produces many
formula tiddlers that are NOT valid LaTeX (observed live: an LLM rasterized each
page and hand-rolled a pseudo-`lines.json` → 65 formula tiddlers, but each was a
flattened transcription — `M = m a (F + j ) (B65)` with the subscripts `m_a`/
`j_0` dropped onto neighbouring lines and the equation number `(B65)` mashed
in). Such a "formula" won't render in KaTeX or transclude. `src/pdfdrill/
mathqc.py` `is_flattened(latex)` detects them **conservatively** — any LaTeX
markup (`\ { } _ ^`) ⇒ structured math, never flagged (so real MathPix LaTeX
like `\mathbf{x}^{(1)}` / `p(\mathbf{a}\mid\mathbf{b})` is clean); only a
markup-free string is examined (spans visual lines / inline `(N)` eq-number /
many detached single letters). `audit_formulas(nodes)` → {total, flattened,
ratio, samples}. **`pdfdrill mathcheck <pdf>`** (fast DocGraph read path) reports
the count + examples and, when any are flagged, steers to `pdfdrill remath` (the
LaTeX-demanding rebuild). The `MATHPIX_MD_PROMPT` was also hardened with an
explicit anti-linearisation rule (preserve `_{}`/`^{}`/`\frac`; the `M = m a (F +
j ) (B65)` → `M = m_a (F + j_0) \tag{B65}` worked example). Verified: 1906.02691
(MathPix model) → 372 formulas, 0 flattened. Tests: `tests/test_mathqc.py` (the
reported case flagged; clean LaTeX not flagged; audit counts/samples).

## Keyless MathPix replacement — `pdfdrill remath` (rebuild the LaTeX-math .md, 2026-06-18)

tesseract (the keyless OCR fallback) yields a plain-text layer with **no LaTeX**,
so equations never become `{{…||FO}}` transclusions and the whole transclusion
model collapses. `pdfdrill remath <pdf> [--pages N|N-M|all]` is the fix: it
renders the pages (`pdf_reading.rasterize`) and **delegates each page to the
Claude agent** (the same `llm_delegate` handshake — CLI `claude -p`, or the
sandbox deferred request/response) with **`openai_vision.MATHPIX_MD_PROMPT`** —
the "stand in for MathPix on this page" prompt: re-emit MathPix-quality Markdown
(inline `\(..\)`, display `$$..$$` on their own lines, headings/lists/tables,
faithful, no summarising) **or output exactly `PDFDRILL_CANNOT_RECONSTRUCT`** and
nothing else (a declined page is skipped + counted — math is never guessed). The
result is written to `<key>.mathpix.md`; `pdfdrill markdown <key>.mathpix.md`
then builds a model with **real Equation objects → transclusion restored**.
Adds the `page_md` task kind to `llm_delegate` (`_parse_page_md` → {markdown,
given_up}). Tests: `tests/test_remath.py` (prompt demands LaTeX + names the
give-up token; give-up/markdown parsing; full sandbox per-page round-trip with
one page declined; graceful no-agent). The SKILL routing block points keyless-
math docs here (to restore transclusion) vs `rasterize`+read (one-off visual).

## Keyless LLM-delegation fallback (`src/pdfdrill/llm_delegate.py`, 2026-06-17)

The two prompt-driven providers (`openai_vision`, `perplexity_client`) need a
hosted chat-LLM, but pdfdrill is *almost always run by a Claude agent* — under
Claude Code CLI or in the Claude.ai sandbox. So when no API key is present,
route the sub-task to **that Claude**, handed pdfdrill's OWN prompts
(`DEFAULT_PROMPT`/`GRAPH_TIKZ_PROMPT`/chem prompt, `bibtex_prompt`/`links_prompt`)
— the prompt IS the carried knowledge. tesseract/pix2tex are NOT fallbacks here
(they can't consume a prompt; full-page OCR already degrades to tesseract).
- **One task contract, two transports** chosen by `detect_runtime()` (CLI wins):
  **CLI** → synchronous `claude -p <prompt> --output-format json --allowedTools
  Read` (vision) / `"WebSearch WebFetch"` (bibtex), parsing the `.result`
  envelope back into the provider's exact return shape; **SANDBOX** (`IS_SANDBOX`,
  no binary) → a DEFERRED file handshake (`<drill>/llm/<task_id>.req.json` → the
  agent writes `.resp.json` → re-run ingests). `task_id` is a blake2b content
  hash (cache-friendly, fixpoint-stable). Overrides: `PDFDRILL_DELEGATE`
  (cli|sandbox|none), `PDFDRILL_CLAUDE_BIN`, `PDFDRILL_DELEGATE_MODEL`.
- **Wired into `cmd_vision`**: the hard no-key guard now detects the runtime; if
  `NONE` it keeps the old "set OPENAI_API_KEY" message, else
  `_vision_via_delegate` downloads each CDN crop locally, delegates, and attaches
  `provenance="openai"` realizations byte-identically to the API loop (incl. the
  chemistry `latex_code` adoption). The API path is untouched. `cmd_bibfetch`
  delegation is proven by the module/test but not yet wired (additive follow-up).
- **`pdfdrill llm <pdf> [--show|--runtime]`** — driver/inspector: detected
  runtime + pending count; `--show` dumps open requests for the sandbox agent.
- **Capability proven on the CLI (not just the sandbox):**
  `tools/claude_capability_test.sh` grades a target model on pdfdrill's REAL
  prompts — VERIFIED here (default model, 4/4): the vision output is a valid
  `tikz-cd` that **recompiles** (more than OCR), and the BibTeX is
  **web-searched** correct (recovered the hidden Vaswani co-authors + pages
  5998–6008). Tests: `tests/test_llm_delegate.py` (7, incl. a full sandbox
  round-trip), `tests/test_vision.py` (delegation round-trip). Additive; all
  test files green; 81 commands in sync.

## Known-host URL inputs + arXiv free routes (`src/pdfdrill/sources.py`)

Every command's `<pdf>` argument may now be an **https URL from a known host**,
not just a local path. `_pdf()` (the single arg-resolution chokepoint in
`cli.py`) calls `sources.resolve_input(arg)`: a local file passes through
unchanged; a known-host URL is **downloaded once (cached)** to a local PDF so the
whole toolchain runs on it. `KNOWN_HOSTS` maps a host → kind (`arxiv` today;
extend per host).

**Bare ids resolve too (skill gotcha fix).** `_pdf` routes a bare arXiv id
(`pdfdrill latex 2510.11170v2`) — not just a URL — through `resolve_input`, so it
no longer fails with `Not found`. `bare_arxiv_id` is a strict **fullmatch** (the
whole arg is the id, optional `arXiv:`/`.pdf`), so an id merely *embedded* in a
missing local path (`data/2312.11532.pdf`) is NOT hijacked into a download, and a
**real local file always wins** (checked first). One consequence worth knowing for
scripts/skills: every command accepts the same URL/id and resolves to the same
cached `<id>.pdf`, so there is no need to `ls *.pdf` to discover the downloaded
name — pass the URL/id to `size`/`model`/`tiddlers`/… directly.

**State-machine ordering on arXiv.** Because `mathpix` skips by default for arXiv,
the MathPix-**rich** path is `pdfdrill mathpix <id> --force` → `model` → `latex`
→ `tiddlers` (force writes the detailed `lines.json`; `model` auto-rebuilds when
`lines.json` is newer). Running `latex` first instead builds the keyless-OCR
skeleton (pages/paragraphs/lists; the gold equations don't match OCR slots).

**arXiv is the money-saver.** Given an `arxiv.org` argument (or a bare id like
`2510.11170v2`) we DON'T pay MathPix at all — `parse_arxiv_id` accepts every
spelling (`/abs/`, `/pdf/`, `/e-print/`, `arXiv:…`, bare, old-style
`math/0309136`), `arxiv_urls` builds the abs/pdf/e-print URLs, and the id is
recorded in the sidecar (`source_arxiv_id`) so downstream commands take the free
routes:

- **Abstract for free** — `cmd_abstract` tries the arXiv abs page FIRST (the
  cheapest authoritative source: no MathPix, no text layer needed).
  `parse_arxiv_abs_html` lifts title/authors/abstract/primary-category from the
  page (pure, unit-tested). Verified live: `pdfdrill abstract
  https://arxiv.org/abs/2510.11170v2` → the EAGer abstract `via arxiv-abs-page`.
- **Gold LaTeX instead of MathPix** — `cmd_mathpix` **skips the paid upload by
  default** for an arXiv input and prints the free-route guidance (so `model`
  falls back to keyless tesseract for page structure); `--force` overrides.
  `cmd_latex` **auto-downloads the e-print `.tgz`** (`download_arxiv_source`, the
  endpoint the abs-page download button hides: `https://arxiv.org/e-print/<id>`)
  when no local `--tex`/`.tgz` is present, then ingests the author's gold
  equations. Verified live end-to-end on 2510.11170v2: PDF downloaded, MathPix
  skipped, base model built by OCR (15 pages), `.tgz` fetched, 5 display
  equations + 425 macros ingested — **zero MathPix spend**. Honest caveat: with
  an OCR base model (no MathPix equation detection) the 5 gold equations matched
  0 OCR equation slots — the gold LaTeX is still extracted/kept, but precise
  overlay/comparison wants MathPix's equation isolation or a source-built model
  (`latexbook`-style, a near-term follow-up).

Pure parsers (`is_url`/`host_of`/`known_host`/`parse_arxiv_id`/`arxiv_urls`/
`parse_arxiv_abs_html`) are network-free and unit-tested; the net routes
(`fetch_arxiv_metadata`/`download`/`resolve_input`/`download_arxiv_source`) go
through `net.urlopen`, so a sandbox block degrades to the local routes. Tests:
`tests/test_sources.py` (pure) + `tests/test_arxiv_routes.py` (mathpix-skip +
free-abstract wiring, network monkeypatched).

## Current status

Merged layout + working pdfdrill CLI (verified on `2605.12061`) + passing
suites. The MathPix-only QC path is **end-to-end functional**:

- **`pdfdrill mathpix <pdf>`** — Python port of `mtestzx.ts`, idempotent,
  creds from env or git-ignored `mathpix_creds.py` (`tests/test_mathpix.py`).
- **Large-file handling (the 463 MB / 175-page edge case).** The upload used to
  `f.read()` the whole PDF + build a `crlf.join` body — a 2× copy that OOMs a
  small sandbox. Now `upload_pdf` STREAMS the multipart body to a temp file
  (chunked `copyfileobj`, bounded RAM) and POSTs it with an explicit
  `Content-Length`; `_stream_multipart` is byte-identical to the in-memory encoder
  (tested). `cmd_mathpix` runs `upload_preflight(size, pages)` only when an upload
  would happen (not cached): **refuse** over MathPix's ~512 MB cap (clear message
  → route to keyless `pdfdrill ocr` / `pdfseparate` chunks), **warn** for large
  inputs (>100 MB / >100 pages: streamed but slow/costly). Any upload/conversion
  failure (413 too-large, API error) is caught and degraded to OCR instead of a
  traceback. The 463 MB file → `warn` + streamed; `model` falls back to tesseract
  if no lines.json appears. Tests: `tests/test_mathpix_large.py`.
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
- **Special-image delivery (state-machine fix).** `snip` was equation-locked even
  though `mathpix_snip.snip()` accepts *any* image — so a consumer interested in a
  SPECIAL image (figure/stamp/table/handwriting) couldn't get it. Now `pdfdrill
  snip <pdf> --image <path|url|data:>` OCRs any image, and `--page N --rect
  x0,y0,x1,y1 [--ppi]` rasterizes that region, **delivers the crop PNG** (Read it,
  or `vision` it) via `_deliver_region_crop`, then OCRs it — the crop is delivered
  **even when OCR is unavailable** (no key/blocked): deliver what we can. Honors
  the image-routing principle (every route to an image hangs off one node; pick
  whichever succeeds). Tests: `tests/test_snip_special.py`.
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
- TiddlyWiki: **LaTeX sectioning commands that MathPix leaves inside a
  paragraph body** (`\section*{X}`/`\subsection*{X}`/…) are converted to the
  native WikiText heading (`! X` / `!! X` / `!!! X`; chapter→`!`) by
  `tiddlywiki.latex_sectioning_to_wikitext`, applied at the single chokepoint
  where PARA `text` is built (`_transclude_paragraph`, last so it doesn't
  disturb offset-based inline substitutions). The PARA template is
  `<p>{{!!text}}</p>` and KaTeX renders only math, so an un-converted
  `\section*{...}` showed as the literal string. The title is brace-balanced so
  a `{{<eq>||FO}}` transclusion inside it survives. On 2004.05631: 57 leaking
  paragraphs → **0** (53 now open with a heading). Footnote refs are emitted as
  `{{<fn>||FN}}` (the `FN` template = superscript link); there is **no**
  `FNREF` and none is emitted — generator and template set are consistent.
  Tests: `tests/test_tiddler_headings.py`.

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
- **Math-span guard (all citation detectors):** a `[...]`/`(...)` group inside
  an inline/display math span (`\(...\)`, `$...$`, `\[...\]`, `$$...$$`) is an
  interval/set/index, NOT a citation, so the `CitationProcessor` and both
  bibliography detectors skip matches that fall inside a math span. Without it,
  `\([A x, B x]\)` (MathPix's render of the interval `[A_x, B_x]`) produced two
  bogus `A x`/`B x` Citations that then leaked into a synthetic FOX formula's
  LaTeX as `{{...||CIT}}` transclusions. Tests:
  `tests/test_citation_math_guard.py`.
- NOTE on the samples: `2312.11532` is author-year text; `2605.12061`'s
  in-text citations live in the **PDF annotation layer** as `cite.<key>` dest
  links (only "(NeurIPS 2026)" is parenthetical in its OCR text), so the
  precise next unlock for `2605` is promoting those `cite.<key>` annotations
  into `Citation`→`Reference` edges (the `annotate`/`link_xref` machinery
  already targets `cite.<key>`; it needs `Citation` nodes keyed by those dests).

Full BibTeX burst: `pdfdrill bibfetch data/2312.11532.pdf` enriched **18/18**
references with full BibTeX + title + citations via Perplexity SONAR.

Drill INTO a citation (`src/pdfdrill/citedrill.py`, `pdfdrill citedrill`): find
where each cited publication can be **downloaded** and fetch it. Per Reference:
(1) Perplexity SONAR is asked for ALL download links (`perplexity_client.
fetch_links` / `links_prompt`), merged with links seeded from the reference's
OWN `bibtex`/`raw_text` (so it still works offline / when the API is blocked);
(2) `rank_links` orders **free routes first** — an arXiv abs/pdf URL is
normalized to its direct PDF URL, then bare `.pdf`, then DOI, then anything
else; (3) each candidate is HEAD-`verify`'d and then (attempt-ANY-link policy)
downloaded in rank order until one PDF lands in `<drill>/cited/<citekey>.pdf`;
(4) a per-reference **`cited/<citekey>.pdf.json`** records the attempt
(candidates + verify/fetched status + the working link), and the Reference is
stamped with **`drill_status`** (fetched / links_only / no_links / blocked) +
`pdf_url` / `pdf_path` / `pdf_json` / `download_links`. Pure helpers (extract/
classify/rank/record/status/fields) are unit-tested; the network parts degrade
gracefully (no key / `NetworkBlocked` → seeded links only / `blocked`).
`pdfdrill citedrill <pdf|md> [--limit N] [--force]`; idempotent per reference.
Verified live on the cspmath monograph: 3/3 cited PDFs fetched (real `%PDF`
files: Carlsson "Topology and data", Coifman-Lafon "Diffusion maps", …), each
Reference carrying its drill status + a link to the pdf.json. Tests:
`tests/test_citedrill.py` (6). Honest note: the attempt-any-link policy will
fetch whatever a link returns (a `@misc` registry ref can pull an incidental
PDF) — the candidates + verify status in the pdf.json are there to audit it.
- Markdown in-text refs: `LLMCompactProjector` gains an opt-in `eq_refs` param
  that rewrites `(N)` → the equation's compact placeholder `[E‹k›]` (off by
  default; for round-trip tests).
- **YAML front-matter** (`include_meta`, default on): the LLM-compact markdown now
  opens with a `--- … ---` YAML header instead of the old `# bibkey` line —
  bibliographic fields (`title`/`author`/`date`/`tags`/`description` from the
  Abstract) plus pdfdrill status info (`bibkey`/`arxiv_id`/`primary_category`/
  `pages` + per-type element counts `sections`/`equations`/`formulas`/`figures`/
  `tables`/`references`) and `generator: pdfdrill`. Scalars are YAML-escaped
  (`llm_compact._yaml_scalar` quotes values with `:`,`,`,`#`,… so a title like
  `EAGer: …` round-trips). Tests: `tests/test_docops.py`
  (`test_llmcompact_emits_yaml_front_matter` — parses the block with `yaml.safe_load`).

Gold bibliography ingest from the author's `.bbl`/`.bib`
(`bibliography.parse_bbl`/`ingest_bbl`/`link_citations_by_label`,
`pdfdrill bibsource`):

- The bibliography analogue of `pdfdrill latex` (author .tex as gold equations).
  When the arXiv e-print is on hand, **`pdfdrill bibsource <pdf> --bbl X.bbl
  --bib X.bib`** ingests the author's compiled bibliography instead of
  reconstructing it from OCR (heuristic) or the web (Perplexity): the `.bbl`
  gives `\bibitem[<alpha label>]{<citekey>}` + the printed entry (each Reference
  gets a `references`-stream anchor so it's addressable), the `.bib` enriches
  structured fields (author/year/title/entry_type/bibtex), and in-text
  Citations are linked to References **by alpha label**, OCR-tolerant
  (`_norm_label` maps MathPix's `ASVo2`→`ASV02`, `NCoo`→`NC00`). Authoritative:
  it drops prior heuristic References + `cites` edges first. No API.
- Verified on arXiv 2004.05631 (Bradley thesis): the heuristic found **1**
  garbage Reference and linked 0 citations; `bibsource` from `thesis.bbl` +
  `thesis.bib` built **63 References** (all enriched) and linked **108/115**
  in-text citations (the 7 misses are mostly section/appendix cross-refs
  mis-detected as citations). Tests: `tests/test_bibsource.py`.
- Use `bibsource` when the `.bbl`/`.bib` is available; `bibfetch` (below) is the
  fallback when only the printed (truncated) references exist.

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

DeepL translation IN PLACE → tiddlers + bi-layer Markdown
(`src/pdfdrill/deepl_client.py`, `pdfdrill translate`):

- **`pdfdrill translate <pdf> [--to EN-US] [--from RU] [--limit N] [--force]`**
  translates the document **in place** via DeepL API v2 (stdlib `urllib`, no
  SDK) — one source, two outputs. The translation replaces the field and the
  original is kept under **`<field>_source`**. Math/code/image objects untouched.
  Idempotent (skips fields that already carry `<field>_source`; `--force`
  re-translates from the preserved original). Key from `DEEPL_API_KEY` (env/.env;
  free keys end `:fx` → api-free host); calls go through `net.urlopen` (graceful
  block message; a quota/error degrades to the original so a batch never aborts).
- **Two representations, two passes — by necessity.** The Markdown projector
  (llm_compact) renders from the model's clean `props["text"]`, but the
  **TiddlyWiki projector rebuilds transcluded paragraphs from the immutable
  source stream BY OFFSET** (to re-insert `{{…||FO}}` tokens) — so translating
  the model's `text` reaches the Markdown but NOT transcluded tiddlers. Hence
  `cmd_translate` does both: (1) `translate_model_prose` translates the model
  prose in place → re-projects the **bi-layer Markdown** `<bibkey>.md`
  (`LLMCompactProjector` `bilayer=True`: a `<div class="seg trans">` + a hidden
  `<div class="seg source">` per block, with a CSS/JS show-source toggle —
  `_bilayer_header`); (2) regenerates `<bibkey>.tiddlers.json` and
  `_translate_tiddler_file_inplace` translates the tiddler `text`/`caption` at the
  tiddler level (tokens already inserted, so DeepL translates the prose around
  them) — your original `~/MX/tiddly-translation` approach, writing the **changed
  tiddler file in place** (not a new `<lang>` file). Verified live on the Russian
  paper 576-659-1-PB (RU→EN-US): tiddler `text` = English / `text_source` =
  Russian (43/46 prose tiddlers English; the rest author/affiliation lines), and
  `576-659-1-PB.md` is bi-layer with the toggle. Tests:
  `tests/test_translate.py` (`translate_model_prose` + `_translate_tiddler_file_inplace`,
  no real API) and `tests/test_docops.py`
  (`test_llmcompact_bilayer_emits_both_layers`).

## Markdown input (`pdfdrill markdown` — the yt2tw route)

**`pdfdrill markdown <file.md> [--bibkey K] [--force]`**
(`src/pdfdrill/markdown_source.py`) builds a source-only model from LLM-summary
Markdown (Perplexity etc.; the yt2tw YouTube-summarizer output): `#` title →
meta, `##`/`###` → Sections (Abstract/TOC/References/BibTeX headings handled
specially), prose → Paragraphs, `\[...\]`/`$$` → Equations, bullets →
ListItems, and `\cite{key}` in prose → Citation objects. The fenced
```bibtex appendix is GOLD: entries become Reference objects (citekey/author/
year/title/entry_type + verbatim bibtex) and citations link to them via
`cites` alignments; without it the numbered References list is parsed
heuristically. **Truncation-tolerant** (live-test find): real Perplexity
output gets cut off mid-entry — an unclosed fence at EOF is flushed and a
brace-unbalanced final entry is salvaged up to EOF, so its parsed fields
survive. Every object anchors into a `markdown_source` Stream. Artifacts in
`<md>.drill/`; the whole docops chain (tiddlers/report/semantic) runs on it.
Verified on ~/Downloads/yt2tw-out/summary.md (sheaf-NN lecture summary): 21
sections, 45 paragraphs, 7 equations, 4 gold references incl. the truncated
phdthesis, 6/6 citations linked, 119 tiddlers. The sibling slide-extractor
PDFs go through the ordinary PDF route; a shared --bibkey family combines a
talk's summary + slides. (The yt2tw `*_video_0001.json` is already a
TiddlyWiki tiddler list — JSON adaptation planned on the yt2tw side.)
Tests: `tests/test_markdown_source.py` (9).

`pdfdrill latexbook <book.tex>` is the one-shot source-only pipeline (no PDF,
no MathPix): build the model from `.tex` (inline `\input`, resolve preamble +
local `.sty` macros, extract sections/equations/TikZ/tables), **auto-render
TikZ + tables to SVG** (`latex→dvisvgm`), and emit the KaTeX formula report
with SVGs embedded — all in one call. `--no-svg` skips rendering; it also
degrades cleanly (clear message) when `latex`/`dvisvgm` are absent. Verified
on the graphbook: 128 sections, 343 equations, 118 macros, **18/18** TikZ/
tables → SVG, one command.

**LaTeX environment tracking (`latex_source.scan_environments`, 2026-06-26).**
The LATW `EnvironmentWrapperScanner`/`EnvironmentCleaner` analogue, but as a
TRACKING layer for higher levels (e.g. a LEAN4 theorem/proof export).
`scan_environments(decl_text, body)` (pure) returns: `used` (the `\begin{X}`
census {name: count}), `newtheorem` (theorem-like envs DECLARED — name / printed
title / shared+reset counter / starred), `newenvironment` (custom or redefined
env names, `#`-parameter templates skipped), `theorem_like`, and
`theorem_blocks`/`proof_blocks` (how many are USED). `build_source_model` scans
the preamble + the local `.sty`/`.cls` (`_local_style_text` — where `\newtheorem`
/`\newenvironment` actually live, incl. the publisher style the user flagged) and
stores it in `doc.meta["environments"]`. `status` surfaces it
(`_format_environments`): used count, the declared theorem-like list, the
theorem–proof block tally tagged as LEAN4 candidates, and the custom-env list
(style-internal `@`-names counted but hidden from display). Verified on arXiv
2110.11150: 23 distinct envs used, theorem/proposition/lemma/corollary/definition/
assumption/remark + starred theorem*/lemma* + example declared, **11 theorem-like
+ 6 proof blocks**, redefined `abstract`/`table` + `algorithmic` custom envs.
Next: a LEAN4 projector consuming this (theorem/proof DocObjects, statement+proof
pairing). Tests: `tests/test_latex_algorithms.py`
(`test_scan_environments_usage_newtheorem_newenvironment`,
`test_format_environments_status_lines`).

**`algorithms` reports from the model objects, not stale sidecar evidence
(2026-06-26).** `pdfdrill algorithms` showed **0** on a source-built doc that
clearly had an algorithm (2110.11150's appendix `\begin{algorithm}[h!]`,
algorithm2e style). Root cause: `_format_algorithms` read the sidecar
`algorithms_created`/`_steps`/`_max_depth` evidence, which ONLY the MathPix
path sets — so when the model already carried Algorithm objects (built by
`build_source_model`'s `extract_algorithms`, which DID isolate the algorithm2e
float) the command early-returned a sidecar summary of 0. Fixed:
`_format_algorithms(doc)` now counts the model's `Algorithm`/`AlgorithmStep`
objects (the source of truth) and lists their titles, working for both build
paths. Verified: 2110.11150 → "1 Algorithm block(s) with 18 steps — \texttt{
edge-popup-scaled}". (`extract_algorithms` already handled an algorithm2e
`\begin{algorithm}` float with NO inner `algorithmic`, one step per line,
recovering the nested-brace `\caption{\texttt{…}}` title — now regression-
tested.) Tests: `tests/test_latex_algorithms.py`
(`test_algorithm2e_float_without_inner_algorithmic`,
`test_format_algorithms_counts_model_objects_not_sidecar`).

**Source-path algorithm isolation** (`latex_source.extract_algorithms`,
2026-06-15). The MathPix `pdfdrill algorithms` path reads `pseudocode` lines;
the LaTeX-source path now isolates algorithms directly from the `.tex`. Each
`\begin{algorithmic}` body (algorithmicx / algpseudocode / algorithmic —
`\Require`/`\Ensure`/`\If{}`/`\State`/`\Return`/`\EndIf`/`\For{}`…, matched
case-insensitively) becomes an **`Algorithm`** DocObject with **`AlgorithmStep`**
children, each step carrying an indentation **`depth`** derived from the
If/For/While/Function block nesting (openers add a level, `\End*`/`\Until` close
one, `\Else`/`\ElsIf` dedent their own line) — the same shape the MathPix path
emits. An enclosing `\begin{algorithm}` float supplies the `\caption` title,
`\label`, and the sequential auto-`number`; a standalone `algorithmic` (no
float) gets `number=None`; an `algorithm` float with no inner `algorithmic`
(algorithm2e/plain) is isolated one step per line. `build_source_model` emits
them after the section/equation/graphic flow (tagged `added_by="latex"`) and
records `algorithms`/`algorithm_steps` in `source_counts`; `cmd_latexbook`
reports the count. **Closes the graphbook gap** (was 0 isolated): `pdfdrill
latexbook book.tex` → **59 algorithms, 816 steps, max nesting depth 4**, all 59
numbered floats. Tests: `tests/test_latex_algorithms.py` (5 — step/depth parse,
float caption/label/number, standalone, ordering, build_source_model wiring).

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
- **Both forms survive projection — visualize expanded, keep the macro source.**
  KaTeX/`<$latex>` can only render the **expanded** `latex` (a private macro like
  the GDL book's `\renewcommand{\vec}{\mathbf}` makes the default `\vec` arrow
  WRONG), so the tiddler/markdown render the expanded form — but the verbatim
  macro source is no longer dropped. The TiddlyWiki projector emits a
  `latex_original` field on formula/equation/diagram tiddlers (when present), and
  the `LLMCompactProjector` glossary appends `· macro source: \`…\`` for any
  formula/equation whose original differs from the expanded form. Verified on the
  Geometric Deep Learning proto-book (arXiv 2104.13478, **468 preamble macros**,
  built source-only via `latex_source.build_source_model` — no OCR): formulas
  like `\gR→{\mathcal{R}}`, `\fg→{\mathfrak{g}}`, `\vec→\mathbf` render expanded
  while their macro source is preserved. Tests: `tests/test_docops.py`
  (`test_tiddler_and_md_keep_both_latex_forms`).
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
failures).

**Source graphics reach `svg` via `pdfdrill latex` (arXiv fix).** For an arXiv
paper whose model is built by OCR (MathPix skipped), `pdfdrill latex` used to
ingest only equations — so `svg` saw **0 graphic objects** even when the paper is
full of diagrams. `commands.ingest_source_graphics` now also lifts the source's
TikZ/tables (notably **`tikzcd` commutative diagrams**) into Diagram/Table objects
with `latex_code` (+ `latex_original`), tagged `added_by="latex"`. `cmd_latex`
extracts the e-print `.tgz` to `<pdf>.drill/texsrc/` and records
`doc.meta["latex_source_dir"]`, which `cmd_svg` puts on `TEXINPUTS` so the
project's **local `.sty`** (e.g. `siamproceedings.sty` bundled in the e-print)
resolves. `compile_to_svg` decodes latex/dvisvgm output with `errors="replace"`
(no crash on latin-1 source). `standalone_preamble` was rebuilt: it keeps the
math/TikZ `\usepackage`s (dropping document-class STYLES + layout packages —
`_STANDALONE_DROP_PKGS`: siamproceedings/geometry/hyperref/… that break
standalone cropping with "Dimension too large") plus the author's macro defs with
**full multi-line bodies** (`_collect_macro_defs` brace-balances them — the old
line-anchored regex truncated a `\newcommand` and left a runaway def) plus
`\DeclareMathAlphabet`/`\SetMathAlphabet`. `standalone_preamble` also captures the rest of the math/diagram setup a snippet
needs: `\usetikzlibrary{…}` (e.g. decorations.markings), `\tikzset{…}`/`\tikzcdset`
style blocks (brace-balanced — custom arrow styles like `utcofarrow`),
`\DeclareMathAlphabet`/`\SetMathAlphabet`, and low-level `\font\…=…` primitives
(e.g. the Yoneda symbol `\yo` from `\font\maljapanese=dmjhira`). Verified on arXiv
2510.15795 (SIAM proceedings, 55 `tikzcd` commutative diagrams): `pdfdrill latex`
→ `pdfdrill svg` went from **0 → 55/55** rendered. The fixes were a cascade — each
missing preamble element surfaced the next: minimal-math preamble (drop the class
style) → multi-line `\newcommand` bodies → `\DeclareMathAlphabet` → `\font`
primitive → `\tikzset` styles → `\usetikzlibrary`. Tests: `tests/test_svg.py`
(graphics ingestion + multi-line/`\font`/`\tikzset`/`\usetikzlibrary` preamble).

**Rendered SVG reaches the tiddlers (inline field + transclusion).** The
TiddlyWiki diagram/table tiddler used to hard-code `<$image source={{!!canonical_uri}}>`
(the CDN crop) and dropped the locally-rendered `props["svg"]` entirely — so after
`pdfdrill svg` the import had no SVG. Now, when a Diagram/Table carries a rendered
`svg`, the projector puts the inline SVG in the tiddler's **`svg_tiddler` field**
(`_svg_inline` cuts everything before the root `<svg>` — XML decl, DOCTYPE,
dvisvgm comment — so the field is pure, inline-renderable SVG) and sets the
tiddler **text to `{{!!svg_tiddler}}`** (simple field transclusion). NOTE:
`<$image source="…">` does **not** render an svg tiddler (it wraps it in an
`<img>` data-URI) — field transclusion renders the inline SVG directly. Falls
back to the CDN `<$image>` when there's no SVG. Verified on arXiv 2510.15795: 55
diagram/table tiddlers, text `{{!!svg_tiddler}}`, field = pure `<svg …>`. Re-run
`pdfdrill tiddlers` AFTER `pdfdrill svg`. Test
`tests/test_docops.py::test_diagram_tiddler_transcludes_svg_field`.

- **External-file mode (`--embed-svg=false`).** Inline SVG is the default, but a
  paper with many diagrams inlines a lot (2510.15795: 1.5 MB tiddlers.json). The
  projector stays pure (always inline); `cmd_tiddlers` then post-processes when
  `--embed-svg=false` — `_externalize_svg_tiddlers` writes each diagram's SVG to
  `<pdf>.drill/svg/<title>.svg` and rewrites the tiddler to `type:
  image/svg+xml` + `_canonical_uri: svg/<title>.svg` + empty text (other fields,
  e.g. `latex_code`, kept). Single boolean flag (also `--no-embed-svg`),
  idempotent, sidecar records `tiddlers_svg_mode`; falls back cleanly when no SVGs
  exist. 2510.15795: **1.5 MB → 147 KB** + 55 files in `svg/` (copy that folder
  alongside the wiki HTML). Test:
  `tests/test_svg.py::test_externalize_svg_tiddlers_writes_files_and_canonical_uri`.

`array` is excluded from graphics extraction (it's math-mode,
KaTeX-rendered inside its equation — not a standalone table). The `\[…\]`
display-math extractor no longer mis-splits `\\[4pt]` row-spacing in
align/cases. `latex/pdflatex/dvisvgm/dvips` present here (`pdf2svg` missing).
Tests: `tests/test_svg.py`, `tests/test_latexbook.py`.

Embedded-image fusion — all image routes on one node
(`src/pdfdrill/image_model.py`, `pdfdrill embedimages`):

- **`pdfdrill embedimages <pdf>`** lifts every embedded raster image from
  `pdfimages -list` (true pixel size / encoding / colour / bpc / ppi / file
  size / object_id) + `pdfplumber` page rects into the model as `EmbeddedImage`
  DocObjects (a `Region` in `space="pdf_points"`), then **fuses** each MathPix
  `Picture`/`Diagram` crop onto the embedded image that *contains* it. Fusion
  normalizes both coordinate systems to page fractions [0,1] (pdfplumber rect ÷
  page-points; MathPix region ÷ MathPix page-pixels) and links by containment →
  `Alignment(kind="image_region")` + an `embedded_image_id` cross-link on the
  crop. Coordinate values are coerced (regions parsed from CDN URLs are
  strings). The EmbeddedImage carries the pdfplumber rect (top-left origin) in
  its `Region` **and** the PDF-native bottom-left Y (`y0_pdf`/`y1_pdf`) +
  `page_width_pt`/`page_height_pt`, so it is self-describing and matches a
  bottom-origin tool byte-for-byte (verified field-for-field against an
  external `pdfimagepos.py` on arXiv 2004.05631: page/obj/src_w/src_h/x0/x1/
  w_pt/h_pt identical, Y = page_height − y).
- The point (the user's "ONE structure"): every route to an image — MathPix
  CDN crop, GPT-4o vision read (`openai` provenance), `pdfimages` XObject
  metadata, `pdfplumber` rect — now hangs off the same graph, so the state
  machine can take whichever route succeeds. Runs in the offline `folder`
  batch (no key). On a scanned PDF each page is one full-page image and all its
  crops link to it; on a born-digital PDF the per-figure XObjects link to their
  matching crops.
- Verified on `~/WKprivate/Scanned/ocrtest.pdf`: 45 EmbeddedImage nodes, 29
  MathPix crops fused (image_region edges + cross-links). Tests:
  `tests/test_embedimages.py` (containment fusion, crop-outside-not-fused,
  string coords, idempotent re-run).

Leftover-crop recovery — empirical route comparison (which tool for what):

- A 37-crop study on `~/WKprivate/Scanned/ocrtest.pdf` (every MathPix-leftover
  image), scoring three recovery routes per crop against the actual image
  (tesseract `deu+eng` OCR, MathPix Snip `/v3/text`, LLM vision). Result: **all
  37 recoverable**; **vision wins 34/37** (mean fidelity 0.91) vs Snip 0.26 vs
  tesseract 0.24. Per content type vision wins every class; the cheap routes
  are competitive only on machine-printed text/table/equation (tesseract hit
  1.0 on a clean printed address block + a printed equation; Snip's single win
  was a handwritten table at 0.85). **Handwriting (12 crops) is vision-only**
  (tesseract 0.06, Snip 0.35, vision 0.85).
- **MathPix Snip is text/math-only:** it returns "Content not found" on photos/
  charts/logos — *identically* whether given the image URL or the uploaded
  bytes (so it's a no-content signal, not a fetch failure). **tesseract emits
  noise** on non-text crops (skip it there).
- **State-machine routing rule** (keeps all options open, vision as the
  terminal fallback so extraction always succeeds): normalize the crop URL
  (unescape `\&`→`&`, else upload bytes) → if confidently machine-printed
  text/table/equation, try tesseract then Snip (accept at ≥0.7) → for
  handwriting, optionally Snip for tables else vision → for chart/diagram/logo/
  mixed/photo, go straight to vision (don't call Snip/tesseract) → vision is the
  terminal route for every path; if max score <0.3, flag unrecoverable (none
  occurred). The competing readings already attach as provenances (`snip`,
  `openai`); `_collect_cdn_crops` now yields only clean fetchable URLs.

OpenAI GPT-4o vision provenance (`src/pdfdrill/openai_vision.py`,
`pdfdrill vision`):

- MathPix sometimes can't OCR a region and drops a CDN **image** in its place
  — including `![](cdn…)` links **inside table cells** (seen on scanned office
  docs). **`pdfdrill vision <pdf> [--limit N]`** reads every CDN crop in the
  model with GPT-4o (`gpt-4o-2024-08-06`, structured-JSON `selector`:
  math/tikzpicture/commutative_diagram/gnuplot/tensor/**table**/empty), and
  attaches the returned LaTeX/TikZ/tabular as a `provenance="openai"`
  `latex_candidate` realization — the third competing reading alongside MathPix
  and Snip. `_collect_cdn_crops` finds an object's own `cdn_url`/`url` AND crops
  embedded in any string prop (table `raw_text`, with `\&`→`&`).
- **Graph/subgraph images → TikZ.** When a crop's owning object's caption/title
  names a graph/subgraph (`\b(sub)?graph\b`), `cmd_vision` swaps in
  `openai_vision.GRAPH_TIKZ_PROMPT` (reconstruct vertices+edges+colour emphasis
  as a standalone `tikzpicture`) instead of the default classifier — vertex/edge
  drawings reconstruct cleanly as TikZ. Verified on arXiv 2004.05631: the p11
  "subgraph in red is complete bipartite" diagram → a bipartite `tikzpicture`
  with the red complete-bipartite subgraph emphasized.
- **Chemistry images → chemfig/mhchem** (integrated from a downstream
  Claude.ai patch). New selectors `chemical_equation` (→ a normalized bare
  `\ce{…}`, mhchem v4) and `chemical_structure` (drawn 2D molecule/reaction
  scheme → chemfig / `\schemestart` body code); a caption naming a molecule/
  compound/reaction/`Scheme N` routes to `CHEM_STRUCTURE_PROMPT` (deliberately
  NOT matching bare "structure"/"formula"). The result is **adopted into an
  empty `latex_code`** (`latex_code_provenance="openai"`, never overwriting
  MathPix/source LaTeX) so `pdfdrill svg` compiles it via latex→dvisvgm like
  TikZ; `svg.is_latex_graphic` accepts `\chemfig|\schemestart|\ce`, the default
  preamble loads chemfig+mhchem, and **compile_to_svg injects the packages into
  a document-derived preamble that lacks them**. KaTeX mhchem extension added
  to compare.html; `doctor` hints `texlive-plain-generic` (chemfig needs
  simplekv.tex). Compile-proven: benzene ring, ethanol bond spec, `\ce`
  reaction, `\schemestart` scheme → 4/4 SVGs. Tests: `tests/test_vision.py`
  (normalizers + chem-prompt routing + latex_code adoption),
  `tests/test_svg.py` (preamble injection).
- **Coloured tables (`\rowcolor`/`\cellcolor`/`\columncolor`) — `xcolor[table]`**
  (2026). A mass keyless-LaTeX run left ~34 tables unrendered because they need
  `xcolor`'s `[table]` option (→ `colortbl`), which the standalone preamble
  didn't carry. The default preamble now loads `\usepackage[table]{xcolor}` (BEFORE
  tikz, which loads xcolor) + `colortbl`; and `svg._augment_preamble` (the
  extracted chemfig/mhchem-injection helper) adds the `table` option to a
  DOCUMENT-derived preamble via `\PassOptionsToPackage{table}{xcolor}` (prepended
  before any explicit/implicit xcolor load → **no option clash**), loading xcolor
  itself only when neither an explicit line nor tikz is present. Tests:
  `tests/test_svg.py` (default-preamble carries it; doc-preamble injection no-clash;
  no-trigger unchanged + chemfig still injected).
- **Conference page-styles dropped from the standalone preamble + executed `.tex`
  persisted for inspection (2026-06-26).** `pdfdrill svg` failed all 4 graphics on
  2110.11150 with `! Dimension too large` — `\usepackage[preprint]{neurips_2022}`
  (the venue PAGE-STYLE) sets full-page geometry `standalone` can't crop. These
  packages are named per venue+year, so a fixed drop-list can't catch them:
  `latex_source._CONFERENCE_STYLE_RE` (neurips/icml/iclr/cvpr/aaai/acl/… + year, or
  `*_conference`) now drops them in `standalone_preamble` via `_drop_from_standalone`
  — but ONLY known venue names, so a LOCAL style that defines macros/colors/pgfplots
  cycle-lists a snippet needs (here `palettes.sty` → the `juarez4` cycle list the
  two pgfplots diagrams use) is KEPT. Dropping only `neurips_2022` (not `palettes`)
  took 2110.11150 from 0/4 → **4/4** (2 booktabs tables + 2 pgfplots diagrams).
  Rebuild the model so the regenerated `standalone` preamble (in `doc.meta`) takes
  effect. For debugging, `compile_to_svg` now returns the exact `src` + latex `log`,
  and `cmd_svg` writes each graphic's compiled standalone `.tex` (+ `.log` on
  failure) to `<drill>/svg/tex/<bibkey>_<Type>_NN.tex` — open it in a LaTeX editor
  (Gummi) to debug a failing snippet. Tests: `tests/test_svg.py`
  (`test_standalone_preamble_drops_conference_style_keeps_local_styles`).
- **`\definecolor`/`\pgfplotsset` kept + booktabs injected (2026-06-27).** Two more
  standalone-preamble gaps found on arXiv 2603.16021 (7/7 graphics failed):
  `standalone_preamble` dropped the paper's `\definecolor{layerstructural}{…}` (and
  `\pgfplotsset{…}`), so tikz errored `Undefined color`; and a booktabs table whose
  paper loads `booktabs` INDIRECTLY (via the class) hit `Undefined control sequence
  \toprule`. Fix: `standalone_preamble` now also captures every `\definecolor` line
  and each brace-balanced `\pgfplotsset{…}` block; `svg._augment_preamble` injects
  `\usepackage{booktabs}` when a snippet uses `\toprule`/`\midrule`/`\bottomrule`/
  `\cmidrule`/`\addlinespace` and the preamble lacks it (mirrors the chemfig/xcolor
  injection). 2603.16021 → **0/7 → 7/7** (2 booktabs tables + 5 tikz/pgfplots with
  custom colors). Tests: `tests/test_svg.py`
  (`test_standalone_preamble_keeps_definecolor_and_pgfplotsset`,
  `test_augment_preamble_injects_booktabs`).
- Ported from the predecessor `~/MX/mathpix_images` (llmUtils.js/imagetester.js
  + prompt.txt). Stdlib `urllib` (no `openai` package). Key from
  `OPENAI_API_KEY` (env/.env), **never hardcoded**; `--limit` caps calls (a doc
  can carry 100+ crops, e.g. ocrtest has 109). Graceful no-key + per-crop error
  handling (a bad key counts as errors, no crash). Tests: `tests/test_vision.py`
  (crop collection incl. escaped table cell, selector→latex, cmd wiring,
  no-key path; no real API call).
- Verified on `~/WKprivate/Scanned/ocrtest.pdf`: the model carries 109 CDN
  crops (28 tables, 2 with embedded cell-images); `cmd_vision` collects them
  and (with a valid key) extracts each. The intended-table case proven by hand:
  the p20 invoice crop reads as a full 7-row tabular.

MathPix-free OCR input path (so the repo runs keyless, all functions
testable):

- **`pdfdrill ocr <pdf> [--lang eng] [--ppi 300]`** (`commands.cmd_ocr` +
  `src/pdfdrill/ocr_lines.py`) renders each page (`pdftoppm`), OCRs it with
  **tesseract** (`--psm 1 tsv`), groups the word boxes into text lines, and
  writes a **MathPix-compatible `<pdf>.lines.json`** (`source:"tesseract"`,
  one `type:"text"` line per visual line, MathPix-style pixel `region`). It
  reuses the TSV parser + `group_lines` already in `geometry.py` (one code
  path). `pdfdrill model` then ingests it unchanged.
- TSV chosen over makebox: TSV carries the block/par/line hierarchy +
  per-word confidence + boxes needed to rebuild lines; makebox is per-glyph.
- **`pdfdrill model`** now prefers MathPix but **falls back to `ocr`** when
  MathPix is unavailable (no creds/network) and tesseract is present — so the
  pipeline runs end-to-end without a key.
- Limits (documented, not hidden): tesseract is **plain text only** — no
  LaTeX, no equation/figure typing, no CDN crops, so the math-comparison
  columns are empty on this path (math fidelity stays MathPix-only). Use
  `--lang eng+equ` for math glyphs (the `equ` model) or `eng+deu` for German.
  `cmd_ocr` refuses to overwrite a MathPix `lines.json` without `--force`.
  Verified live: page 1 of arXiv 2312.11532 → 69 OCR lines → `model` built (1
  Paragraph), title recovered. Tests: `tests/test_ocr.py` (pure assembler +
  feeds-the-docmodel + clobber/unavailable guards).

NLP layer (Stanza — optional `[nlp]` extra, first-class command):

- **`pdfdrill nlp <pdf> [--limit N] [--pages N] [--types T,T]`**
  (`commands.cmd_nlp`) loads/auto-builds the model and runs the
  `StanzaNlpMutator` (`src/docops/mutators/stanza_nlp.py` + portable engine
  `src/docops/nlp_stanza.py`) over each prose object (Paragraph/Abstract/
  Section/ListItem/Footnote): projects the text to clean prose (LaTeX markup
  stripped, inline math → `⟨math⟩`, `[n]` cites dropped, and **TiddlyWiki
  transclusions rewritten to natural-language phrases** — `{{Bibkey_FO0139||FO}}`
  → "formula 139", `||FREF` → "referenced formula number N", `||PIC/DIA` →
  "picture/diagram N", `||CIT` → "a citation" — so Stanza's tokenizer/parser
  sees real noun phrases instead of opaque IDs; the rewrite is stable per
  template (`docops.nlp_stanza._rewrite_transclusion`)),
  splits into sentences, and attaches per-sentence tokens (POS/lemma/xpos/
  feats/head/deprel) + named entities under `props["nlp"]`. The raw source
  field is untouched; result is persisted back to `model.docmodel.json`.
- Optional + graceful: needs `pip install 'pdfdrill[nlp]'` (stanza) plus a
  one-time `stanza.download('en')`. When the library/model is missing the
  command prints an install hint and changes nothing (mutator skips unless
  `require:true`). Model load is ~30–40 s, so `--limit`/`--pages` keep dev
  runs fast. The sibling project `~/MX/NLP` (`mxnlp`) is a standalone twin
  (same engine + an `annotate`/`search` CLI) and is what installed stanza +
  the `en` model into this environment.
- Verified on the Ludwiger model: 8 prose objects → 47 sentences, 78 entities
  (PERSON/DATE/ORG/GPE/CARDINAL; e.g. "Burkhard Heim", "Potsdam", "1944").
  Tests: `tests/test_nlp_stanza.py` (engine + mutator, fake annotator) +
  `tests/test_nlp_command.py` (cmd_nlp wiring + graceful-unavailable path).

Still to do: deepen the self-learning loop (auto-tune from accumulated flags);
math-expression / document-structure / citation graphs queried like Pyre/Pysa
over the persisted `model.docmodel.json` (the between-call memory).
