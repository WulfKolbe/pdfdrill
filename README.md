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

Optional OCR extra (PyTorch — heavy, not on the live path):

```bash
pip install -e ".[pix2tex]"
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

Every command also accepts an **https URL from a known host or a bare arXiv
id** (`pdfdrill model 2510.11170v2`) — downloaded once, cached; for arXiv the
abstract and the author LaTeX come from the **free** routes (no MathPix
spend).

Without the installed console script, run as a module:

```bash
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
```

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

## Feature extraction (commercial documents)

`src/features/` is a small **additive** layer (a starter, not yet wired into the
CLI): source-agnostic extractors take plain text and emit flat `Feature`
objects, with flat `Relation` edges and a NetworkX `build_graph`. It never
touches the existing pipeline.

```bash
pip install '.[features]'                      # dateparser, phonenumbers, price-parser, …
PYTHONPATH=src python3 -m features invoice.txt # → JSON of EMAIL/URL/DOI/DATE/PHONE/PRICE/… features
```

Always-on (regex): `EMAIL`, `URL`, `DOI`. Library-backed (degrade to nothing
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
- `src/features/` — additive, source-agnostic feature extractors (commercial
  documents): flat `Feature`/`Relation`, a registry, and a NetworkX graph
  builder. Never modifies the pipeline.
- `src/semantic/` — the evidence-backed semantic graph (entities/relations/
  evidence, identity resolution, grounding layers G1–G4, concepts, kitems,
  the compiler, gap detection, bundle/rulebook/sTeX projections).

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
