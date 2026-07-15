# PROMPT — Integrate the enriched OCR module (PDFDRILLocr) into PDFDRILL

You are a Claude Code agent working in ~/MX/PDFDRILL. Work under the Humble
Engineer rules recorded in this repo's AGENTS.md / the user's methodology:
interface contracts first, one unit at a time, full `pytest` after every
unit, checkpoint language ("Unit X verified, N tests passing"), never claim
"done". Gate every commit on an UN-PIPED pytest (or `set -o pipefail`).

## What you are integrating

`~/PDFDRILLocr/ocr_lines.py` — a single-file, stdlib-only, drop-in
replacement for `src/pdfdrill/ocr_lines.py` (137 tests in ~/PDFDRILLocr).
Same four public functions (`tools_available`, `build_lines_json`,
`lines_json_from_words`, `_render_and_ocr`) with byte-frozen legacy
behavior, PLUS on the enriched path (`build_lines_json`):

- lines typed MathPix-compatibly: section_header / page_info / table
  (incl. TOC-as-table with children_ids) / equation (display blocks merged)
  / diagram; everything else "text"
- per-line conf + words[{text,x0,y0,x1,y1,conf,word_num,raw_text?}] +
  block_num/par_num/line_num + per-page blocks tree
- coordinates in PDF POINTS, page image_id "tesseract-p{N}" → works with
  docmodel.mathpix.image_ref() local pyramid crops (units=pt)
- language autocorrection (stopword probe; deu-first fixes Griiner→Grüner),
  equ explicit-only, German text repairs (vowel-gated ß, quotes, bullets)
  with raw_text provenance, min_conf noise filter (default 5.0)
- OSD auto-upright (90/180/270) BEFORE OCR — coords in the true frame
- second passes: text_math (Greek re-OCR of equation regions), 
  text_layer_text (pdftotext -tsv overlay merge), barcodes
  ([{symbology,data,region?}] via zbarimg + pylibdmtx)
- `ocr` meta block: lang/lang_effective/min_conf/units/render_dpi/
  text_layer/type_counts/warnings

## Integration steps (one unit each, full suite between)

1. Copy `~/PDFDRILLocr/ocr_lines.py` over `src/pdfdrill/ocr_lines.py`.
   Leave `geometry.py` untouched (other consumers). Run pytest: the
   ingest preserves extra keys verbatim, and ParagraphProcessor already
   splits on block_num/par_num (commit a245e3f).
2. Wire `cmd_ocr` (commands.py:618): pass through `--min-conf`,
   `--no-typing` equivalents if you expose them; keep the source guard.
   The module renders its own pages (gs) — cmd_ocr's out_dir handling
   stays valid.
3. Audit consumers that assumed tesseract-source regions are raster px:
   grep for source=="tesseract" coordinate branches; regions are now
   POINTS with ocr.units="pt" + render_dpi for the mapping back.
   `image_ref()` now yields working /cropped/ URLs for the keyless path.
4. Update the SKILL (`src/pdfdrill/skill/SKILL.md` `ocr` row + commands.yaml
   via tools/skillsync.py): "plain text only — no typing/no crops" is no
   longer true. Re-sync the attestation token.
5. Reconsider the model gate: NEEDS_VISION_OCR fired on "tesseract ⇒ 0
   equations"; the enriched path DOES emit equation lines (type+rectangle,
   garbled text, text_math hint). visionocr remains the LaTeX route; the
   gate should key on missing LaTeX, not missing equation lines.
6. `pdfdrill qr` (zxing-cpp) overlaps the module's barcode pass — decide:
   keep both (lines.json standalone vs sidecar) or back both with zxing-cpp.

## Coordination — DO NOT COLLIDE

- DRILLTEXT (parallel project, in progress): a sentence-segmentation
  processing step (punctuation-based, analogous to ParagraphProcessor)
  will consume Paragraph objects. Keep Paragraph boundaries/props STABLE;
  do not refactor paragraph.py beyond a245e3f; additive changes only.
- ~/PDFDRILLocr remains the OCR module's home (own tests/spec); fixes to
  the module go THERE first, then re-copy. Do not fork the file's logic.

## The large test — route matrix (start after step 1-3 are green)

Run `python3 tools/route_matrix.py <pdf> [...]` (in this repo) over the
corpus: 1802.08153.pdf, 2305.04710v1.pdf, 2601.07372.pdf (born-digital,
all four routes), ~/HeimTheory/files/Zur_Herleitung_Der_Heimschen_
Massenformel.pdf (scanned: tesseract vs MathPix), ~/WKprivate/Scanned/
ocrtest.pdf + temp/scan_*.pdf (letters). It builds one docmodel per
available route and emits a per-document markdown table:

| object type | OCR (tesseract) | OCR++ (MathPix) | pdfminer | LaTeX (gold) |

Routes per document (skip gracefully when a source is absent):
- OCR: fresh lines.json from the NEW module (deu+eng where German)
- OCR++: MathPix lines.json (pdfdrill mathpix — paid; reuse existing files)
- pdfminer: ~/DRILLPDFse lines_json.py output (source "pdfminer")
- LaTeX gold: pdfdrill latex/model from the arXiv e-print

Deliverable: docs/route-matrix-<date>.md with all tables + a findings
section (where each route wins/loses per object type). Numbers are counts
of DocObjects by type; flag empty-but-expected cells (e.g. 0 Equations on
a math doc) as failures per SKILL rule 4.
