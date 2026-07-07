# Example — math QC (is the extraction correct?)

The core purpose: quality-control PDF→LaTeX. Build the model, then compare readings
and flag bad math — never transcribe an equation from a rendered page.

```bash
pdfdrill model     paper.pdf          # build (records model_caps = {geometry, math})
pdfdrill report    paper.pdf          # LaTeX | KaTeX-render | source-image, per equation
pdfdrill compare   paper.pdf          # the comparison HTML across provenances
pdfdrill mathcheck paper.pdf          # flags FLATTENED / garbled formulas
pdfdrill mathir    paper.pdf          # canonical SymPy tree per formula (srepr)
```

Keyless math when there's no MathPix key and the model came out math-less:

```bash
pdfdrill visionocr paper.pdf          # rasterize → an agent reads each page → real
                                      #   Equation nodes (paired by geometry)
```

Dual-route reconciliation — keep the pdfminer route's structure + geometry, but
correct its garbled math with MathPix's clean LaTeX (region-matched):

```bash
pdfdrill reconcile paper.pdf                          # QC report: how many garbled
pdfdrill mathpix   paper.pdf --force                  # clean math (paid) → a lines.json
pdfdrill reconcile paper.pdf --mathpix paper.mathpix.lines.json   # adopt clean math,
                                                      #   keep geometry + structure
```

**Why:** `mathcheck` catches equations linearised into unusable LaTeX (`M = m a (F +
j ) (B65)` with dropped subscripts); `reconcile` fixes the pdfminer route's
char-spacing / interleaving by adopting MathPix's clean body while keeping pdfminer's
self-contained geometry. Coordinate systems never mix — that's match-time only.

**Gotcha:** a keyless tesseract model has 0 equations and sets `NEEDS_VISION_OCR` —
`model` will tell you to run `visionocr`; don't present a 0-equation model as
complete. `mathir` needs the `[math]` extra (latex2sympy).
