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
| `pdfdrill compare <pdf>` | Emit `compare.html`: one row per equation, a LaTeX+KaTeX pair per provenance, plus the MathPix image. Each crop **links to its full page**. `--embed` base64-inlines crops; `--force` rebuilds. |
| `pdfdrill report <pdf>` | Emit `formula-report.html`: **every** inline Formula + display Equation as LaTeX source \| KaTeX render (`data-latex`) \| MathPix CDN image. The grounded artifact for "show me equation N"; each crop **links to its full page**. `--embed` makes it self-contained (best for the Claude.ai preview, which may not load remote images); the page link stays live even when embedded. |
| `pdfdrill tiddlers <pdf>` | Emit a TiddlyWiki JSON tiddler array for quick inspection. Equation tiddlers carry `latex`, `displayMode`, `refnum`, `canonical_uri`, `width`/`height`, and competing readings as `latex_<provenance>` — drive a `<$list>`+`<$latex>`+`<$image>` table macro. `--embed` inlines `canonical_uri` as a data: URI. |
| `pdfdrill nlp <pdf> [--limit N] [--pages N] [--types T,T]` | **Optional NLP layer** (Stanza). Runs the neural pipeline (tokenize/POS/lemma/dependency + NER) over each prose object (Paragraph/Abstract/Section/ListItem/Footnote), attaching per-sentence tokens + named entities under `props['nlp']` (raw text untouched). Needs the `[nlp]` extra: `pip install 'pdfdrill[nlp]'` then `python -c "import stanza; stanza.download('en')"`. Without it, prints a friendly install hint and changes nothing. Use `--limit`/`--pages` for quick runs (model load is ~30–40 s). |

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
