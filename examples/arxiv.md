# Example — an arXiv paper (keyless, gold LaTeX)

The best case: pdfdrill uses the author's e-print `.tgz` directly — real equations,
no OCR, no key. You pass the **id** (or `https://arxiv.org/abs/…`), never the file.

```bash
pdfdrill size    2312.11532          # born-digital, has a text layer
pdfdrill route   2312.11532          # → born-digital lane (free)
pdfdrill model   2312.11532          # auto-downloads the e-print, ingests gold LaTeX
pdfdrill bibtex  2312.11532          # → @misc{…, eprint=…, archivePrefix=arXiv, primaryClass=…}
```

Then any projection or analysis over the model:

```bash
pdfdrill report    2312.11532        # formula-report.html (LaTeX | KaTeX | image)
pdfdrill tiddlers  2312.11532        # TiddlyWiki tiddlers (bibkey-prefixed)
pdfdrill context   2312.11532 --type formula --max-tokens 500   # just the math
pdfdrill gaps      2312.11532        # undefined acronyms / unmatched citations
pdfdrill classify  2312.11532        # subject (needs a compiled vocab — see SKILL)
```

**Why it's keyless:** for an arXiv input, `model`/`latex` fetch the free e-print and
expand the author's macros — MathPix is never touched. Don't run `mathpix` here
unless you want the paid OCR/CDN route (`--force`).

**Gotcha:** a LaTeX-source model has **math but no page geometry**, so `inspect`'s
page-box view won't work on it — `inspect` will tell you to build a geometry-bearing
model (`ocr`/`mathpix`). For the math itself, `report`/`context`/`tiddlers` are what
you want.
