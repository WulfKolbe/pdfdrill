# L3 — Word/line string level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

The string level: words and visual lines with geometry, **one schema for both
channels**.

## Structure

- The 12-column TSV record
  `(level, page, par, block, line, word, left, top, width, height, conf, text)`
  — deliberately identical for `pdftotext -tsv` and tesseract
  (`text_layers.py`), so digital and OCR channels are one shape.
- `pdf_lines` **Stream** (anchors + payload) lifted from the TSV
  (`geometry.py`): coordinates normalized to the page box [0,1]; per-line
  `_geom`: left/right margins, baseline y, **indentation relative to
  body-left**, `sim` trust score, `fallback` flag.
- MathPix-shape `lines.json` emitted by the keyless path (`ocr_lines.py`):
  one `type:"text"` line per visual line with MathPix-style pixel region.

Note: tesseract's TSV already carries a block/paragraph/line/word hierarchy —
**a free proto-L4**.

## Implementing modules

| Module | What it contributes |
|---|---|
| `src/pdfdrill/text_layers.py` | the shared TSV schema over both producers |
| `src/pdfdrill/ocr_lines.py` | word boxes → lines → MathPix-compatible `lines.json` (keyless path) |
| `src/pdfdrill/geometry.py` | TSV → `pdf_lines` Stream; geometry fusion onto `mathpix_lines` (`Alignment(kind="geometry")`, y-tolerance + nearest-line fallback) |
| `src/pdfdrill/lines_paragraphs.py` | line/paragraph grouping in the engine path |

CLI: `tsv`, `ocr`, `geometry`.

## Inter-layer notes

- This is the level the L7 compiler's **grounding check** bottoms out in:
  cited `evidence_text` must literally occur in the cited block (L7→L3).
- Layout (indentation, margins, line spacing) is a *different level* than the
  text: block structure is derived from L3 geometry at L4/L5, not from OCR
  text.
- Native metric: edit distance over normalized strings; bbox IoU for the
  geometry half (see [TOWER — metrics](TOWER.md)).

## Open work

- Storage: stage-2 of the tiddler-canonical move retires the per-char/line
  offset machinery once text carries materialized transclusion tokens (see
  CLAUDE.md storage-overhead section).
