# pdfdrill

**Token-economical drill-down extraction + PDF→LaTeX OCR quality control.**

🔗 **Project page:** <https://pdfdrill.github.io>

`pdfdrill` is a flat CLI that returns prose, persists state in a sidecar next
to each PDF, and wraps the heavy tools (poppler, pdfplumber) so an LLM can
drill into a document with the cheapest sufficient command. It is paired with
a unified document model (`docmodel`) and an operator pipeline (`docops`) that
turn MathPix `lines.json` into a typed `Document` and emit QC artifacts — a
LaTeX | KaTeX | MathPix-image comparison table, a full formula report, and
TiddlyWiki tiddlers.

## Interfaces (five ways to drive it)

| # | Interface | Entry point | For |
|---|-----------|-------------|-----|
| 1 | **CLI** | `pdfdrill <cmd> <pdf>` (or `python -m pdfdrill`) | scripts, agents, the SKILL |
| 2 | **drillui terminal** | `bun tools/drillui_bridge.ts` → browser at `:8787` (spawns `tools/drillui_chat.py`, serves `tools/drillui_term.html`) | interactive ask-the-document chat in a browser terminal |
| 3 | **MCP — stdio** | `tools/pdfdrill_mcp.py` | Claude Desktop / Claude Code (local) — results as MCP resources |
| 4 | **MCP — Streamable HTTP** | `tools/pdfdrill_mcp_http.py` → `https://<host>/mcp` | claude.ai web **custom connector** |
| 5 | **Batch** | `tools/drillbatch.py` | drill a list of URLs/ids shallow→deep; `--list-outputs` |

drillui details → [`tools/DRILLUI.md`](tools/DRILLUI.md); MCP details →
[`tools/MCP.md`](tools/MCP.md). All UI/server files have ONE canonical copy, in
`tools/`.

## Install

System prerequisites (not pip-installable): **poppler-utils** (core),
**tesseract-ocr** (keyless OCR route), and the **LaTeX DVI toolchain +
dvisvgm** (TikZ/table/chemistry SVG rendering). `bash bootstrap.sh` installs
whatever is missing via apt-get; `pdfdrill doctor` reports the state anytime.

```bash
apt-get install poppler-utils      # Debian/Ubuntu
dnf install poppler-utils          # Fedora
eopkg install poppler              # Solus
brew install poppler               # macOS
```

Then:

```bash
pip install -e .                   # installs the `pdfdrill` console script
# or, for the offline path only:
pip install -r requirements.txt
```

## Quick start

```bash
pdfdrill size  paper.pdf           # one-sentence metadata (~40 ms)
pdfdrill links paper.pdf           # external URLs from the annotation layer,
                                   #   flags code/data hosts (~50 ms)
pdfdrill model paper.pdf           # build the unified docmodel from lines.json
pdfdrill compare paper.pdf         # LaTeX | KaTeX | MathPix-image QC table
pdfdrill report  paper.pdf         # full inline+display formula report
pdfdrill tiddlers paper.pdf        # TiddlyWiki tiddler array (--bibkey KEY sets the prefix)
pdfdrill translate paper.pdf --from DE --to EN-US   # DeepL-translate prose tiddlers
pdfdrill folder  ./papers          # batch-build every PDF that already has a
                                   #   sibling .lines.json — no network calls
pdfdrill markdown summary.md       # source-only model from LLM-summary Markdown
                                   #   (+ gold ```bibtex appendix)
pdfdrill tables  paper.pdf         # span-aware tables (keyless) + tables.html QA
pdfdrill semantic paper.pdf        # evidence-backed entity/relation graph
pdfdrill gaps    paper.pdf         # MISSING-information linter (acronyms/symbols/
                                   #   claims/citations)
pdfdrill rulebook paper.pdf        # claims/definitions -> kitems -> rulebook.md
                                   #   with [→k:hash] drill-down anchors
```

Every command's `<pdf>` argument is, interchangeably, a **local file path**, an
**https URL from a known host**, or a **bare arXiv id** (`pdfdrill model
2510.11170v2`) — downloaded once, cached. **pdfdrill does the acquisition and
decides if/when to use the LaTeX source**: for an arXiv input the abstract and
the author LaTeX come from the **free** routes (`latex`/`model` auto-download the
e-print `.tgz` and ingest the gold equations, keyless, no MathPix). Pass the
URL/id/path and let pdfdrill fetch it — **never `curl`/`wget`/`tar` a PDF or
e-print yourself, and never hand-process a `.tex`/`.tgz`**.

Without the installed console script, run as a module:

```bash
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
```

## Projections — one docmodel, many outputs

The unified docmodel is the canonical IR; every projection is **codegen** from it
(build the model once with `pdfdrill model`, then project). Each is a single
command that writes into the doc's `.drill/` sidecar:

| Command | Output | What it is |
|---|---|---|
| `pdfdrill md <pdf>` | `<bibkey>.md` | LLM-compact Markdown with materialized math transclusions (bi-layer source+translation after `translate`) |
| `pdfdrill llmtext <pdf>` | `<bibkey>.llm.txt` | Flat LLM dump — one unit per block, tiddler-titled, document order |
| `pdfdrill context <pdf> "q" [--type …]` | stdout / `--out` | **Deterministic structural RAG**: select typed objects by query/`--type`/`--section`/`--concept`, ranked, with a token budget |
| `pdfdrill tiddlers <pdf>` | `<bibkey>.tiddlers.json` | TiddlyWiki tiddler array (bibkey-prefixed titles; `<$latex>`/transclusions/SVG) |
| `pdfdrill okf <pdf> [--semantic]` | `okf/<bibkey>/*.md` | **Open Knowledge Format** bundle — one Markdown-with-frontmatter file per unit in per-type folders, relative links; `--semantic` projects the entity graph (Company/BankAccount/…) instead |
| `pdfdrill distill <pdf>` | `<bibkey>.distill.html` | **Distill-structured** single-file reading view (named-column grid, runtime TOC, late-bound `??` figure refs, hover citations, hard-dark, KaTeX) |
| `pdfdrill report <pdf>` | `formula-report.html` | Inline+display formula report (LaTeX \| KaTeX \| MathPix image) |
| `pdfdrill compare <pdf>` | `compare.html` | LaTeX \| KaTeX \| image comparison **across competing provenances** (MathPix/snip/vision/tex) + scores |
| `pdfdrill inspect <pdf>` | `<bibkey>.inspect.html` | DevTools-style docmodel inspector — every object a hover/click box, self-contained via the pdfminer route |
| `pdfdrill scikgtex <pdf> [--compile]` | `<bibkey>.scikg.tex` | SciKGTeX-annotated LaTeX → compiled PDF carries **ORKG** contribution metadata as XMP/RDF |
| `pdfdrill stex <pdf> [--stex]` | `<bibkey>.glossaries.tex` / `.stex.tex` | Enriched LaTeX / **sTeX** — acronyms, glossary, table-of-symbols, index from the named-concept layer |
| `pdfdrill lean <pdf>` | `<bibkey>.lean` | **Lean 4** export of theorems (LLM-generated Lean stored per Theorem, then projected) |

HTML projections accept `--embed` to base64-inline every CDN crop (fully
self-contained); the `.distill.html`, `.inspect.html`, `report.html` and the
`okf/` bundle all open directly in drillui's Outputs panel.

### The killer case

`pdfdrill links` reads the PDF **annotation layer**, so it finds hyperlinks
that have no visible anchor text — e.g. a paper whose page-1 text says only
*"Our code is available here."* where *here* is a link. The URL never appears
in any rendered-text stream (plain extraction, Markdown, or a chatbot upload
all drop it); `links` surfaces it in ~50 ms.

### Translating a document (DeepL, in place)

`pdfdrill translate <pdf> [--from RU] [--to EN-US] [--limit N] [--force]`
translates the document **in place**: the model prose is translated (original
preserved under `<field>_source`), the bi-layer Markdown `<bibkey>.md` is
re-projected (translation shown, original behind a show-source toggle), and
the tiddler file is rewritten in place — `text` carries the translation,
`text_source` the original. Math/code/image objects are untouched; re-runs are
idempotent. Needs `DEEPL_API_KEY` (see **API keys** below).

## Publish a document set to GitHub Pages

Turn a drilled set into a standalone TiddlyWiki served from github.io:

    pdfdrill repoinit <repo> --username <you> --title "My Set"
    pdfdrill tiddlers <pdf>          # per document (produces <bibkey>.tiddlers.json)
    pdfdrill publish <repo> <pdf> …  # export tiddlers -> tiddlers/, PDFs -> files/
    cd <repo> && npm i tiddlywiki && npx tiddlywiki . --output . --build index
    git init && git add -A && git commit -m "my set"
    gh repo create <repo> --public --source=. --push       # from your own machine
    gh api -X POST repos/<you>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'

Live at `https://<you>.github.io/<repo>/`. In the Claude.ai sandbox the
`docset-publish` SKILL runs build → tar; you push from your own machine (no
credential ever enters the sandbox). A one-time navigator on `<you>.github.io`
auto-lists every doc-set repo.

## Feature extraction (`src/features/`)

`src/features/` is a small **additive** layer of **source-agnostic** extractors:
each `extract(text, page_id="") -> list[Feature]` takes plain text and emits flat
`Feature` objects, with flat `Relation` edges and a NetworkX `build_graph`. There
is **no standalone `pdfdrill features` command**, but the extractors are now
consumed by several commands — `identifiers` (ISBN/DOI/ids + author matching),
`entities` (IBAN/BIC/German address/ids), `spellqc` and `semantic` (language
detection).

```bash
pip install '.[features]'                      # dateparser, phonenumbers, price-parser, …
PYTHONPATH=src python3 -m features invoice.txt # → JSON of EMAIL/URL/DOI/DATE/PHONE/PRICE/… features
```

Always-on (regex / checksum, no deps): `EMAIL`, `URL`, `DOI`, `IBAN`, `BIC`,
`ISBN`/`ISSN`, German admin `ids`, `LANGUAGE`. Library-backed (degrade to nothing
when the dep is absent): `DATE` (dateparser), `PHONE` (phonenumbers), `PRICE`
(price-parser), `PERSON_NAME` (probablepeople), `ADDRESS` (usaddress);
`match_entities` (rapidfuzz) links OCR-typo/invoice/company duplicates as
`SAME_AS` relations. Two read-only audits ship too:
`python -m features.audit_deps` (module dependency graph) and
`python -m features.audit_nested` (nested-container findings).

## Layout

- `src/pdfdrill/` — the CLI toolkit, sidecar state machine, and capture layer.
- `src/docmodel/` — the unified document-object model (`Stream` / `Anchor` /
  `Realization` / `Alignment` / `Region`), built from MathPix `lines.json`.
- `src/docops/` — `Mutator`s and `Projector`s over a `Document` (plaintext,
  LLM-compact markdown, TiddlyWiki, comparison table, formula report).
- `src/features/` — additive, source-agnostic feature extractors: flat
  `Feature`/`Relation`, a registry, and a NetworkX graph builder. No standalone
  command; consumed by `identifiers`/`entities`/`spellqc`/`semantic`.
- `src/semantic/` — the evidence-backed semantic graph (entities/relations/
  evidence, identity resolution, grounding layers G1–G4, concepts, kitems,
  the compiler, gap detection, bundle/rulebook/sTeX projections).
- `tools/drillui_*` — an "ask-the-document" terminal UI (see below).
- `tools/pdfdrill_mcp.py` + `tools/drillbatch.py` — a stdio MCP server (drill
  results as MCP resources) + a batch driver (see the MCP section below).

## drillui — ask-the-document terminal

`tools/drillui_*` is a browser terminal for chatting with one drilled document.
Three co-located pieces (full guide: [`tools/DRILLUI.md`](tools/DRILLUI.md)):

- **`drillui_chat.py`** — the *brain* (Python REPL over one doc): asks
  `pdfdrill retrieve` for grounded context, sends the enriched prompt to an LLM
  (`claude -p`), and stores the Q&A back via `pdfdrill chatlog`. Runs standalone
  in a terminal; self-locates `pdfdrill` from `../src`.
- **`drillui_bridge.ts`** — the *bridge* (Bun): spawns one `drillui_chat.py` per
  WebSocket, pipes stdin/stdout, serves the UI + the files pdfdrill writes
  (`/artifact`) + a host-browser opener (`/open`). Pure plumbing.
- **`drillui_term.html`** — the *UI* (xterm.js terminal + retrieval rail +
  Outputs panel of clickable reports).

Run it (zero config from the repo root — the bridge finds its siblings):

```bash
bun tools/drillui_bridge.ts data/paper.pdf      # then open http://localhost:8787/
bun tools/test_drillui_bridge.ts data/paper.pdf # integration test
```

Command model in the terminal: `open <url|file>` opens a new window (handled
locally, never an LLM call); a pdfdrill command name (`status`, `report`,
`model`, `latex`, …) runs **on the open doc**; anything else is a grounded
question. The document must already be drilled (`pdfdrill model <doc>`).

## MCP server — drill results as clickable resources in a chat client

`tools/pdfdrill_mcp.py` is a **pure-stdlib stdio MCP server** (no `mcp` SDK,
JSON-RPC 2.0 over stdin/stdout) exposing `drill` / `md` / `tiddlers` / `report`.
Each tool runs pdfdrill on the resolved doc (local path, https URL, or arXiv id)
and returns a text summary **plus the produced files as MCP resources** —
`resource_link` items + embedded `resource` content, fetchable via
`resources/read`. The client pulls files over the MCP connection, so there is
**no localhost port and no dead `/artifact` link** (the failure mode when a
drillui bridge URL is opened inside a hosted chat client).

Best fit: **Claude Desktop / Claude Code** (local stdio) — add to
`claude_desktop_config.json`:

```json
{ "mcpServers": { "pdfdrill": {
    "command": "python3",
    "args": ["/ABS/PATH/pdfdrill/tools/pdfdrill_mcp.py"] } } }
```

then ask: *"drill arxiv.org/abs/2305.04710 standard"* → the md/tiddlers come back
as openable resources. The **claude.ai web** client uses
`tools/pdfdrill_mcp_http.py` — the **Streamable HTTP** transport (one `/mcp`
endpoint, SSE responses, session + optional bearer auth + CORS) behind your
public HTTPS front, added as a custom connector. It imports the stdio server, so
both transports expose the same tools. Batch helper: `tools/drillbatch.py`
(shallow→standard→deep ladder; `--list-outputs` prints every produced file).
Full guide: [`tools/MCP.md`](tools/MCP.md).

## The layer tower

The whole toolchain is one stratified stack **L0–L8** (container → raster →
glyph → text lines → layout regions → typed objects → expression syntax →
semantic graph → ontology). **One canonical document per layer** lives in
[`docs/layers/`](docs/layers/README.md); the inter-layer semantics (support/
abstraction maps, split recovery, level skipping, metrics) in
[`docs/layers/TOWER.md`](docs/layers/TOWER.md).

## API keys

Network features read their credentials from **environment variables** (or a
git-ignored `.env` — copy `.env.example`); keys are never stored in the repo.
The whole offline path (`folder`, `model`, `compare`, `report`, `tiddlers`,
`ocr`, `embedimages`, `bibsource`, `latexbook`, …) needs **no keys at all**.

| Key | Used by | Get it |
|-----|---------|--------|
| `MATHPIX_APP_ID` / `MATHPIX_APP_KEY` | `mathpix`, `model` (OCR → `lines.json`), `snip` | <https://mathpix.com/> → Console → API Keys |
| `OPENAI_API_KEY` | `vision` (GPT-4o reads CDN crops MathPix left as images → math/TikZ/table) | <https://platform.openai.com/api-keys> |
| `NOVITA_API_KEY` | `snip --gemma` / `route` (Gemma-4 vision OCR of scanned ≤20-page docs → LaTeX/tables; `GEMMA_MODEL`/`NOVITA_BASE_URL` override) | <https://novita.ai/> → Settings → Key Management |
| `DEEPL_API_KEY` | `translate` (DeepL-translate prose tiddlers) | <https://www.deepl.com/your-account/keys> (free keys end in `:fx`) |
| `PERPLEXITY_API_KEY` | `bibfetch` (online BibTeX enrichment) | <https://www.perplexity.ai/> → Settings → API |

Run `pdfdrill doctor` to see which system tools, Python deps, and keys are
present and what each enables. A blocked sandbox host yields a clear
"enable it in your network settings" message, never a stack trace.

## Tests

```bash
for t in tests/test_*.py; do python3 "$t"; done
```

See `CLAUDE.md` for the full command list and architecture notes.
