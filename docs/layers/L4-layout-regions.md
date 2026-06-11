# L4 — Layout-region level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

Typed regions with rects — the MathPix `lines.json` shape
`{type, region{top_left_x, top_left_y, width, height}, text/latex, page, …}`
for types text/math/table/column/…, fused with L3 geometry via
`Alignment(kind="geometry")`.

> **This is the layer where splits are created.** The layout cut (columns,
> page breaks, crop margins) happens here, so every recovery operation must
> re-enter here or below. See [TOWER — split recovery](TOWER.md).

## Role classifiers on top of raw regions

| Classifier | Roles | Notes |
|---|---|---|
| `src/semantic/geometry_columns.py` | `MarginRole`: continuity, page_number, control_number, label, marginal | **source-independent** — works on MathPix and tesseract regions alike; `body_column` from the wide body lines, `out_of_column` non-overlap test |
| `src/semantic/blocks.py` | `BlockRole`: header/footer/body/table/signature/stamp/handwritten | content cues beat position (franking→stamp, HRB/USt-ID→footer, "Herrn …"→body recipient) |
| `src/pdfdrill/continuity.py` | margin markers | full-page margin OCR for "Seite N von M" / "Fortsetzung" / control numbers — explicitly OUTSIDE the MathPix content crop |

## Learned elements + image fusion

| Module | What it contributes |
|---|---|
| `src/pdfdrill/layout_elements.py` + `tsv_gcn.py` | learned layout elements (postal addresses, BOM line items) with content-addressed identity (blake3) + a 48-dim geometric projection vector; GNN attention over relative word-box features |
| `src/pdfdrill/extract_addresses.py` | the heuristic address finder (PLZ anchor) the GNN cross-checks against; libpostal enrichment |
| `src/pdfdrill/image_model.py` | fuses pdfplumber rects + `pdfimages` metadata with MathPix picture crops into ONE `EmbeddedImage` node (`Alignment(kind="image_region")`) — every route to an image hangs off the same node |
| `src/pdfdrill/emphasis_detector.py` | emphasis/region styling cues |

CLI: `elements`, `embedimages`, `continuity`, `geometry` (fusion).

## Inter-layer notes

- α up: block detectors + `tsv_gcn` propose L5 objects from L4 patterns.
- MathPix's column detection is one **fixed α that cuts support where it
  shouldn't**; owning the support relation means the stack can overrule it
  (see TOWER: split = multi-fragment support, repaired by re-segmentation
  here, never by text mutation).
- Margin continuity tokens ("Fortsetzung Seite 3") are explicit, printed
  **support pointers** — the L4 evidence for cross-page repairs.

## Open work

- The margin classifier is heuristic (phone numbers/times can read as
  control_number); the geometry *detection* is the robust part.
- A GNN model trained on real labelled pages (the synthetic-trained one
  over-generalizes on unseen layouts).
