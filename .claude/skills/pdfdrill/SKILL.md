---
name: pdfdrill
description: |
  Token-economical drill-down extraction from PDF documents. Use whenever
  the user provides a PDF — as a local file, an https URL, or a bare arXiv id
  (pdfdrill downloads/resolves it; never fetch or hand-process it yourself) —
  with a question about its content.
  Always starts shallow (pdfinfo, TOC, abstract) and escalates only when the
  question demands it. State persists in a sidecar JSON next to the PDF, so
  repeated calls accumulate knowledge instead of redoing work.
allowed-tools: [Read, Bash, Write]
---

# pdfdrill

A PDF drill-down toolkit that starts shallow, returns prose, and remembers
what it already knows. The LLM uses small commands; pdfdrill manages the
state machine and the heavy tools underneath.

## ⛔ MANDATORY PREFLIGHT — do this before ANY build/extract command

pdfdrill's output reads as authoritative, so using it **without** the rules
below silently produces WRONG results (bad extraction route, duplicated
equations, a directory treated as a PDF). To make that impossible, build/extract
commands (`model`, `mathpix`, `latex`, `tiddlers`, `semantic`, `make`, …) are
**HARD-BLOCKED** until you attest that you read this SKILL:

1. Run **`pdfdrill preflight`** (it prints the critical rules + checks the env).
2. Read this SKILL **to its very last line** — it ends with an attestation token
   `DRILL-xxxxxxxx` (a checksum of this file: if you can quote it, you read it all).
3. Run **`pdfdrill preflight --ack DRILL-xxxxxxxx`** with that exact token.

Only then do build/extract commands run. Read-only commands (`size`, `pdfinfo`,
`doctor`, `status`, `config`, `steps`, `plan`) stay open so you can bootstrap.
Trusted automation/CI may set `PDFDRILL_NO_PREFLIGHT=1` to skip the gate.

**The distilled rules the token attests you have read:**
1. Pass an identifier (path / https URL / bare arXiv id) as `<pdf>`; pdfdrill
   downloads + resolves it. NEVER `curl`/`wget`/`tar`/`unzip` a PDF or e-print.
2. Start shallow (`size`, `pdfinfo`, `links`, `abstract`) before a model; escalate
   only when the question needs it.
3. A built model can be a different SPECIES (geometry vs math). Trust `status`,
   not the bare `MODEL_BUILT` fact.
4. Never present a math paper as complete without REAL LaTeX. The keyless OCR
   route emits equation *regions* whose text is GARBLED (it cannot read math), so
   an equation COUNT proves nothing; `model` flags `NEEDS_VISION_OCR` — run
   `mathpix`/`visionocr`.
5. One command per step; let pdfdrill manage prerequisites (`--ensure`, `steps`).
6. Read the files pdfdrill writes (`llmtext`, `report`, `tables`) from the drill
   folder; do not re-extract by hand.

## READ FIRST — input & who decides (do not work around pdfdrill)

**You pass an identifier; pdfdrill does the acquisition.** Every command's
`<pdf>` argument accepts, interchangeably:
- a **local file path** (`paper.pdf`, `~/papers/x.pdf`),
- an **https URL** from a known host (`https://arxiv.org/abs/2501.06699`),
- a **bare arXiv id** (`2501.06699`, `math/0309136`).

pdfdrill downloads (once, cached) and resolves it. **NEVER** `curl`/`wget`/
`tar`/`unzip` a PDF or an arXiv e-print yourself, and never read/extract/edit a
`.tex`/`.tgz` by hand. Just hand the URL/id/path to pdfdrill.

**pdfdrill — not you — decides if and when to use the LaTeX source.** For an
arXiv input, `pdfdrill model` / `pdfdrill latex` AUTOMATICALLY fetch the free
e-print `.tgz` and ingest the author's gold LaTeX (equations + TikZ/tables),
keylessly, with no OCR. Your job is one command; pdfdrill's job is the download,
the macro expansion, and the model build.

> **ANTI-PATTERN (this is cheating):** downloading the e-print `.tgz` yourself,
> untarring it, hand-editing the `.tex`, or building a model by hand. If you find
> yourself running `tar`/`curl`/`latexmk`/parsing `.tex`, STOP — call
> `pdfdrill model <id>` (keyless arXiv → builds from the LaTeX source and sets the
> model built so projectors consume it) then `svg` → `tiddlers`/`llmtext`. The
> only sanctioned LaTeX entry points are `pdfdrill latex` / `model` / `latexbook`
> (a local `.tex`/book) / `bibsource` — all of which do the acquisition for you.
> If a paper has no LaTeX source and there is no MathPix key, do NOT fall back to
> an OCR/pdfplumber workaround — wait for a key (or the proper route), as the
> user instructed.

## When to use

- The user gives you a PDF and asks a question about it.
- The user pastes auto-extracted PDF text and you need to verify it.
- The user asks for the abstract, TOC, fonts, or a specific page.

Always run `pdfdrill size` first — it's free, cached, and tells you whether
the auto-extracted text is enough.

## Commands

All commands run via:
`PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]`

Each command returns **prose**, not JSON. Quote it back to the user directly.

### Introspection (fast, no extraction)

| Command | Returns |
|---|---|
| `pdfdrill size <pdf>` | One sentence: page count, MB, producer, **text layer vs. scanned (OCR required)**, encrypted? Detects a scan (no extractable text on page 1, no fonts) and says "NO text layer — scanned, OCR required" + sets `needs_ocr`. |
| `pdfdrill pdfinfo <pdf>` | Full PdfInfo struct (title, author, dates, flags) |
| `pdfdrill bibtex <pdf>` | Derived BibTeX record (auto-chains pdfinfo) |
| `pdfdrill links <pdf>` | **FAST** external URLs via `pdfinfo -url` (~50 ms); flags code/data hosts (github, 4open.science, zenodo, huggingface, …) |
| `pdfdrill urls <pdf>` | URL annotations **with anchor text** — heavier (pdfplumber over all pages, seconds on big PDFs). Use only when you need the visible link text |
| `pdfdrill dests <pdf>` | Named destinations: theorem/equation/section anchors |
| `pdfdrill fonts_layer <pdf>` | Structured per-font records (parsed `pdffonts`) |
| `pdfdrill images <pdf>` | Image rectangles + metadata (pdfplumber + `pdfimages -list`) |
| `pdfdrill fonts <pdf>` | One sentence: font count, math font detection |
| `pdfdrill abstract <pdf>` | Abstract paragraph verbatim, or "not found" |
| `pdfdrill toc <pdf>` | Bulleted section list, or "not found" |
| `pdfdrill status <pdf>` | What I already know about this PDF |

The `dests` command is especially powerful for math papers — it lists every
named anchor in the PDF (theorem.3.1, equation.12, section.4, etc.). Use
this to find structure without running the full Markdown pipeline. The
`urls` command catches arxiv/doi/github links embedded as PDF annotations.
The `bibtex` command derives a partial BibTeX record from the metadata; for
bare LaTeX PDFs it will return mostly empty fields and note what's missing.

### Extraction (does real work)

| Command | Returns |
|---|---|
| `pdfdrill md <pdf>` | Summary sentence + stores full Markdown in sidecar |
| `pdfdrill page <pdf> <n>` | Full text of page N |
| `pdfdrill drill <pdf>` | Runs size → fonts → abstract → toc → md in one call |
| `pdfdrill mathpix <pdf>` | Download MathPix OCR (`lines.json`, `md`, `tex.zip`) next to the PDF; idempotent (skips upload if outputs exist), `--force` re-uploads. `lines.json` is the input to the LaTeX-vs-image comparison pipeline. |

> **Credentials come from the environment / `.env` — don't ask the user mid-task.**
> `mathpix`, `snip`, and `bibfetch` read `MATHPIX_APP_ID` / `MATHPIX_APP_KEY` /
> `PERPLEXITY_API_KEY` from the real environment, falling back to a `.env` file
> at the repo root (real env wins; see `src/pdfdrill/env.py`). `.env` is
> git-ignored; `.env.example` documents the names — `cp .env.example .env` and
> fill in. If a key is genuinely missing the command exits with a one-line
> setup hint (not a deep 401). Most questions need **no** network at all: the
> structural path (`model`, `compare`, `report`, `tiddlers`, `folder`, `latex`,
> …) runs entirely offline from an existing `<name>.lines.json`.

> **Never transcribe math from rendered text — always go through the model.**
> Every structural command runs **offline from an existing
> `<name>.lines.json`** next to the PDF (`model`, `compare`, `report`,
> `tiddlers`, `folder`, …). For an equation/structure question: if a
> `lines.json` exists, `pdfdrill model <pdf>` then query the model — the
> equation numbers, LaTeX and CDN crops are already there (e.g. eq (9)). If no
> `lines.json` exists yet, run `pdfdrill mathpix <pdf>` (keys are bundled, see
> above) to fetch it. Either way the answer comes from MathPix LaTeX + the CDN
> image, never from reading the rendered page.

### Math QC comparison pipeline (LaTeX vs image)

For checking / improving math OCR quality, build the unified model and a
LaTeX | KaTeX | image table, optionally with competing readings:

| Command | Returns |
|---|---|
| `pdfdrill ocr <pdf> [--lang eng+deu] [--min-conf N] [--no-typing]` | **MathPix-free OCR input — aimed at COMMERCIAL documents** (scans, letters, tables, form fields). Ghostscript (≥400 DPI) → tesseract → a MathPix-compatible `<pdf>.lines.json`, so the toolkit runs keyless. Lines are **TYPED** (`section_header`/`table`/`equation`/`diagram`/`page_info`), carry per-line `conf` + `words` + block/par/line, and their regions are **PDF POINTS** (`ocr.units="pt"`, `image_id="tesseract-p{N}"`) → local `/cropped/…&units=pt` pyramid crops work keylessly. Also: language autocorrection, OSD auto-upright, Greek re-OCR of equation regions, a text-layer merge, barcodes. **NO LaTeX** — an equation gets a correct *region* but **garbled text** (tesseract can't read math), so a math paper wants `mathpix`/`visionocr` (`model` flags this as `NEEDS_VISION_OCR`). `--lang eng+deu` for German; `--min-conf` tunes the noise floor; `--no-typing` for the legacy untyped shape. Refuses to overwrite a MathPix `lines.json` without `--force`. |
| `pdfdrill model <pdf>` | Build the unified docmodel from `lines.json` (auto-chains `mathpix`; **falls back to `ocr` (tesseract)** when MathPix is unavailable, so it runs keyless) |
| `pdfdrill snip <pdf> [--limit N]` | OCR each equation crop via MathPix Snip → `snip` column (LaTeX + confidence) |
| `pdfdrill candidates <pdf> [--provider llm]` | Export a manifest of equation crops (`eq_id` + `cdn_url` + MathPix LaTeX) for an LLM to read |
| `pdfdrill ingest <pdf> <json> [--provider llm]` | Attach the reader's `{eq_id, latex}` back as a competing column |
| `pdfdrill vision <pdf> [--limit N]` | **GPT-4o vision** reads every MathPix CDN crop — equation/picture/diagram images **and CDN links MathPix left inside table cells** — returning a `selector` (math/tikzpicture/commutative_diagram/gnuplot/tensor/**table**/empty) + the matching LaTeX/TikZ/tabular, attached as the `openai` provenance. Needs `OPENAI_API_KEY` (env/.env); without it, prints a hint and changes nothing. `--limit` caps API calls (a doc can have 100+ crops). |
| `pdfdrill embedimages <pdf>` | Lift **`pdfimages -list` + `pdfplumber`** embedded raster images into the model as `EmbeddedImage` nodes — true pixel size / encoding / colour / ppi / file size + the page rect (`Region` in PDF points) — and **fuse** each MathPix `Picture`/`Diagram` crop onto the image that contains it (`Alignment(kind="image_region")` + an `embedded_image_id` cross-link). Now every route to an image — MathPix CDN crop, GPT-4o vision read, pdfimages XObject metadata, pdfplumber rect — hangs off one graph node. Runs in the `folder` batch (no key). |
| `pdfdrill compare <pdf>` | Emit `compare.html`: one row per equation, a LaTeX+KaTeX pair per provenance, plus the MathPix image. Each crop **links to its full page**. `--embed` base64-inlines crops; `--force` rebuilds. |
| `pdfdrill report <pdf>` | Emit `formula-report.html`: **every** inline Formula + display Equation as LaTeX source \| KaTeX render (`data-latex`) \| MathPix CDN image. The grounded artifact for "show me equation N"; each crop **links to its full page**. `--embed` makes it self-contained (best for the Claude.ai preview, which may not load remote images); the page link stays live even when embedded. |
| `pdfdrill tiddlers <pdf>` | Emit a TiddlyWiki JSON tiddler array for quick inspection. Equation tiddlers carry `latex`, `displayMode`, `refnum`, `canonical_uri`, `width`/`height`, and competing readings as `latex_<provenance>` — drive a `<$list>`+`<$latex>`+`<$image>` table macro. `--embed` inlines `canonical_uri` as a data: URI. |
| `pdfdrill nlp <pdf> [--limit N] [--pages N] [--types T,T]` | **Optional NLP layer** (Stanza). Runs the neural pipeline (tokenize/POS/lemma/dependency + NER) over each prose object (Paragraph/Abstract/Section/ListItem/Footnote), attaching per-sentence tokens + named entities under `props['nlp']` (raw text untouched). Needs the `[nlp]` extra: `pip install 'pdfdrill[nlp]'` then `python -c "import stanza; stanza.download('en')"`. Without it, prints a friendly install hint and changes nothing. Use `--limit`/`--pages` for quick runs (model load is ~30–40 s). |
| `pdfdrill rasterize <pdf> [--pages N\|N-M\|all] [--dpi] [--fmt png\|jpeg]` | **Visual inspection** — render page(s) to images (`gs`, the only rasterizer, >=400 DPI) into the sidecar and return their paths so you can **Read the image** to see charts/equations/multi-column layout/forms (text extraction is blind to these). ~1,600 tokens per 150-DPI page — rasterize only the pages that matter. |
| `pdfdrill attachments <pdf> [--extract]` | **Embedded file attachments** (`pdfdetach -list`, pypdf fallback) — spreadsheets/data files inside reports/portfolios/PDF-A-3, invisible to text & MathPix. `--extract` saves all to the sidecar (`attachments/`). |
| `pdfdrill formfields <pdf>` | **Interactive AcroForm field values** (pypdf `get_fields`): name / value / type / options for text inputs, checkboxes, radios, dropdowns. For government forms / Formulare / contracts. Flat/scanned forms have no fields → `rasterize` and read visually. |
| `pdfdrill extractimages <pdf> [--pages N-M] [--all-formats]` | **Extract embedded raster image BYTES** to files (`pdfimages -png`/`-all`) so you can Read the figures. Tiny/empty images (masks/decorative) filtered by size. Vector charts (matplotlib/Excel/R) are page operators, not image objects — they won't appear; `rasterize` the page for those. Complements `images`/`embedimages` (metadata only). |
| `pdfdrill tables <pdf> [--pages N-M]` | **Keyless offline table extraction** (pdfplumber `extract_tables`) → `tables.json` + `tables.md`. The no-MathPix/no-vision table path; for garbled output, `rasterize` and read visually. |
| `pdfdrill elements <pdf> [--model M.npz] [--bibkey K] [--source S] [--lang deu+eng] [--ppi 300]` | **Layout-element layer** — a pure-NumPy geometric-attention **GNN** over tesseract word boxes isolates structured elements (postal **address**, **BOM line item**) the way MathPix isolates equations, giving each a content-addressed identity + a TiddlyWiki tiddler (`<bibkey>_AD/BM_<serial>`) with data fields, a `geo-projection`, and (GNN path) a learned `projection` embedding. Writes a `layout` sidecar layer + `<bibkey>.elements.tiddlers.json`. Additive (never touches the docmodel pipeline). **Two routes:** with `--model` the GNN emits addresses **and** BOM-line items (reconciled against the heuristic); **without a model** the vendored `extract_addresses` heuristic still finds **addresses** (German-PLZ anchor + geometry, no model, no libpostal). BOM-line items are GNN-only. Train a model with `python -m pdfdrill.tsv_gcn synth <dir> && python -m pdfdrill.tsv_gcn train <dir>/*.tsv --labels-dir <dir> -o model.npz`. The `[layout]` extra (`pip install 'pdfdrill[layout]'`: numpy + blake3) backs the GNN; the heuristic address path is pure-stdlib. |

The LLM-as-reader loop: run `candidates`, look at each entry's `cdn_url`
image and fill its `latex`, then `ingest`. No API key — the LLM supplies the
vision; pdfdrill just prepares the crops and folds the answers into the model.

### Query stored data

| Command | Returns |
|---|---|
| `pdfdrill fetch <pdf> md` | Full stored Markdown |
| `pdfdrill fetch <pdf> md --section 3` | Just section 3 |
| `pdfdrill fetch <pdf> abstract` | Stored abstract |
| `pdfdrill fetch <pdf> toc` | Stored TOC |
| `pdfdrill plan <pdf> "question"` | Lists what steps would be needed |

### Structure, scan triage, and the semantic layer

| Command | Returns |
|---|---|
| `pdfdrill geometry <pdf>` | Fuse cheap pdftotext word geometry onto the model (indentation/margins) |
| `pdfdrill lists / algorithms / eqnums / annotate / bibliography <pdf>` | Nested lists, algorithm steps, equation numbers, link annotations, references + citation links |
| `pdfdrill bibsource <pdf> --bbl X.bbl --bib X.bib` | GOLD bibliography from the author's compiled files |
| `pdfdrill latex <pdf>` | Author LaTeX (arXiv e-print auto-download): gold equations + TikZ/tables |
| `pdfdrill markdown <md> [--bibkey K]` | Source-only model from LLM-summary Markdown (+ gold ```bibtex appendix) |
| `pdfdrill svg <pdf>` | Render TikZ/tables/chemfig/mhchem to SVG (latex→dvisvgm) |
| `pdfdrill tables <pdf>` | Span-aware tables (keyless) → tables.json/md/**html** (QA) |
| `pdfdrill pageside <pdf>` | recto/verso per page (column roles flip with the book side) |
| `pdfdrill continuity / entities / segment / ordered / autosegment <pdf>` | Multi-document scan triage (margin markers, IBAN/ids, document grouping) |
| `pdfdrill qr / fontid / spellqc <pdf>` | QR/GiroCode payloads, visual font id, de-hyphenation QC |
| `pdfdrill semantic <pdf> [--store g.json]` | Evidence-backed entity/relation graph (accumulates across documents) |
| `pdfdrill gaps <pdf\|md>` | MISSING-information linter: undefined acronyms/symbols, unsupported claims, unmatched citations |
| `pdfdrill rulebook <pdf\|md>` | Claims/definitions → kitems (evidence spans) → rulebook.md with [→k:hash] drill-down |
| `pdfdrill stex <pdf> [--stex] [--compile]` | Enriched LaTeX (acronyms/glossary/symbols/index) or sTeX |
| `pdfdrill scikgtex <pdf> [--compile]` | SciKGTeX LaTeX → PDF carrying ORKG metadata in XMP |
| `pdfdrill translate <pdf> --to EN-US` | DeepL-translate the document IN PLACE (bi-layer md + tiddlers) |
| `pdfdrill doctor` | Which tools/deps/keys are present and what each enables |

## Decision flow

1. **Always start with `size`** — free, takes ~40ms.
2. **For "where is the source code / repo / dataset?"** → `links` (~50 ms).
   It reads the **annotation layer**, so it finds the code link even when it
   has **no visible text** — the usual case for anonymized releases
   (`anonymous.4open.science`). Do **not** reach for `md`/`mathpix` here: they
   read *rendered* text and will miss an annotation-only link entirely. Only
   escalate to `urls` if you need the visible anchor text.
3. **For "what is this paper about?"** → `abstract` is usually enough.
4. **For "what are the sections?"** → `toc`.
5. **For "is there math in this?"** → `fonts` (math fonts mean
   pdfplumber extraction will work; their absence means MathPix may
   be needed for scanned math).
6. **For specific content questions** → run `md`, then `fetch md
   --section N`.
7. **For a single page** → `page <n>` is cheaper than full `md`.
8. **Unsure?** → `plan <pdf> "the question"` shows what steps would run.

### Reach for the cheapest sufficient tool — powerful ≠ right

A heavyweight tool can *miss the point*. "Where is the code?" is answered in
~50 ms by `links` (annotation layer); `urls` re-derives the same link in ~6 s
on a 60-page PDF, and MathPix wouldn't find it at all. Escalate only when a
cheaper command can't answer. The state machine guarantees no wasted work:
every command records cumulative *facts* in the sidecar and returns instantly
if its fact is already set, so a higher-level call never repeats a low-level
step that already ran.

### ⚠️ Uploading a PDF to Claude.ai is NOT enough

When a PDF is attached in the Claude.ai web chat it is silently converted to
**Markdown** (math as Unicode symbols, roughly pdfplumber quality), and the
original PDF — including its **annotation layer** — is never consulted. That
is precisely why LLMs miss annotation-only links like the code URL above.
Always run `pdfdrill` against the **actual PDF file**. For high-fidelity math,
use `pdfdrill mathpix` (`lines.json`), which is far better than the auto-
Markdown and is what the comparison pipeline consumes.

## Example flows

### Flow A — "What is this paper about?"

```bash
pdfdrill size paper.pdf
# → "18-page PDF, 0.2 MB, letter, produced by xdvipdfmx, has a text layer, not encrypted."

pdfdrill abstract paper.pdf
# → "Abstract:\n\nFor a finite planar set P, let ν(P) be the number of..."
```

Quote the abstract back. Done. Two subprocess calls, no extraction.

### Flow B — "What does Section 3 prove?"

```bash
pdfdrill size paper.pdf       # check it's reasonable size
pdfdrill md paper.pdf         # auto-chains size → fonts → md (~1 sec)
# → "Extracted 9175 words across 18 pages. 925 inline, 128 display math, 130 refs."

pdfdrill fetch paper.pdf md --section 3
# → Full Markdown of section 3 with $math$ and {{cite:...}}
```

### Flow C — "How many pages and is there math?"

```bash
pdfdrill size paper.pdf
pdfdrill fonts paper.pdf
# → "Uses 21 font families including math fonts (LMMathSymbols10, MSBM10).
#    pdfplumber extraction will detect math expressions."
```

Two cached calls. Total ~50ms.

### Flow D — "What's on page 7?"

```bash
pdfdrill page paper.pdf 7
# → "Page 7 of 18 (576 words, 49 lines):\n\n[full text]"
```

One pdftotext call. Doesn't build the full layered model.

### Flow E — Coming back later

```bash
pdfdrill status paper.pdf
# → "For paper.pdf I have:
#      size info (18 pages, 0.2 MB)
#      font analysis (math fonts present)
#      abstract extracted
#      Markdown extracted (9175 words)
#    Last action: md. 6 transitions logged."
```

All previous calls are remembered. The sidecar file `paper.pdf.drill.json`
holds the state.

## Sidecar files

For each PDF you process, pdfdrill creates:

- `paper.pdf.drill.json` — small JSON: facts, evidence, transition log
- `paper.pdf.drill/` — directory with heavy blobs (`md.md`, `ir.json`)

Both live **next to the PDF**, same directory. Safe to delete; everything
will be rebuilt on next call.

## Things to avoid

- **Don't** download/`tar`/`curl` a PDF or arXiv e-print yourself, or hand-process
  a `.tex`/`.tgz`. Pass the URL/arXiv-id/path to pdfdrill; it acquires and decides
  if/when to use the LaTeX source (see READ FIRST).
- **Don't** call `pdftotext` or `pdfplumber` directly. pdfdrill knows how
  to call them with the right flags.
- **Don't** delete `*.drill.json` unless you want a fresh start.
- **Don't** run `md` if `abstract` answers the question.
- **Don't** reformat the prose output. It's already LLM-ready.
- **Don't** assume the auto-extracted upload text is complete — run
  `pdfdrill size` and check `text_layer` first.

## Output forms — reading-Markdown vs TiddlyWiki (per-format render)

The docmodel holds the abstract link (Citation → Reference); each output renders
it its OWN way — there is NO single literal transclusion baked into the text:

- **`pdfdrill md` — reading-Markdown:** clean, human/LLM-readable. Inline math
  `$…$`, display `$$…$$`, headings `##`, and citations/refs/eq-numbers in their
  **printed form** (`[18]`, `(5)`, `Theorem 1.1`). The paper's own References
  section is in the text, so `[18]` resolves there by reading. (No `{{cite:…}}`
  pseudo-transclusions — those resolved nowhere and broke the Markdown.)
- **`pdfdrill tiddlers` — TiddlyWiki:** real **templated transclusions** to
  tiddlers: `{{<bibkey>_FO….||FO}}` (formula), `{{<bibkey>_REF_<key>||CIT}}`
  (citation → Reference tiddler), `{{<bibkey>_…||FN}}` (footnote). Import THIS
  into TiddlyWiki — not the Markdown.

When the user asks "what's Theorem 3?", grep the markdown for
`{{ref:Theorem 3}}` to find every site that cites it.

## Routing — pick the right move BEFORE reaching for delegation

LLM delegation (`vision`/`bibfetch`) is a *last-resort* fallback, not the first
move. pdfdrill almost always has a better, deterministic route — use it:

- **Bibliography of an arXiv paper, or ANY doc with the author's `.bbl`+`.bib`:**
  use `pdfdrill bibsource <pdf> --bbl X.bbl --bib X.bib` — the GOLD route. It
  already does the `\bibitem` alpha-label ↔ citekey ↔ field match and links the
  in-text citations. **Do NOT hand-roll a bibitem/bib comparison, and do NOT use
  `bibfetch`** — `bibfetch` (which delegates a web search) is ONLY for *truncated
  printed* references when there is no gold source. (`pdfdrill latex <pdf>`
  auto-downloads the arXiv e-print `.tgz`, so the `.bbl`/`.bib` are right there.)
- **Math equations, MathPix model present (the model has CDN image crops):**
  `pdfdrill vision <pdf>` — with no `OPENAI_API_KEY` it delegates the crops to you.
- **Math equations, MathPix-KEYLESS (no CDN crops):** `vision` has nothing to
  delegate, and the tesseract text layer has NO LaTeX so transclusion breaks.
  Moves, best first:
  * born-digital paper → `pdfdrill latex <pdf>` (the author's GOLD equations, no LLM).
  * to get first-class **Equation nodes** keyless → `pdfdrill visionocr <pdf>`: it
    rasterizes every page and delegates each to YOU (`eq_ocr` request per page);
    you read the page and return a JSON array of `{page, number, latex, kind}` —
    real LaTeX, sub/superscripts preserved, `[]` for a page with no math, never
    fabricated. The records are folded into the lines.json as `equation`/
    `equation_number` lines (paired by geometry) and the model rebuilds. This is
    the route the **`model` gate steers to** (see below).
  * to rebuild the WHOLE page (prose + math) as Markdown → `pdfdrill remath <pdf>`:
    delegates each page with the MathPix-replacement prompt; you re-emit MathPix-
    quality Markdown (inline `\(..\)`, display `$$..$$`) or decline a page
    (`PDFDRILL_CANNOT_RECONSTRUCT`). Then `pdfdrill markdown <key>.mathpix.md`.
  * one-off visual answer (no model change) → `pdfdrill rasterize <pdf>` and READ.

  **DECISION RULE:** *math-bearing PDF + no MathPix key + agent runtime ⇒
  `visionocr` (rasterize → read → ingest), NOT the tesseract model.*
  **ANTI-PATTERN:** *Never report a math paper's model as complete after a keyless
  fallback that captured no real LaTeX.* Note the enriched OCR route DOES emit
  equation objects — correct region, GARBLED text (`Ih=glly <7 =3k € = < | =] (4)`),
  and that text lands in `latex` — so a non-zero equation COUNT is not evidence of
  captured math. A keyless text-only source cannot produce LaTeX by construction;
  only a gold overlay (`latex`) or a keyed route (MathPix/`visionocr`) can.
  `pdfdrill model` detects this, sets `NEEDS_VISION_OCR`, and tells you. Do not
  hand-roll a pseudo-`lines.json` by linearising equations (that yields flattened,
  unusable LaTeX — see `pdfdrill mathcheck`); let `visionocr` keep the structure.

  **ESCAPE LADDER — when a delegated page image is hard to read (do NOT drift to
  `texsrc/` or hallucinate LaTeX; that is finding F8, cheating).** The sanctioned
  moves, in order:
  1. **Crop tighter, same image** — `pdfdrill snip <pdf> --page N --rect
     x0,y0,x1,y1 [--ppi 300]` delivers a higher-resolution crop of the SAME region
     to Read again. Repeat per hard equation. (`snip` delivers the crop even if OCR
     is unavailable.)
  2. **Ingest what you COULD read** — write the equations you managed as a JSON
     array of `{page,number,latex,kind}` and fold them in: `pdfdrill visionocr
     <pdf> --ingest partial.json`. Partial is fine; it keeps real structure.
  3. **Report the rest as PENDING** — the unread pages remain queued as eq_ocr
     requests in `<pdf>.drill/llm/`. Say so plainly ("N eq_ocr requests pending")
     and STOP. A later `pdfdrill visionocr` re-run under Claude Code — or with a
     MathPix/Novita key — completes them, and `inspect`/`report` regenerate with
     full math. A partial, honestly-pending result beats an invented one.

  Likewise, if `pdfdrill inspect` reports the model has NO page geometry (a
  LaTeX-source / prose species), do NOT improvise boxes — follow the message: get
  a geometry-bearing model via `mathpix --force` or `ocr` → `model --force` →
  `inspect`. `model` records `model_caps` (geometry/math/source) so the species is
  never guessed.

So "no LLM call happened" is usually CORRECT: a gold/visual route applied. Only
`bibfetch` (truncated printed refs, no key) and `vision` (MathPix crops, no key)
actually trigger the delegation handshake below.

## Keyless LLM delegation — the sandbox contract (READ THIS before `vision`/`bibfetch`)

Two pdfdrill tasks need a hosted chat-LLM: **`vision`** (an image crop →
LaTeX/TikZ/chemfig — *more than OCR*) and **`bibfetch`** (a truncated reference →
a correct BibTeX by *web search*). When there is **no `OPENAI_API_KEY` /
`PERPLEXITY_API_KEY`** and **no `claude` binary** — i.e. you are in the Claude.ai
code sandbox — pdfdrill **cannot call a model itself**. It does NOT fall back to
tesseract: it is OCR, it cannot consume a prompt and cannot recover
LaTeX/TikZ structure or search the web. **Instead, pdfdrill defers the task to
YOU — the Claude agent running it. You ARE the model.**

The protocol (a deferred file handshake):

1. Run `pdfdrill vision <pdf>` / `pdfdrill bibfetch <pdf>` as normal. With no key
   it prints a `=== PDFDRILL-LLM-DELEGATION ===` block and writes one request per
   task to `<pdf>.drill/llm/<task_id>.req.json` (each: `{kind, prompt,
   image_path, schema}`).
2. Enumerate them: `pdfdrill llm <pdf> --show` (dumps every open prompt at once;
   `pdfdrill llm <pdf> --runtime` confirms it detected `sandbox`).
3. For EACH request, **do the task yourself with your own abilities**:
   - `kind=vision` → **VIEW the image** at `image_path` directly (you can see
     it) and answer the prompt's JSON schema with compilable LaTeX/TikZ. **Do
     NOT run tesseract/pdftotext or any OCR tool** — OCR is the wrong
     tool and a wrong answer; the whole point is the structure OCR can't get.
   - `kind=bibtex`/`links` → **WEB-SEARCH** for the real publication and emit the
     BibTeX / URLs. Do not fabricate.
4. Write the answer to `<pdf>.drill/llm/<task_id>.resp.json` as
   `{"task_id": "<id>", "kind": "<kind>", "result": <object-or-string>}`.
5. **Re-run the same `pdfdrill` command.** It finds the responses, parses them
   into the exact provider shape, and continues — attaching the result identically
   to the API path.

If `pdfdrill llm <pdf> --runtime` says `none` although you ARE in the sandbox,
force the path with `PDFDRILL_DELEGATE=sandbox`. (Never prepare an OCR'd document
to shortcut this — it produces incorrect extractions.)

<!-- COMMANDS:BEGIN (generated by skillsync — do not edit by hand) -->

## Command reference

_Generated from `commands.yaml` by skillsync. Edit the manifest, not this section._

### Introspection (fast, no extraction)

| Command | Returns |
|---|---|
| `pdfdrill doctor` | Requirement check: system tools (poppler/tesseract/LaTeX+dvisvgm), Python deps, API keys + the apt-get fix line |
| `pdfdrill preflight <token> [--ack]` | MANDATORY first step. Prints the critical usage rules + an env check; build/extract commands are hard-blocked until you attest you read the SKILL via `preflight --ack <TOKEN>` (the token is the SKILL's last line). Read-only commands stay open. Automation may set PDFDRILL_NO_PREFLIGHT=1. |
| `pdfdrill config [--init] [--json] [--download-dir] [--library-root]` | Show / init / set the config FILE (not CLI flags): download_dir (where URL/arXiv downloads land) + library_root (the git folder holding one self-contained folder per drilled doc). --init; --json; --download-dir [DIR]; --library-root DIR |
| `pdfdrill relocate <paths> [--apply] [--library]` | Migrate legacy scattered drills into the self-contained library layout: <library>/<stem>/ holding the PDF + every X.* sibling + the flattened X.pdf.drill/ blobs (X.pdf.drill.json → X.drill.json). Dry-run by default; --apply moves. Collision-safe + idempotent. |
| `pdfdrill artifacts <pdf> [--all]` | List the openable files in the doc's drill folder (report.html, the extracted <bibkey>.md, tiddlers/semantic/llm *.json/*.txt, SVGs) with paths — clickable in the drillui Outputs panel. Giant model JSON hidden unless --all. (`status` also lists them.) |
| `pdfdrill size <pdf>` | File size, page count, producer |
| `pdfdrill ls <dir> [--images]` | Shallow-scan a FOLDER: run pdfinfo (size) on every PDF, store it in each file's sidecar, and report a compact table led by the PRODUCER (the triage signal). The cheapest rung over a whole directory; size is cached so re-running is fast. --images adds the pdfimages count. |
| `pdfdrill route <pdf> [--run]` | Auto-pick the OCR lane and (with --run) EXECUTE it: born-digital → pdfminer/text-layer (free); scanned & ≤20 pages → Gemma 4 (5-parallel); scanned & larger → MathPix (large books). Auto-chains size. Without --run reports the decision; with --run runs the chosen lane (paid/keyed lanes degrade gracefully when creds are absent). |
| `pdfdrill abstract <pdf>` | Abstract from first pages |
| `pdfdrill toc <pdf>` | Table of contents |
| `pdfdrill fonts <pdf>` | Font analysis, math font detection |
| `pdfdrill status <pdf>` | What is already known |
| `pdfdrill pdfinfo <pdf>` | Full PdfInfo struct (title/author/dates/flags) |
| `pdfdrill bibtex <pdf>` | Derived BibTeX record from embedded PDF metadata, AUGMENTED by the free arXiv abs-page metadata (title/authors) + the drilled title; warns when still a placeholder (run abstract/model first) |
| `pdfdrill urls <pdf>` | URL annotations with anchor text (heavier; pdfplumber) |
| `pdfdrill links <pdf>` | FAST external URLs via pdfinfo -url (~50ms); flags code/data hosts |
| `pdfdrill dests <pdf>` | Named destinations: theorems, equations, sections |
| `pdfdrill fonts_layer <pdf>` | Structured per-font records (pdffonts) |
| `pdfdrill images <pdf>` | Image rectangles + metadata (pdfplumber + pdfimages -list) |
| `pdfdrill tsv <pdf> [--ocr]` | Word-level bounding boxes (pdftotext -tsv; --ocr forces tesseract) |
| `pdfdrill render <pdf> [--force]` | Render the built markdown to PDF (pandoc + lualatex) |
| `pdfdrill mathpix <pdf> [--force]` | Download MathPix OCR (lines.json, md, tex.zip); --force re-uploads _(network)_ |
| `pdfdrill ocr <pdf> [--lang LANG] [--ppi PPI] [--min-conf MIN_CONF] [--no-typing]` | MathPix-free OCR for COMMERCIAL documents (scans/letters/tables/forms): Ghostscript (>=400 DPI) → tesseract → a MathPix-compatible lines.json. Lines are TYPED (section_header/table/equation/diagram), carry per-line conf + words, and their regions are PDF POINTS (units=pt) so local /cropped/ pyramid crops work keylessly. Language autocorrection, OSD auto-upright, text-layer merge (as a SEPARATE text_layer_text channel), barcodes. NO LaTeX: an equation gets a correct REGION but GARBLED text — math papers want mathpix/visionocr. Refuses to overwrite a MathPix lines.json without --force. |
| `pdfdrill continuity <pdf> [--lang LANG] [--ppi PPI] [--force]` | Full-page OCR of the MARGINS → page-sequence markers (Seite N von M / Fortsetzung) MathPix's content crop drops; attaches seq to Page objects |
| `pdfdrill pageside <pdf>` | Classify each page recto/verso (book left/right) from page-number parity+position + side-note column asymmetry + sequence alternation; attaches page_side to model Pages (column roles flip with the side) |
| `pdfdrill entities <pdf> [--force]` | Commercial entities per page: IBAN (mod-97 validated + BLZ/Konto/bank), BIC, German address, Steuer-/Kassen-/Aktenzeichen. Zero external tools |
| `pdfdrill segment <pdf> [--force]` | Partition a scanned bundle into ordered documents (by sender/identifier + continuity number); flags duplicate copies |
| `pdfdrill elements <pdf> [--model MODEL] [--bibkey BIBKEY] [--source SOURCE] [--lang LANG] [--ppi PPI] [--force]` | Find layout elements (postal address / BOM line) via the geometric-attention GNN over tesseract word boxes → content-addressed tiddlers (--model M.npz) |
| `pdfdrill semantic <pdf> [--store STORE]` | Build the semantic graph (CSP): extractors become sensors emitting evidence; entities (Company/Person/BankAccount) accumulate it. --store graph.json accumulates ACROSS documents |
| `pdfdrill qr <pdf> [--dpi DPI] [--formats FORMATS]` | Scan QR codes & barcodes (zxing-cpp): GiroCode/EPC payment QR (creditor/IBAN/amount/reference) + Data Matrix franking marks — confirmation data outside the text layer. --dpi 300 --formats QRCode,DataMatrix |
| `pdfdrill fontid <pdf> [--pages PAGES] [--limit LIMIT] [--ppi PPI]` | VISUAL font id for scanned/OCR input (no font layer): WORD crops → torch-free ONNX font-classify → vote WITHIN each OCR block, so font is reported per text FIELD (heading/body/fine-print), not one doc vote. Per-field confidence; weak on scanned generic sans. --limit 12 --ppi 200 |
| `pdfdrill spellqc <pdf> [--lang LANG]` | Dictionary-assisted de-hyphenation QC (hunspell via spylls→enchant→.dic-set, on-demand per language): join/keep/REVIEW each line-break hyphen. Surfaces OCR fragments to fix |
| `pdfdrill ordered <pdf> [--threshold THRESHOLD]` | Segment an ORDERED scan stack into documents (gap scoring + DataMatrix tracking codes → 2-level mailing/letter-enclosure). Commercial provenance (publisher=sender, receiver). --threshold 0.5. (Shuffled bundle → use `segment`) |
| `pdfdrill autosegment <pdf> [--threshold THRESHOLD]` | AUTO-PICK ordered vs shuffled: contiguous per-sender runs → `ordered` (gap scorer); interleaved → `segment` (signature grouping). Then runs the right one |
| `pdfdrill selftest <target> [--full]` | DIAGNOSTIC GRID: run the command battery across a PDF (or every PDF in a folder), log OK/⊘-n/a/✗-ERROR + the actual result per command → selftest.log. --full adds entities/elements/semantic |
| `pdfdrill rasterize <pdf> [--pages PAGES] [--dpi DPI] [--fmt png|jpeg] [--force]` | Rasterize page(s) to PNG/JPEG for visual inspection (Ghostscript, >=400 DPI) → sidecar; --pages N\|N-M\|all --dpi 400. Read the images to see charts/equations/layout |
| `pdfdrill attachments <pdf> [--extract]` | List embedded file attachments (pdfdetach + pypdf); --extract saves them to the sidecar. Surfaces embedded spreadsheets/data invisible to text/MathPix |
| `pdfdrill formfields <pdf>` | Read interactive AcroForm field values (pypdf get_fields): name/value/type/options. For government/Formulare PDFs |
| `pdfdrill extractimages <pdf> [--pages PAGES] [--all-formats]` | Extract embedded raster image BYTES to files (pdfimages); tiny masks/decorative <1KB filtered |
| `pdfdrill tables <pdf> [--pages PAGES]` | Extract tables KEYLESS offline (pdfplumber extract_tables) → tables.json + tables.md; --pages N-M |
| `pdfdrill model <pdf> [--bibkey BIBKEY]` | Build unified docmodel from lines.json. No lines.json → MathPix (if key) → arXiv LaTeX source (arXiv) → born-digital text layer (pdfplumber, FREE/fast) → tesseract OCR (scans only). --bibkey KEY sets the tiddler prefix (persisted) |
| `pdfdrill compare <pdf>` | LaTeX \| KaTeX \| MathPix-image comparison HTML (auto-chains model) |
| `pdfdrill snip <pdf> [--image IMAGE] [--page PAGE] [--rect RECT] [--limit LIMIT] [--force] [--gemma] [--provider PROVIDER]` | OCR each equation/table crop → competing column. THE STATE MACHINE picks the provider (vision_router: MathPix when keyed — native promptless OCR — else the cheap Gemma-4 vision route on Novita); --gemma/--provider remain explicit overrides. --limit N _(network)_ |
| `pdfdrill candidates <pdf> [--provider PROVIDER] [--limit LIMIT] [--out OUT]` | Export equation crops as a manifest for an LLM to read; --provider P --limit N |
| `pdfdrill ingest <pdf> <json> [--provider PROVIDER] [--force]` | Attach externally-supplied {eq_id,latex} readings as a competing provenance (grows a compare column) |
| `pdfdrill vision <pdf> [--limit LIMIT] [--force]` | GPT-4o vision reads every MathPix CDN crop (incl. table-cell images) → math/TikZ/gnuplot/table as the `openai` provenance; --limit N (needs OPENAI_API_KEY) _(network)_ |
| `pdfdrill llm <pdf> [--show SHOW] [--runtime RUNTIME]` | Keyless LLM-delegation driver: show detected runtime (cli/sandbox/none) and any pending vision/bibtex/links requests deferred to the running Claude agent; --show dumps open prompts, --runtime prints the runtime only |
| `pdfdrill embedimages <pdf> [--force]` | Lift pdfimages + pdfplumber image rects into the model as EmbeddedImage nodes (pixel size/encoding/ppi + page rect), fused onto MathPix crops they contain |
| `pdfdrill geometry <pdf> [--force]` | Fuse pdftotext -tsv layout (indent/margins) onto the model — substrate for block detection |
| `pdfdrill tiddlers <pdf> [--bibkey BIBKEY] [--embed] [--force] [--no-embed-svg]` | Emit a TiddlyWiki JSON tiddler array (latex/displayMode/canonical_uri/width/height) for quick inspection; --bibkey KEY sets the title prefix + filename. Diagram SVGs inline by default; --embed-svg=false writes them to .drill/svg/<title>.svg and references via _canonical_uri (leaner store) |
| `pdfdrill translate <pdf> [--to TO] [--from FROM_] [--limit LIMIT] [--force]` | DeepL-translate the document IN PLACE (--to EN-US --from RU): writes the changed tiddler file (translated text field) AND a bi-layer Markdown <bibkey>.md (translation + hidden source, CSS toggle); original kept under <field>_source (needs DEEPL_API_KEY) _(network)_ |
| `pdfdrill lists <pdf> [--force]` | Nest flat ListItems into recursive List blocks using fused indentation (auto-chains geometry) |
| `pdfdrill algorithms <pdf> [--force]` | Reconstruct Algorithm blocks from MathPix pseudocode lines (caption + indented steps) |
| `pdfdrill annotate <pdf> [--force]` | Promote hyperlink annotations into the model as first-class Link nodes (uri + rect Region) |
| `pdfdrill score <pdf> [--force]` | Score equations by cross-provenance agreement + snip confidence; flags review candidates |
| `pdfdrill nlp <pdf> [--limit LIMIT] [--pages PAGES] [--types TYPES]` | Stanza NLP over prose (POS/lemma/dependency + NER → props['nlp']); --limit N --pages N --types T,T  (optional [nlp] extra) |
| `pdfdrill escalate <pdf> [--limit LIMIT]` | Phase-3: export flagged equations for a second LLM reading; --limit N |
| `pdfdrill relearn <pdf>` | Phase-3: re-score after ingest; report resolved vs still-flagged |
| `pdfdrill eqnums <pdf> [--force]` | Fuse equation numbers ("(N)") from margin geometry for \|\|FO/\|\|FREF transclusion |
| `pdfdrill bibliography <pdf> [--force]` | Parse the References section into Reference nodes (citekey/author/year/text) |
| `pdfdrill bibsource <pdf> [--bib BIB] [--bbl BBL] [--force]` | Ingest the author's GOLD bibliography (--bbl file.bbl + --bib file.bib): alpha label↔citekey↔fields, links in-text citations by label. No API. |
| `pdfdrill bibfetch <pdf> [--limit LIMIT] [--force]` | Enrich References with full BibTeX via Perplexity SONAR; --limit N (needs PERPLEXITY_API_KEY) _(network)_ |
| `pdfdrill report <pdf> [--scale SCALE] [--embed]` | Full inline+display math report (formula-report.html). --scale N scales each KaTeX render to the CDN image height (1.0=same, 2.0=200%); --embed |
| `pdfdrill inspect <pdf> [--pages PAGES] [--dpi DPI] [--no-images]` | DevTools-style docmodel inspector HTML (<bibkey>.inspect.html): every DocObject as a hover/click box on the rendered page AND a DOM-like ELEMENTS tree + INSPECTOR pane (region/LaTeX/ props/realizations/alignments) + reading-order REFLOW. Self-contained (embeds downscaled pages); --no-images = boxes-only; --dpi N inlined-page DPI (default 120) |
| `pdfdrill folder <dir>` | Build the full structure for every PDF in <dir> from existing |
| `pdfdrill injectlatex <pdf> [--tex TEX]` | INJECT the author's LaTeX source (.tex/.tgz, arXiv e-print auto-downloaded) as a competing `tex` provenance on each matched equation (original+expanded LaTeX). INPUT direction (was `latex`); for LaTeX OUTPUT use `latex`. --tex <path> |
| `pdfdrill merge <pdf> [--tex TEX]` | Merge gold LaTeX prose onto a layout skeleton (MathPix OR born-digital pdfminer/pdfplumber OR tesseract): the model's Paragraphs fix the boundaries + regions, the author LaTeX supplies the text (LaTeX always wins; original kept as text_source). On a born-digital 2-column paper this DROPS the column interleaving + arXiv margin watermark from the prose. Refuses a source-built model (already gold). Needs a model + a LaTeX source. |
| `pdfdrill fontspans <pdf> [--pages PAGES]` | The pdfminer LEG: recover the local formatting MathPix flattens — bold headings, bold/italic key terms, COLOURED runs (red/blue link text), small footnotes/captions — from the born-digital glyph layer via pdfminer.six (fontname/size/CTM/colour). Writes <bibkey>.fontspans.json, attaches per-page emphasis onto Page objects + fuses inline emphasis onto the merged Paragraphs by page-fraction overlap, and cross-checks visual bold+larger headings against the model Sections (confirms matches; flags missed headings as repair candidates). Born-digital only. |
| `pdfdrill latexbook <tex> [--no-svg]` | One-shot source-only pipeline from a .tex book: model + TikZ/table SVGs + KaTeX report (no PDF, no MathPix) |
| `pdfdrill markdown <md>` | Build a source-only model from LLM-summary Markdown (yt2tw route): sections/paragraphs/math/lists + cite{} commands linked to the gold ```bibtex appendix (or the numbered References list). --bibkey K |
| `pdfdrill identifiers <pdf>` | Front-matter scan (scoped by the booktoc offset): checksum-valid ISBN/ISSN/DOI/arXiv + German ids + ALL-CAPS named-entity candidates (publisher/author) |
| `pdfdrill booktoc <pdf>` | Greppable TOC with printed→PDF page alignment (front-matter offset from title↔section matches): grep a chapter/section name → its PDF page |
| `pdfdrill gaps <pdf>` | Report MISSING information (cohomology-as-linter): acronyms used but never expanded, undeclared math symbols, novelty claims without citations, unmatched in-text citations |
| `pdfdrill llmtext <pdf> [--delimiter DELIMITER] [--no-split]` | Flat LLM dump: per unit the tiddler title + paragraph text / formula latex, document order, units split on double line breaks + separated by --delimiter (default %%%%); empty formulas skipped |
| `pdfdrill quantities <pdf>` | Quantitative-layer report: quantities by kind (number/ratio/money/count/ named_metric/derivation), measurements, verification tally (verified/refuted/ uncheckable via VER.EQ.RECOMPUTE) + the top refuted item. Needs `pdfdrill enhance --only quantity,measurement,concepts` first |
| `pdfdrill ask <pdf> <question> [--precision PRECISION] [--json] [--k K]` | STRICT grounded answering (verified-only mode): retrieve top-k units, compose answer parts labeled grounded (span-verified) / derived (VER-recomputed) / proposed (mere retrieval); --precision P withholds proposed parts (and says so); no grounded part → explicit no-grounded-answer, zero paragraphs quoted. On a fresh model it usually WITHHOLDS (nothing is span-verified yet) — for practical question-answering use `retrieve` (grounded context) + synthesis as the primary path; `ask` is the strict verified-only mode. Proof block with witness ids + recompute details; the turn persists via chatlog |
| `pdfdrill mathcheck <pdf> [--limit LIMIT]` | Formula QC: flag FLATTENED formulas (a visual/keyless reconstruction that linearised a 2-D equation instead of LaTeX — subscripts dropped, eq-number mashed in); steers to remath to rebuild |
| `pdfdrill mathir <pdf>` | Canonical math layer: parse each FO/EQ macro-expanded LaTeX into a canonical tree (SymPy, anchored by its srepr) and persist it under props['math'] — first backend of many (Lean4/FriCAS/ Mathematica/SMT-LIB/GraphRAG planned off the same tree). Needs the [math] extra. |
| `pdfdrill conclusion <pdf> [--limit LIMIT]` | Retrieve the document's CONCLUDING paragraphs — the actual outcome (the Abstract gives only goal+method, not results). Finds the conclusion section by a heading heuristic over the TOC/Section captions (strong match before References/Appendix), else the final body paragraphs. |
| `pdfdrill enhance <pdf> [--only ONLY] [--skip SKIP]` | Run the uniform enhancement PASS PIPELINE over the model IR — an ordered, dependency-aware sequence of idempotent passes (frontmatter/math/citation/concepts/abstract/toc/index/summary). Loads the Document once, runs the passes, persists once. Projectors consume the enriched model. |
| `pdfdrill clean <pdf>` | Strip MathPix LaTeX residuals from the model: a leading section* command merged into a paragraph -> the title alone + kind/refnum fields (so semantic analysis sees plain text) |
| `pdfdrill locate <pdf>` | Locate embedded images on their pages (canonical pt/top-left coords + normalized [0,1] + PDF object number), detect full-page/template images, and COMPARE to MathPix regions (IoU) incl. MathPix-only figures |
| `pdfdrill rulebook <pdf> [--force]` | Claims/definitions -> kitems (fixpoint, evidence spans) -> rulebook.md: one supported/accepted statement per line with a [->k:hash] drill-down anchor + kitem tiddlers |
| `pdfdrill svg <pdf> [--limit LIMIT] [--force]` | Render TikZ diagrams + tables to SVG via latex->dvisvgm (KaTeX can't); embeds in the report |
| `pdfdrill stex <pdf> [--stex] [--compile]` | Project the semantic graph to enriched LaTeX: acronyms/glossary/Table-of-Symbols/index (--compile runs lualatex), or sTeX smodule/symdecl/symref (--stex). Needs `semantic` first |
| `pdfdrill pyramid <pdf> [--dpi DPI] [--force] [--offline]` | Build a local 600-DPI Deep-Zoom (DZI) pyramid for the doc (Ghostscript render + pyvips tiling) → <drill>/viewer/ — the MathPix-free image source backing `imageserve` (cdn crop drop-in) + the deep-zoom viewer. Needs ghostscript + pyvips/libvips |
| `pdfdrill imageserve <pdf> [--port PORT] [--dpi DPI] [--background]` | Serve the doc's local pyramid as a MathPix-free image source: a drop-in cdn.mathpix.com (/cropped/<id>?top_left_x=… assembled from the 600-DPI tiles) PLUS the deep-zoom viewer (/viewer.html). Run `pdfdrill pyramid` first. Foreground (Ctrl-C) unless --background. The bun drillui bridge spawns this and proxies /cropped,/tiles,/viewer.html |
| `pdfdrill lean <pdf> [--limit LIMIT] [--force] [--emit-only]` | Export theorems to Lean 4: STORE LLM-generated Lean per Theorem (props/tiddler lean4 field, like bibfetch) then PROJECT <bibkey>.lean from the stored code (sorry-stub if ungenerated). Needs theorem envs from a LaTeX-source build _(network)_ |
| `pdfdrill scikgtex <pdf> [--compile]` | Project to SciKGTeX-annotated LaTeX → compiled PDF carries ORKG contribution metadata (title/authors/field + research-problem/method/result roles + numeric facts + bib-DOI links) as XMP/RDF. --compile (lualatex + vendored scikgtex) |
| `pdfdrill skill [--emit EMIT] [--json] [--check]` | Emit/serve the bundled SKILL folder (--emit DIR \| --json \| --check) |

### Extraction

| Command | Returns |
|---|---|
| `pdfdrill md <pdf> [--pages PAGES]` | Full Markdown with math transclusions |
| `pdfdrill page <pdf> <n>` | Single page text extraction |
| `pdfdrill distill <pdf> [--embed]` | A distill-structured single-file reading view (<bibkey>.distill.html): the Anthropic/Distill v2 article skeleton (named-column grid, runtime TOC, LATE-BOUND ?? figure/eq refs, hover cite/footnote popovers) rebuilt from the docmodel — self-contained, no template JS, KaTeX from data-latex. Auto-chains model; --embed inlines CDN crops. Citation popovers need bibliography/bibsource first (else graceful). |
| `pdfdrill repoinit <dir> [--username USERNAME] [--title TITLE]` | Scaffold a GitHub-repo TiddlyWiki document-set layout (tiddlywiki.info with katex+markdown, package.json, .gitignore, .nojekyll, pdfdrill-repo.json, tiddlers/, files/). Offline; the standalone index.html is built later by `npx tiddlywiki . --output . --build index`. |
| `pdfdrill publish <dir> <pdfs> [--username USERNAME] [--title TITLE]` | Fill a document-set repo from drilled PDFs: export each doc's tiddlers into tiddlers/<bibkey>/ (shared template tiddlers deduped across the set), copy PDFs + tiddlers.json into files/, refresh the Documents landing tiddler + pdfdrill-repo.json. Auto-scaffolds via repoinit. Offline; build index.html afterwards with `npx tiddlywiki . --output . --build index`. |
| `pdfdrill okf <pdf> [--out OUT] [--bibkey BIBKEY] [--semantic]` | Project the docmodel into an OKF (Open Knowledge Format) BUNDLE: one Markdown-with-YAML-frontmatter file per knowledge unit (required `type`) + a reserved index.md, cross-linked by [label](./unit.md) markdown links. OKF is the tiddler bundle re-serialized; the .md files open in drillui like any markdown. Written to <drill>/okf/<bibkey>/ (or --out DIR). |

### Query

| Command | Returns |
|---|---|
| `pdfdrill fetch <pdf> <layer> [--section SECTION]` | Retrieve stored Markdown |
| `pdfdrill occurrences <pdf> [--type TYPE]` | Emit <bibkey>.occurrences.json — a per-element region list (page + top_left_x/y/width/height + tiddler title) for the optional EXTERNAL image-enrichment tools (locate an element on the rendered page by region, no content matching). Region-bearing types only: Equation by default, --type adds Table/ Picture/Diagram. Inline Formula excluded (deduped, no per-object region). |

### Planning & automation

| Command | Returns |
|---|---|
| `pdfdrill plan <pdf> <question> [--goal]` | Show what steps are needed to answer a question — or, with --goal <capability>, the ordered commands to establish that capability, clobber-checked against what the doc already holds (refuses a plan that would rebuild the model and silently destroy a held enrichment like LATEX_INGESTED). |
| `pdfdrill make <pdf> <goal> [--goal]` | Establish a capability GOAL: plan the ordered commands (clobber-checked against what the doc already holds), then execute them — recording proofs, stopping at the first failure. A plan that would rebuild the model and destroy a held enrichment is REFUSED and nothing runs. |
| `pdfdrill drill <pdf> [--full]` | Full auto-drill |
| `pdfdrill steps <cmd> <pdf>` | Show the prerequisite chain for a command (what's done, what --ensure would run) |
| `pdfdrill combine <docs> [--out OUT] [--force]` | Merge several drilled docs into ONE combined store (--out FILE) for MULTI-DOCUMENT chat/retrieve; pools prose/math/concepts, ids namespaced <bibkey>:<id>. Each input must be drilled (model) first |
| `pdfdrill reconcile <pdf> [--mathpix MATHPIX] [--adopt-all]` | Dual-route reconciliation (parallel MathPix + pdfminer.six): keep the pdfminer model's STRUCTURE (citations/figrefs/transclusions/front-matter) + GEOMETRY (self-contained inspect), correct its garbled MATH with MathPix's clean LaTeX, region-matched (per-aspect best-of). Runs the math-garble QC always; adopts MathPix when a `--mathpix LINES.json` source is present (else reports the garble + next step). Geometry never touched; original kept as latex_pdfminer. |
| `pdfdrill context <pdf> <query> [--type TYPE] [--concept CONCEPT] [--section SECTION] [--k K] [--max-tokens MAX-TOKENS] [--aspect ASPECT] [--out OUT]` | Project the docmodel into an LLM CONTEXT (deterministic structural RAG): select typed objects by free-text query + --type/--concept/--section, rank (structural/IDF now; pluggable per-aspect embedding rankers later), render Markdown blocks with metadata + object ids under --max-tokens N. The LLM sees a projection, never the whole doc or a filename. Also accepts a combined store. |
| `pdfdrill retrieve <pdf> <question> [--k K] [--json]` | Transform a question into grounded context: top-k relevant drilled units (the chat-proxy enrichment / future-SKILL seed). Also accepts a COMBINED store (multi-document) |
| `pdfdrill chatlog <pdf> [--question QUESTION] [--answer ANSWER] [--units UNITS] [--model MODEL] [--verdict VERDICT]` | Store one Q&A turn: append the transcript + emit the answer as a kitem in the semantic graph (provenance qid=ask) |

### Other

| Command | Returns |
|---|---|
| `pdfdrill citedrill <pdf> [--limit LIMIT] [--force]` | Drill INTO each citation: find download links (Perplexity + seeded), fetch the cited PDF, stamp drill_status/pdf_url/pdf_json on the Reference |
| `pdfdrill scan <job> [--out-dir OUT_DIR] [--from-dir FROM_DIR] [--device DEVICE] [--title TITLE] [--simplex] [--no-deskew] [--json]` | Acquire paper from the scanner ADF and assemble its lossless PDF (needs the [scan] extra + scanimage; the rig is fixed: ADF duplex @300dpi, deskew measured+applied, raw/ retained, blank sides RECORDED not deleted). Takes no <pdf> — it CREATES one. The job name defaults to a timestamp because it names an acquisition EVENT; the per-document sender-date-type prefix is derived later, after segmentation (one stack is usually several documents). NO OCR layer is added: that would make `route` read the scan as born-digital and pick pdfminer over the vision lane. |
| `pdfdrill docos <command>` | docOS document-set shell (L0 selector): run one command against the persisted working set — cd <path>, add <glob>, remove <glob>, clear, save-set/load-set/sets, show — and print the compact level-gated state UI. No args → show current state. (L1+ materialization wired in later steps.) |
| `pdfdrill classify <pdf> [--k K]` | Subject-classify the drilled doc against the vocabnet vocabularies (MSC discipline rollup + PhySH/GND/STW), persisted in the sidecar. PREREQUISITE: at least one compiled vocab in vocab/compiled/ (not shipped) — build with `python3 -m vocabnet.sources build msc` first; without one it reports the build step and does nothing. |

### Projection / export

| Command | Returns |
|---|---|
| `pdfdrill latex <pdf> [--force] [--compile] [--dump-stages]` | PROJECT the docmodel to LaTeX (<drill>/latex/<bibkey>.tex) — the LaTeX analog of `md`; reads the unified Document, so the SOURCE that built it (MathPix/arXiv/tesseract/textscan) is IRRELEVANT. Resolves transclusion markers ({{id\|\|FO}}→$..$ by array lookup), emits cite commands, builds the bibliography from References (+ a .bib). Compile with XELATEX (not pdflatex — the model can carry raw Unicode ≥ ✓ → ℃); --compile runs it, --dump-stages writes the inspectable stages. OUTPUT direction — for a source use `injectlatex`; for enriched LaTeX (glossary/index, ORKG) use `stex`/`scikgtex`. |
| `pdfdrill beamer <pdf> [--force] [--compile]` | PROJECT the docmodel to a LaTeX **beamer** slide deck (<drill>/latex/<bibkey>.beamer.tex) — one frame per Section (allowframebreaks so long content auto-continues), a title + outline + References frame. Same source-agnostic docmodel projection as `latex` (transclusions, cite commands, lists all resolve), a deck instead of an article. Compile with XELATEX; --compile runs it. |

### OCR / model pipeline

| Command | Returns |
|---|---|
| `pdfdrill remath <pdf> [--pages PAGES] [--force]` | Keyless MathPix replacement: rebuild MathPix-quality Markdown (LaTeX math) from rendered pages via Claude delegation, so transclusion works without a MathPix key |
| `pdfdrill visionocr <pdf> [--ingest INGEST] [--dpi DPI] [--pages PAGES] [--force]` | Keyless agent-delegated EQUATION OCR: rasterize each page → the running Claude reads the math → fold {page,number,latex,kind} records into the lines.json as real Equation nodes (number paired by geometry). The keyless math route when tesseract built a doc prose-only (NEEDS_VISION_OCR) |

<!-- COMMANDS:END -->

<!-- PREFLIGHT-TOKEN:BEGIN -->
Attestation token — the LAST line of this SKILL. If you can read this, you read the whole file. Run `pdfdrill preflight --ack DRILL-f17fe4db` before any build/extract command.
DRILL-f17fe4db
<!-- PREFLIGHT-TOKEN:END -->
