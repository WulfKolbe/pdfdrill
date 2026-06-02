# pdfdrill

**Token-economical drill-down extraction + PDF→LaTeX OCR quality control.**

🔗 **Project page:** <https://wulfkolbe.github.io>

`pdfdrill` is a flat CLI that returns prose, persists state in a sidecar next
to each PDF, and wraps the heavy tools (poppler, pdfplumber) so an LLM can
drill into a document with the cheapest sufficient command. It is paired with
a unified document model (`docmodel`) and an operator pipeline (`docops`) that
turn MathPix `lines.json` into a typed `Document` and emit QC artifacts — a
LaTeX | KaTeX | MathPix-image comparison table, a full formula report, and
TiddlyWiki tiddlers.

## Install

System prerequisite (not pip-installable): **poppler-utils**
(`pdfinfo`, `pdftotext`, `pdffonts`, `pdfimages`).

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
pdfdrill folder  ./papers          # batch-build every PDF that already has a
                                   #   sibling .lines.json — no network calls
```

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

## Layout

- `src/pdfdrill/` — the CLI toolkit, sidecar state machine, and capture layer.
- `src/docmodel/` — the unified document-object model (`Stream` / `Anchor` /
  `Realization` / `Alignment` / `Region`), built from MathPix `lines.json`.
- `src/docops/` — `Mutator`s and `Projector`s over a `Document` (plaintext,
  LLM-compact markdown, TiddlyWiki, comparison table, formula report).

## MathPix / Perplexity credentials

Network features (`mathpix`, `snip`, `bibfetch`) read credentials from
environment variables — `MATHPIX_APP_ID` / `MATHPIX_APP_KEY` and
`PERPLEXITY_API_KEY` — and never store them in the repo. The whole offline
path (`folder`, `model`, `compare`, `report`, `tiddlers`, …) needs no keys.

## Tests

```bash
for t in tests/test_*.py; do python3 "$t"; done
```

See `CLAUDE.md` for the full command list and architecture notes.
