# QUICKSTART — pdfdrill in 60 seconds

A complete keyless workflow: install → drill an arXiv paper → inspect the math →
open the results. Everything below is copy-pasteable and needs **no API key**.

## Install

```bash
git clone https://github.com/pdfdrill/pdfdrill && cd pdfdrill
bash bootstrap.sh          # system deps via apt-get (poppler, ghostscript,
                           #   tesseract, LaTeX+dvisvgm, libvips) — installs only
                           #   what's missing, then runs the requirement check
pip install -e .           # puts the `pdfdrill` command on PATH
pdfdrill doctor            # confirm: present/missing tools + Python deps + keys
```

Not on Debian/Ubuntu? `bootstrap.sh` prints the exact packages; install the
equivalents, then `pip install -e .`.

## Drill a paper (keyless — arXiv gold LaTeX, no OCR, no key)

You pass an **id, URL, or path** — pdfdrill downloads/resolves it (cached). Never
fetch the PDF yourself.

```bash
pdfdrill size    2312.11532     # page count, producer, text-layer vs scan
pdfdrill route   2312.11532     # which extraction lane pdfdrill will use, and why
pdfdrill model   2312.11532     # build the docmodel (auto-acquires the LaTeX source)
pdfdrill report  2312.11532     # → <drill>/formula-report.html  (LaTeX | KaTeX | image)
pdfdrill inspect 2312.11532     # → <bibkey>.inspect.html  (DevTools-style, self-contained)
```

Open the HTML the commands print (they live in `2312.11532.pdf.drill/`), or list
everything openable:

```bash
pdfdrill artifacts 2312.11532
```

## Ask the document (structural, no embeddings)

```bash
# a query → a small Markdown context of typed objects with ids (deterministic RAG):
pdfdrill context  2312.11532 "what is the main contribution?" --max-tokens 800
pdfdrill context  2312.11532 --type formula --max-tokens 400   # just the equations
pdfdrill conclusion 2312.11532                                  # the actual outcome
pdfdrill abstract   2312.11532                                  # goal + method
pdfdrill bibtex     2312.11532                                  # a @misc/@article record
```

## Next

- Genre recipes: `examples/` (arxiv, book, slides, invoice, equations).
- The full command surface (~100 commands) + the anti-patterns: `SKILL.md`.
- If you're an AI agent driving pdfdrill: **read `AGENTS.md` first** (DO/NEVER,
  allowed transitions, the escape ladder).
- Stuck? `pdfdrill steps <cmd> 2312.11532` shows the prerequisite chain;
  `pdfdrill status 2312.11532` shows what's already known.

## The one rule

pdfdrill owns the heavy tools and the state machine. **Never** `curl`/`tar` the PDF,
hand-parse a `.tex`, or run your own OCR — hand the id/URL/path to pdfdrill and let
it do the acquisition, extraction, and model build.
