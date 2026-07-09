# Example — all projections off one model

The docmodel is the canonical IR; every output is **codegen** from it. Build the
model once, then project it every way you need — each is one command writing into
the doc's `.drill/` sidecar.

```bash
pdfdrill model 2312.11532            # build the model ONCE (keyless for arXiv)
```

## Text / data

```bash
pdfdrill md       2312.11532         # <bibkey>.md      — LLM-compact Markdown, math transcluded
pdfdrill llmtext  2312.11532         # <bibkey>.llm.txt — flat, one unit per block, tiddler-titled
pdfdrill tiddlers 2312.11532         # <bibkey>.tiddlers.json — TiddlyWiki tiddler array
pdfdrill context  2312.11532 "main contribution?" --max-tokens 800   # structural RAG context
```

## Portable knowledge bundle (OKF)

```bash
pdfdrill okf 2312.11532              # okf/<bibkey>/*.md — per-type folders, relative links,
                                     #   pure Markdown+frontmatter (type per unit) + index.md
pdfdrill okf invoice.pdf --semantic  # …the ENTITY graph instead (Company/BankAccount/Person),
                                     #   relations as cross-links — the commercial-doc form
```

## Reading views (HTML, self-contained)

```bash
pdfdrill distill 2312.11532          # <bibkey>.distill.html — distill-structured, dark, KaTeX,
                                     #   runtime TOC, late-bound ?? figure refs, hover citations
pdfdrill report  2312.11532          # formula-report.html — LaTeX | KaTeX | image, per equation
pdfdrill compare 2312.11532          # compare.html — competing OCR provenances + scores
pdfdrill inspect 2312.11532          # <bibkey>.inspect.html — DevTools-style object inspector
```

Add `--embed` to any HTML projection to base64-inline every CDN crop (no live-CDN
dependency). All of these open in drillui's **Outputs** panel.

## LaTeX / formal targets

```bash
pdfdrill scikgtex 2312.11532 --compile   # <bibkey>.scikg.tex → PDF with ORKG metadata (XMP/RDF)
pdfdrill stex     2312.11532 --stex      # <bibkey>.stex.tex — sTeX / glossaries (acronyms, symbols, index)
pdfdrill lean     2312.11532             # <bibkey>.lean — Lean 4 export of theorems
```

**Why one model, many projections:** the extraction (MathPix / pdfminer / OCR /
LaTeX-source) runs once and the structure is captured in the docmodel; every
consumer — an LLM (`md`/`llmtext`/`context`), a wiki (`tiddlers`/`okf`), a reader
(`distill`/`report`/`inspect`), or a formal tool (`scikgtex`/`stex`/`lean`) — reads
the same validated model. See the full table in [../README.md](../README.md#projections--one-docmodel-many-outputs).
