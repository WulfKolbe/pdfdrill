# PDF assembly: control, metadata, lossless embedding, and the OCR layer

Everything below was measured on this machine, not read from docs.

## Verdict on the Ghostscript pdfocr devices

**They are not available here, and they are the wrong tool for this pipeline anyway.**

```
$ gs --version                → 10.07.1
$ gs -h | grep pdf            → pdfimage8, pdfimage24, pdfimage32, pdfwrite
$ gs -sDEVICE=pdfocr8 ...     → Unknown device: pdfocr8
```

`pdfocr8/24/32` exist in Artifex's source, but only when Ghostscript is **compiled
with Tesseract linked in** (`--with-tesseract`). This Solus build wasn't, so the
devices are absent. Getting them would mean building gs from source.

That's moot, because the devices conflict with SCANDRILL's prime directive:

- **They rasterize.** The pdfocr devices render the page through the gs raster
  pipeline and wrap the result. Our page image is *already* the scanner's exact
  output — sending it through a renderer is a decode → re-encode round trip that
  throws away the byte-identical embed for nothing.
- **`pdfocr8` is 8-bit grayscale.** It would silently destroy a `--mode Color`
  scan. `pdfocr24` (RGB) / `pdfocr32` (CMYK) keep colour but still re-encode, and
  CMYK would be an unwanted colour-space conversion.
- **No metadata control.** The device writes the PDF; title/author/`/Lang`/page
  labels are ours to set, and we'd be fighting it.

So: **do not route page images through Ghostscript.** (gs stays useful for the
600 dpi *renders* pylepto consumes — that's a different job, per pylepto's
"rasterize with Ghostscript at 600 dpi" decision.)

## What was measured instead

| Path | JPEG stream | PNG pixels | Text layer | Metadata control |
|---|---|---|---|---|
| `img2pdf` (ours) | **byte-identical** | **identical** | none | full (pikepdf) |
| `tesseract … pdf` | byte-identical (DCT passthrough) | identical (Flate) | yes | **none — it writes the PDF** |
| gs `pdfocr8` | n/a — device absent; rasterizes; grayscale | — | yes | none |
| **ours + text-only graft** | **byte-identical** | **identical** | **yes** | **full** |

Tesseract's own PDF writer turned out better than expected — it passes JPEG
through verbatim rather than re-encoding. But it *writes the whole PDF*, so we'd
lose title/author/`/Lang`/page labels and our page ordering. The fix is to take
only the part we want.

## The recommended architecture: graft a text-only layer

```
kept pages (seq order)
   ↓ img2pdf            — no re-encode: JPEG→DCTDecode verbatim, PNG→Flate identical
image PDF
   ↓ pikepdf            — /Lang, DocInfo + XMP, page labels        ← full control
lossless PDF  ────────────────────────────────► deliverable (default)
   ↓ tesseract -c textonly_pdf=1                — invisible text ONLY, no image
text-only PDF (3.4 KB vs 7.4 KB with image)
   ↓ pikepdf Page.add_overlay                   — grafts text onto our page
searchable PDF, image stream untouched
```

Measured on the graft:

```
image stream byte-identical after graft: True   (filter=/FlateDecode)
OCR text now extractable:  'SCANDRILL OCR probe 12345'
```

`textonly_pdf=1` is the key: Tesseract emits a PDF containing *only* the invisible
text positioned over the page, no image at all. `add_overlay` composites it onto
our page's content stream. The image XObject is never rewritten — hence
byte-identical. This is the same technique ocrmypdf uses (not installed here).

**Why OCR at all, given the design rule?** Per CLAUDE.md, OCR only serves to
*prepare a better PDF* — here it adds a text layer to a scan that has none, which
is a strictly additive improvement to the artifact. pdfdrill still does the real
analysis downstream (`route --run` picks its own lane). The text layer is opt-in
(`--ocr`), because for an arXiv-style born-digital source it would be noise.

### On fitz / PyMuPDF

fitz (1.27.2.3, installed) is excellent for *reading* — `get_text()` verified the
graft above, and it's the right tool for inspecting/QA'ing the result. For
*writing*, pikepdf is the better fit here: `add_overlay` does exactly the graft,
and pikepdf is already the metadata tool. fitz's `insert_text(render_mode=3)` is
the alternative if we ever need to place text without Tesseract's PDF writer
(e.g. from hOCR/TSV), but that means re-implementing glyph placement Tesseract
already does correctly. Recommendation: **fitz for verification, pikepdf for
mutation.**

## Metadata control

The PDF carries metadata in two places that must agree, or readers disagree with
each other:

- **DocInfo** (`/Title`, `/Author`, `/Producer`, …) — the legacy dictionary.
- **XMP** (`dc:title`, `dc:creator`, `pdf:Producer`, …) — the modern packet;
  what most tooling and PDF/A validators read.

pikepdf's `open_metadata()` writes XMP and can sync DocInfo. Proposed `DocMeta`:

| Field | DocInfo | XMP | Note |
|---|---|---|---|
| `title` | `/Title` | `dc:title` | |
| `author` | `/Author` | `dc:creator` (a *list*) | |
| `subject` | `/Subject` | `dc:description` | |
| `keywords` | `/Keywords` | `pdf:Keywords` | |
| `creator` | `/Creator` | `xmp:CreatorTool` | the *producing app* |
| `producer` | `/Producer` | `pdf:Producer` | defaults to `SCANDRILL <version>` |
| `created` | `/CreationDate` | `xmp:CreateDate` | from the job, not wall clock |
| `lang` | — | — | catalog `/Lang`; OCR + a11y read it |

Plus **page labels** (`/PageLabels`): decimal from 1 by default; the structure
also supports roman front matter and prefixes, which matters once `segment`
splits a bundle into documents.

`set_pikepdf_as_editor=False` keeps pikepdf from stamping *itself* as the editor
(already a gotcha in CLAUDE.md).

## What stays true regardless

- The PDF is a **projection of `ingest.json`** — kept pages, seq order. Anything
  that can't be re-derived from the manifest doesn't belong in the assembly step.
- Rotation (deskew) is the *only* pixel-touching step, it is recorded, and `raw/`
  is retained. Assembly itself never resamples — verified by
  `tests/test_adf_assemble.py`.
