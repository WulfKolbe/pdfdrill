# L0 — Container / digital-native channel

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

Flat typed records parsed from the **PDF object tree** — no geometry except
annotation rects. Born-digital assertions at the highest semantic precision but
physically at the lowest level. Properties: **exact, ~free, available before
any rendering** — the classification short-circuit.

## Structure

- **PdfInfo** struct: title, author, dates, pages, producer, encryption,
  text-layer flag; plus `-custom` metadata (DOI, arXivID, License).
- Named destinations (theorem/equation/section anchors).
- URL annotations; link kinds (url / internal / javascript), resolved
  destinations and anchor text.
- **FontRecord**: name, family, type, encoding, embedded, subset, is_math,
  is_bold, is_italic, is_subscript_size.
- **ImageRecord**: page, bbox in points, pixel size, ppi, colorspace,
  encoding, file size.
- Embedded XMP/XML payloads (the e-invoice / Factur-X case) and attachment
  streams belong here too.

## Implementing modules

| Module | What it contributes |
|---|---|
| `src/pdfdrill/pdfinfo_layers.py` | PdfInfo struct, `-custom` metadata, named destinations, URL annotations |
| `src/pdfdrill/font_image_layers.py` | FontRecord, ImageRecord |
| `src/pdfdrill/annotations.py`, `links_layer.py` | annotation rects, link kinds, resolved destinations, anchor text |
| `src/pdfdrill/pdf_reading.py` (attachments/formfields) | attachment streams, AcroForm field values |

CLI: `size`, `pdfinfo`, `links`, `dests`, `fonts`, `images`, `attachments`,
`formfields`.

## The killer case (why this layer pays)

`pdfdrill links` (~50 ms, pure `pdfinfo -url`) reads the annotation layer and
surfaces hyperlinks with **no visible anchor text** — invisible to every
rendered-text stream an LLM reads, and to MathPix. Run the cheap L0 commands
before assuming the rendered text is all there is.

## Inter-layer notes

- **Level skipping is legitimate here:** an L8 query answered entirely by
  L0-supported nodes (embedded XML → invoice classification) never triggers
  rendering or OCR. See [TOWER — level skipping](TOWER.md).
- QR payloads decoded at L1 are L0-*quality* data (exact, structured) found in
  the raster.

## Open work

- Promote L0 link annotations into first-class `Link` graph nodes feeding the
  citation/provenance graph (the `cite.<key>` dest micro-grammar is in
  `annotations.py`; Citation nodes keyed by those dests are the missing half).
- Factur-X / ZUGFeRD XML extraction as a direct L0→L8 schema fill.
