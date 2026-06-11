# L2 — Glyph level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

One record per character: **codepoint, font name/size, baseline position,
bbox, source channel**.

## Structure

Two parallel producers fill the same conceptual record:

| Channel | Producer | Confidence |
|---|---|---|
| digital text layer | pdfplumber `chars` (`ingest_pdfplumber.py`) | none (exact by construction) |
| OCR | tesseract per-glyph boxes | per-glyph confidence |

**The confidence asymmetry is structural**: it exists only on the OCR channel,
and the fusion layer above must carry it (a fused line's trust is the min of
its channels').

## Implementing modules

| Module | What it contributes |
|---|---|
| `src/pdfdrill/ingest_pdfplumber.py` | pdfplumber char records into the engine context |
| `src/pdfdrill/latex_map.py` | the glyph→LaTeX command table consumed by the math assembler (L2 → L6 vocabulary) |
| `src/pdfdrill/tokenizer.py`, `math_detector.py` | glyph-run tokenization, math-glyph detection |

## Inter-layer notes

- γ-support: every L3 word's support is an ordered list of L2 glyph records.
- The `latex_map` table is the **vocabulary bridge** L2→L6: a math codepoint's
  LaTeX command is decided here, but its *binding* (which `\psi` this is) is
  only decidable at L7 — see the negative result recorded in
  [L6](L6-expression-syntax.md).

## Open work

- Uniform glyph `node(level=2)` emission for the TOWER schema (today glyphs
  live inside the engine context / TSV, not as standoff nodes).
