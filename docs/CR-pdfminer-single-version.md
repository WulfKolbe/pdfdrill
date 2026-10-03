# CR: one pdfminer glyph-identity build for pdfdrill, pdf2mmd and psred

Owner of the work: **pdfdrill CLI** (code in the pdfdrill repo).
Consumer: psred (github.com/WulfKolbe/psred) adapts after each item lands.
Goal: **one** patched pdfminer, **one** installer, **one** copy of each shared
glyph-level tool -- used by pdfdrill, pdf2mmd and psred alike.

Every statement below was measured (psred commit after 13bc486, 2026-10-03);
the numbers are reproducible with the files named.

## Current state (measured)

- `pdfminer-glyph-identity.patch` exists in **three byte-identical copies**:
  `pdfdrill/vendor/`, `pdfdrill/src/pdfreader/`, `pdf2mmd/`. The installer
  `install-pdfminer-fork.sh` pins upstream `a18de2a`; it built and verified
  here (`cid 7 -> 'star'`).
- psred used **stock** pdfminer.six 20251230 and re-derived what the patch
  provides. Comparison per character, patch `LTChar.glyphname` vs psred's own
  route (`/tmp/cmp_names.py` logic, now in psred tests):

  | document | chars | agree | patch only | psred only | different |
  |---|---|---|---|---|---|
  | psred fixtures/t1.pdf (Type 1) | 233 | 230 | 1 | 0 | 2 (`fi` vs `f_i`) |
  | psred fixtures/cff/t1_cff.pdf (CFF) | 233 | 233 | 0 | 0 | 0 |
  | featjudge fixtures/plain.pdf | 351 | 347 | 4 | 0 | 0 |
  | arXiv 1701.02095 p1 | 2404 | 2362 | 42 | 0 | 0 |
  | Springer book pp. 20-22 | 6836 | 6836 | 0 | 0 | 0 |

  The patch is a strict superset; it also covers CFF (Type 1C) fonts.
- psred now prefers `LTChar.glyphname` when present (feature detection, no
  pin) and falls back to its own route; its suite passes under **both**
  builds (152/152 each).

## Requests

### R1 - one source for the patch and the installer
Keep exactly one copy (proposal: `pdfdrill/vendor/`), make the others
references (or a sync script with a checksum check).
**Accept:** a test in pdfdrill fails when two copies differ; pdf2mmd and
psred install from that one installer with the same pin.

### R2 - flag numbered pseudo-names (defect class, measured)
For pdfTeX bitmap fonts (Type 3, PK) the /Differences names are `a44`,
`a97`, ... The patch returns them as `glyphname`. They are not names: psred
had to add a filter (`^a\d+$`), otherwise its "never guess" test fails
(psred fixtures/lang/text_t1.pdf: 125 glyphs, all such pseudo-names).
**Proposal:** keep `glyphname` raw, add `LTChar.glyphname_reliable: bool`
(False for `a<n>`, `g<n>`, `cid<n>`, `uni`-less index names).
**Accept:** text_t1.pdf -> 0 reliable names; t1.pdf -> all reliable.

### R3 - keep what pdfminer throws away (additive, like the patch)
Measured needs of the glyph tools:
- `font.spec` (the font dictionary): stock pdfminer drops it, so /Differences
  and /FontFile* are not reachable from the font object. psred had to
  subclass `PDFResourceManager.get_font`; until then its /Differences source
  never ran.
- `LTChar.fontsize`, `LTChar.scaling`, `LTChar.rise`: `LTChar.matrix` does
  NOT contain the font size, and `render_char` receives `scaling` ALREADY
  x 0.01 (pdfdevice line ~110). Both pitfalls produced wrong boxes in psred
  (x extents 100x too narrow -- featjudge finding F10).
**Accept:** the byte-identical regression the patch already uses (1.16M
LTChar records) still holds; new fields covered by tests.

### R4 - one shared ink-box module (not inside pdfminer)
psred's `tools/inkboxes.py` computes exact glyph ink boxes from the embedded
font programs (Type 1 FontFile, CFF FontFile3) via fontTools BoundsPen, no
rendering. Against TFM ht/dp: median 0.011 em, 95 % 0.022 em; widths /
TFM advance median 0.871. pdfminer's own char box is -0.194..0.806 em for
every CM glyph. Move it into `pdfdrill/src/pdfreader/` as the single
version; psred then imports it.
Known pitfalls to keep fixed (each has a psred test):
- caches must live ON the font object, never in a dict keyed by `id(font)`
  (a recycled id served another PDF's font program: order-dependent wrong
  boxes);
- pdfTeX CM fonts carry no /Encoding: names come from the Type 1 program's
  built-in encoding (the patch provides this);
- Type 3 (`d1` operands in each CharProc) and TrueType (`glyf` bounds) are
  NOT covered yet.
**Accept:** psred's `tests/test_u46_inkboxes.py` (7 tests) passes against the
pdfdrill module.

### R5 - render mode in scan triage
The patch carries `render_mode` (Tr). OCR layers use mode 3 (invisible).
psred's preflight now counts characters by render mode on a sample (scan
pages, at most 5, plus pages 1-2) and recognises an OCR layer when >= half
of the characters on scan pages are invisible -- not only by Tesseract's
`GlyphLessFont`. Fixture: psred `fixtures/scan/scan_ocr_invisible.pdf`
(154 chars in mode 3, CMR10, no GlyphLessFont). Cost: 6 s for a 343-page
book, 19 s for 33 test documents.
**Accept:** pdfdrill's scan triage uses the same rule; the psred fixture is
classified "scanned with OCR layer".

### R6 - report the build
psred's `<doc>.preflight.json` now records
`pdfminer: {version, glyph_identity_patch}` (patched build:
`20260108.dev6+ga18de2a9c...`). pdfdrill outputs should record the same, so
every finding names the build that produced it.

## Fixtures to reuse (all in the psred repo)
`fixtures/t1.pdf`, `fixtures/cff/t1_cff.pdf`, `fixtures/lang/text_t1.pdf`,
`fixtures/scan/scan_only.pdf`, `fixtures/scan/scan_ocr.pdf`,
`fixtures/scan/scan_ocr_invisible.pdf`,
`playground/featjudge/fixtures/plain.pdf`.

## Order
R1 -> R2 -> R3 (patch work, each keeps the byte-identical regression) ->
R4 (module move) -> R5, R6. psred removes its own fallbacks only after R2-R4
have landed and its suite passes against the single version.
