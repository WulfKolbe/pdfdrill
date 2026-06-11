# L1 — Raster / pixel level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

Per-page bitmaps plus derived geometric primitives, **each with confidence**.
The immutable base medium for everything standoff above it (see
[TOWER](TOWER.md): base media are never mutated; layers above are recomputable).

## Structure

Primitive types:
- line segments, rectangles, **blobs** (centroid, principal axis, extent);
- decoded symbologies (payload, symbology, rect) — QR / GiroCode / DataMatrix;
- page renders; empty-page flags; skew estimates.

## Implementing modules

| Module | What it contributes |
|---|---|
| `pdftoppm` path (`pdf_reading.rasterize`, `ocr_lines`, `qrscan`) | page renders |
| `src/pdfdrill/qrscan.py` | QR/GiroCode/DataMatrix decoding from the raster — the payload is **L0-quality data found at L1** (a GiroCode carries creditor/IBAN/amount/reference) |
| `src/pdfdrill/font_classify.py` | ONNX glyph-image classifier (torch-free): WORD crops → font face + category votes per OCR field |
| skew/blob detection | Hough-style; the external `blobcc` moment-based principal-axis estimator is the streaming variant of the same layer (not vendored) |

CLI: `rasterize`, `qr`, `fontid`, `extractimages` (raster bytes).

## Inter-layer notes

- **Level-skipping showcase:** a decoded GiroCode populates the L8 invoice
  frame directly (edge `level_from=1, level_to=8`) — see `pdfdrill semantic`,
  which attaches `qr_creditor`/`qr_iban`/`qr_amount` as 0.95-confidence
  evidence and resolves the issuer the OCR text omits.
- `compare_math` closes an **L6↔L1 verification loop**: the LaTeX reading is
  scored against the MathPix-rendered crop.
- Visual font id exists because a *scan* has no L0 font layer — L1 recovers
  what L0 lost. Font is a property of each text FIELD, not one document vote;
  the **category** (sans/serif/mono) is the robust signal.

## Open work

- Vendoring/porting the blob/skew estimator as a first-class primitive
  producer.
- Empty-page and deskew records as uniform `node(level=1)` rows (see TOWER
  schema).
