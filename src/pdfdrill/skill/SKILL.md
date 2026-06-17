---
name: pdfdrill
description: |
  Token-economical drill-down extraction from PDF documents. Use whenever
  the user provides a PDF (URL or upload) with a question about its content.
  Always starts shallow (pdfinfo, TOC, abstract) and escalates only when the
  question demands it. State persists in a sidecar JSON next to the PDF, so
  repeated calls accumulate knowledge instead of redoing work.
allowed-tools: [Read, Bash, Write]
---

# pdfdrill

A PDF drill-down toolkit that starts shallow, returns prose, and remembers
what it already knows. The LLM uses small commands; pdfdrill manages the
state machine and the heavy tools underneath.

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
| `pdfdrill pix2tex <pdf>` | OCR rasterized equations via pix2tex (auto candidates) |
| `pdfdrill pix2tex <pdf> --page N --rect x0,y0,x1,y1` | Force OCR a specific crop |
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
| `pdfdrill ocr <pdf> [--lang eng] [--ppi 300]` | **MathPix-free OCR input.** Render pages → tesseract → a MathPix-compatible `<pdf>.lines.json` (so the whole toolkit runs without a key). Reuses the TSV word-geometry + line-grouping already in `geometry.py`. **Plain text only** — no LaTeX, no equation/figure typing, no CDN crops (math fidelity stays MathPix-only). `--lang eng+equ` for math glyphs, `eng+deu` for German. Refuses to overwrite a MathPix `lines.json` without `--force`. |
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
| `pdfdrill rasterize <pdf> [--pages N\|N-M\|all] [--dpi 150] [--fmt png\|jpeg]` | **Visual inspection** — render page(s) to images (`pdftoppm`) into the sidecar and return their paths so you can **Read the image** to see charts/equations/multi-column layout/forms (text extraction is blind to these). ~1,600 tokens per 150-DPI page — rasterize only the pages that matter. |
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

- **Don't** call `pdftotext` or `pdfplumber` directly. pdfdrill knows how
  to call them with the right flags.
- **Don't** delete `*.drill.json` unless you want a fresh start.
- **Don't** run `md` if `abstract` answers the question.
- **Don't** reformat the prose output. It's already LLM-ready.
- **Don't** assume the auto-extracted upload text is complete — run
  `pdfdrill size` and check `text_layer` first.

## Working with transclusions in the output

The Markdown output uses transclusion syntax for non-textual references:

- `$\nu(P)$` — inline math (LaTeX)
- `$$...$$` — display math
- `{{cite:[Erd46]}}` — bibliography citation
- `{{ref:Theorem 1.1}}` — structural reference
- `{{eq:5}}` — equation number reference

When the user asks "what's Theorem 3?", grep the markdown for
`{{ref:Theorem 3}}` to find every site that cites it.

<!-- COMMANDS:BEGIN (generated by skillsync — do not edit by hand) -->

## Command reference

_Generated from `commands.yaml` by skillsync. Edit the manifest, not this section._

### Introspection (fast, no extraction)

| Command | Returns |
|---|---|
| `pdfdrill doctor` | (doctor) |
| `pdfdrill size <pdf>` | File size, page count, producer |
| `pdfdrill abstract <pdf>` | Abstract from first pages |
| `pdfdrill toc <pdf>` | Table of contents |
| `pdfdrill fonts <pdf>` | Font analysis, math font detection |
| `pdfdrill status <pdf>` | What is already known |
| `pdfdrill pdfinfo <pdf>` | Full PdfInfo struct (title/author/dates/flags) |
| `pdfdrill bibtex <pdf>` | Derived BibTeX record |
| `pdfdrill urls <pdf>` | URL annotations with anchor text (heavier; pdfplumber) |
| `pdfdrill links <pdf>` | FAST external URLs via pdfinfo -url (~50ms); flags code/data hosts |
| `pdfdrill dests <pdf>` | Named destinations: theorems, equations, sections |
| `pdfdrill fonts_layer <pdf>` | Structured per-font records (pdffonts) |
| `pdfdrill images <pdf>` | Image rectangles + metadata (pdfplumber + pdfimages -list) |
| `pdfdrill pix2tex <pdf> [--page PAGE] [--rect RECT] [--rerun]` | Run pix2tex on candidate rects (auto from images_layer) |
| `pdfdrill tsv <pdf>` | Word-level bounding boxes (pdftotext -tsv; --ocr forces tesseract) |
| `pdfdrill render <pdf>` | Render the built markdown to PDF (pandoc + lualatex) |
| `pdfdrill mathpix <pdf> [--force]` | Download MathPix OCR (lines.json, md, tex.zip); --force re-uploads _(network)_ |
| `pdfdrill ocr <pdf> [--lang LANG] [--ppi PPI]` | MathPix-free OCR: tesseract → MathPix-compatible lines.json (--lang eng+equ, --ppi N). Plain text only (no LaTeX/CDN) |
| `pdfdrill continuity <pdf>` | Full-page OCR of the MARGINS → page-sequence markers (Seite N von M / Fortsetzung) MathPix's content crop drops; attaches seq to Page objects |
| `pdfdrill pageside <pdf>` | Classify each page recto/verso (book left/right) from page-number parity+position + side-note column asymmetry + sequence alternation; attaches page_side to model Pages (column roles flip with the side) |
| `pdfdrill entities <pdf>` | Commercial entities per page: IBAN (mod-97 validated + BLZ/Konto/bank), BIC, German address, Steuer-/Kassen-/Aktenzeichen. Zero external tools |
| `pdfdrill segment <pdf>` | Partition a scanned bundle into ordered documents (by sender/identifier + continuity number); flags duplicate copies |
| `pdfdrill elements <pdf>` | Find layout elements (postal address / BOM line) via the geometric-attention GNN over tesseract word boxes → content-addressed tiddlers (--model M.npz) |
| `pdfdrill semantic <pdf> [--store STORE]` | Build the semantic graph (CSP): extractors become sensors emitting evidence; entities (Company/Person/BankAccount) accumulate it. --store graph.json accumulates ACROSS documents |
| `pdfdrill qr <pdf> [--dpi DPI] [--formats FORMATS]` | Scan QR codes & barcodes (zxing-cpp): GiroCode/EPC payment QR (creditor/IBAN/amount/reference) + Data Matrix franking marks — confirmation data outside the text layer. --dpi 300 --formats QRCode,DataMatrix |
| `pdfdrill fontid <pdf>` | VISUAL font id for scanned/OCR input (no font layer): WORD crops → torch-free ONNX font-classify → vote WITHIN each OCR block, so font is reported per text FIELD (heading/body/fine-print), not one doc vote. Per-field confidence; weak on scanned generic sans. --limit 12 --ppi 200 |
| `pdfdrill spellqc <pdf>` | Dictionary-assisted de-hyphenation QC (hunspell via spylls→enchant→.dic-set, on-demand per language): join/keep/REVIEW each line-break hyphen. Surfaces OCR fragments to fix |
| `pdfdrill ordered <pdf>` | Segment an ORDERED scan stack into documents (gap scoring + DataMatrix tracking codes → 2-level mailing/letter-enclosure). Commercial provenance (publisher=sender, receiver). --threshold 0.5. (Shuffled bundle → use `segment`) |
| `pdfdrill autosegment <pdf>` | AUTO-PICK ordered vs shuffled: contiguous per-sender runs → `ordered` (gap scorer); interleaved → `segment` (signature grouping). Then runs the right one |
| `pdfdrill selftest <target> [--full]` | DIAGNOSTIC GRID: run the command battery across a PDF (or every PDF in a folder), log OK/⊘-n/a/✗-ERROR + the actual result per command → selftest.log. --full adds entities/elements/semantic |
| `pdfdrill rasterize <pdf> [--pages PAGES] [--dpi DPI] [--fmt png|jpeg] [--force]` | Rasterize page(s) to PNG/JPEG for visual inspection (pdftoppm) → sidecar; --pages N\|N-M\|all --dpi 150. Read the images to see charts/equations/layout |
| `pdfdrill attachments <pdf> [--extract]` | List embedded file attachments (pdfdetach + pypdf); --extract saves them to the sidecar. Surfaces embedded spreadsheets/data invisible to text/MathPix |
| `pdfdrill formfields <pdf>` | Read interactive AcroForm field values (pypdf get_fields): name/value/type/options. For government/Formulare PDFs |
| `pdfdrill extractimages <pdf> [--pages PAGES] [--all-formats]` | (extractimages) |
| `pdfdrill tables <pdf> [--pages PAGES]` | Extract tables KEYLESS offline (pdfplumber extract_tables) → tables.json + tables.md; --pages N-M |
| `pdfdrill model <pdf> [--bibkey BIBKEY]` | Build unified docmodel from lines.json (auto-chains mathpix, falls back to tesseract ocr if no MathPix); --bibkey KEY sets the tiddler prefix (persisted) |
| `pdfdrill compare <pdf>` | LaTeX \| KaTeX \| MathPix-image comparison HTML (auto-chains model) |
| `pdfdrill snip <pdf> [--image IMAGE] [--page PAGE] [--rect RECT] [--limit LIMIT] [--force]` | OCR each equation crop via MathPix Snip (/v3/text) → competing column; --limit N _(network)_ |
| `pdfdrill candidates <pdf>` | Export equation crops as a manifest for an LLM to read; --provider P --limit N |
| `pdfdrill ingest <pdf> <json> [--provider PROVIDER] [--force]` | (ingest) |
| `pdfdrill vision <pdf>` | GPT-4o vision reads every MathPix CDN crop (incl. table-cell images) → math/TikZ/gnuplot/table as the `openai` provenance; --limit N (needs OPENAI_API_KEY) _(network)_ |
| `pdfdrill embedimages <pdf>` | Lift pdfimages + pdfplumber image rects into the model as EmbeddedImage nodes (pixel size/encoding/ppi + page rect), fused onto MathPix crops they contain |
| `pdfdrill geometry <pdf>` | Fuse pdftotext -tsv layout (indent/margins) onto the model — substrate for block detection |
| `pdfdrill tiddlers <pdf> [--bibkey BIBKEY] [--embed] [--force] [--no-embed-svg]` | Emit a TiddlyWiki JSON tiddler array (latex/displayMode/canonical_uri/width/height) for quick inspection; --bibkey KEY sets the title prefix + filename. Diagram SVGs inline by default; --embed-svg=false writes them to .drill/svg/<title>.svg and references via _canonical_uri (leaner store) |
| `pdfdrill translate <pdf> [--to TO] [--from FROM_] [--limit LIMIT] [--force]` | DeepL-translate the document IN PLACE (--to EN-US --from RU): writes the changed tiddler file (translated text field) AND a bi-layer Markdown <bibkey>.md (translation + hidden source, CSS toggle); original kept under <field>_source (needs DEEPL_API_KEY) _(network)_ |
| `pdfdrill lists <pdf>` | Nest flat ListItems into recursive List blocks using fused indentation (auto-chains geometry) |
| `pdfdrill algorithms <pdf>` | Reconstruct Algorithm blocks from MathPix pseudocode lines (caption + indented steps) |
| `pdfdrill annotate <pdf>` | Promote hyperlink annotations into the model as first-class Link nodes (uri + rect Region) |
| `pdfdrill score <pdf>` | Score equations by cross-provenance agreement + snip confidence; flags review candidates |
| `pdfdrill nlp <pdf> [--limit LIMIT] [--pages PAGES] [--types TYPES]` | Stanza NLP over prose (POS/lemma/dependency + NER → props['nlp']); --limit N --pages N --types T,T  (optional [nlp] extra) |
| `pdfdrill escalate <pdf>` | Phase-3: export flagged equations for a second LLM reading; --limit N |
| `pdfdrill relearn <pdf>` | Phase-3: re-score after ingest; report resolved vs still-flagged |
| `pdfdrill eqnums <pdf>` | Fuse equation numbers ("(N)") from margin geometry for \|\|FO/\|\|FREF transclusion |
| `pdfdrill bibliography <pdf>` | Parse the References section into Reference nodes (citekey/author/year/text) |
| `pdfdrill bibsource <pdf>` | Ingest the author's GOLD bibliography (--bbl file.bbl + --bib file.bib): alpha label↔citekey↔fields, links in-text citations by label. No API. |
| `pdfdrill bibfetch <pdf>` | Enrich References with full BibTeX via Perplexity SONAR; --limit N (needs PERPLEXITY_API_KEY) _(network)_ |
| `pdfdrill report <pdf> [--scale SCALE] [--embed]` | Full inline+display math report (formula-report.html). --scale N scales each KaTeX render to the CDN image height (1.0=same, 2.0=200%); --embed |
| `pdfdrill folder <dir>` | Build the full structure for every PDF in <dir> from existing |
| `pdfdrill latex <pdf> [--tex TEX]` | Ingest author .tex/.tgz as a `tex` provenance (original+expanded LaTeX); --tex <path> |
| `pdfdrill latexbook <tex> [--no-svg]` | (latexbook) |
| `pdfdrill markdown <md>` | Build a source-only model from LLM-summary Markdown (yt2tw route): sections/paragraphs/math/lists + cite{} commands linked to the gold ```bibtex appendix (or the numbered References list). --bibkey K |
| `pdfdrill identifiers <pdf>` | Front-matter scan (scoped by the booktoc offset): checksum-valid ISBN/ISSN/DOI/arXiv + German ids + ALL-CAPS named-entity candidates (publisher/author) |
| `pdfdrill booktoc <pdf>` | Greppable TOC with printed→PDF page alignment (front-matter offset from title↔section matches): grep a chapter/section name → its PDF page |
| `pdfdrill gaps <pdf|md>` | Report MISSING information (cohomology-as-linter): acronyms used but never expanded, undeclared math symbols, novelty claims without citations, unmatched in-text citations |
| `pdfdrill llmtext <pdf|md>` | Flat LLM dump: per unit the tiddler title + paragraph text / formula latex, document order, units split on double line breaks + separated by --delimiter (default %%%%); empty formulas skipped |
| `pdfdrill clean <pdf|md>` | Strip MathPix LaTeX residuals from the model: a leading section* command merged into a paragraph -> the title alone + kind/refnum fields (so semantic analysis sees plain text) |
| `pdfdrill locate <pdf>` | Locate embedded images on their pages (canonical pt/top-left coords + normalized [0,1] + PDF object number), detect full-page/template images, and COMPARE to MathPix regions (IoU) incl. MathPix-only figures |
| `pdfdrill rulebook <pdf|md>` | Claims/definitions -> kitems (fixpoint, evidence spans) -> rulebook.md: one supported/accepted statement per line with a [->k:hash] drill-down anchor + kitem tiddlers |
| `pdfdrill svg <pdf|tex>` | Render TikZ diagrams + tables to SVG via latex->dvisvgm (KaTeX can't); embeds in the report |
| `pdfdrill stex <pdf>` | Project the semantic graph to enriched LaTeX: acronyms/glossary/Table-of-Symbols/index (--compile runs lualatex), or sTeX smodule/symdecl/symref (--stex). Needs `semantic` first |
| `pdfdrill scikgtex <pdf>` | Project to SciKGTeX-annotated LaTeX → compiled PDF carries ORKG contribution metadata (title/authors/field + research-problem/method/result roles + numeric facts + bib-DOI links) as XMP/RDF. --compile (lualatex + vendored scikgtex) |
| `pdfdrill skill [--emit EMIT] [--json] [--check]` | Emit/serve the bundled SKILL folder (--emit DIR \| --json \| --check) |

### Extraction

| Command | Returns |
|---|---|
| `pdfdrill md <pdf> [--pages PAGES]` | Full Markdown with math transclusions |
| `pdfdrill page <pdf> <n>` | Single page text extraction |

### Query

| Command | Returns |
|---|---|
| `pdfdrill fetch <pdf> <layer> [--section SECTION]` | Retrieve stored Markdown |

### Planning & automation

| Command | Returns |
|---|---|
| `pdfdrill plan <pdf> <question>` | Show what steps are needed |
| `pdfdrill drill <pdf>` | Full auto-drill |
| `pdfdrill steps <cmd> <pdf>` | Show the prerequisite chain for a command (what's done, what --ensure would run) |

### Other

| Command | Returns |
|---|---|
| `pdfdrill citedrill` | (citedrill) |
| `pdfdrill classify` | (classify) |

<!-- COMMANDS:END -->
