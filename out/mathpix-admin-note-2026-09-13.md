# Note for the MathPix admin mail — 2026-09-13

Drafted from measurements on a 20-document published set (44,633 equation and
formula rows) and a 1,359-document library. Every number below is reproducible
from `out/682.txt`, `out/682-goldens-mielke.json` and `out/685.txt`.

---

## The paragraph (paste-ready)

> **Systematic misreading of the interior-product operator ⌋ (U+230B).** In one
> 330-page monograph (Mielke, *Geometrodynamics of Gauge Fields*) we find 24
> equations in which ⌋ is read incorrectly — 43 instances in total: 30 as
> `\downharpoonleft`, 13 dropped entirely. The same glyph is also read in that
> document as `\jmath`, `」` (a CJK corner bracket), `\downarrow`, and —
> correctly — `\rfloor`: five readings of one symbol in one book. The
> distinguishing feature is not ink quantity but **stroke angle**: ⌋ joins its
> strokes at 90°, ⇃ at an acute barb, so the two are near-identical by area and
> component count. Every one of these readings **typesets successfully**, so no
> downstream validation catches them; across our labelled sample, 34 of 36
> known-wrong equations render without error. We would rather not report
> symbol-by-symbol. The useful ask is that **low-confidence equations be
> surfaced to the customer as such** — several of these sit at 0.05–0.10
> confidence — so they can be routed for correction rather than shipped looking
> clean.

---

## The one suggestion worth pressing

**For a born-digital PDF the answer is already inside the file.** The page's
font `/Encoding` names the glyph:

    MTSYN        /Differences [ 2 /angbracketleft … /floorright … ]  → code 8 is ⌋
    Times-Roman  /Lslash at code 173                                 → Ł, not \pounds
    (a third)    a literal `+` above Ω                               → \stackrel{+}{\Omega}

MathPix appears to OCR a rendered image while ignoring a text layer that states
the answer. Our reference implementation is ~200 lines of pdfminer
(`src/pdfdrill/glyphcensus.py`: `font_differences()` + `census()`), no font
parsing, no network. We are happy to share it.

Its limits are known and worth stating: scanned pages carry nothing to read,
and a symbolic font declaring `WinAnsi` with no `/ToUnicode` yields
plausible-but-wrong characters rather than an honest `(cid:N)` — 15 of 230
fonts in that book.

Measured across our library of 1,359 documents with a MathPix snapshot:

    LaTeX-produced             961   (71%)  glyph names are rich and reliable
    scanned, no text layer      64   ( 5%)  nothing to read
    born-digital, not LaTeX    334   (25%)  text layer present, publisher
                                            tooling, glyph names unhelpful

So the text-layer route covers roughly 71% outright, and identifies the
remaining 29% cheaply — which is itself the win.

## A second suggestion that needs no new recognition capability

**Self-consistency within a document.** Five readings of one glyph in one book
is detectable by clustering identical glyph bitmaps across a document and
requiring one reading. No angle measurement, no text layer, no model change —
and it would have caught all 43 instances above.

---

## Why we are not asking for "better harpoon recognition"

The failures that MathPix's own pipeline can already see are the ones that
refuse to typeset: unbalanced delimiters, glyph decomposition into CJK
radicals, truncated environments. Those are visible and largely handled.

What survives is the class that **renders perfectly and is wrong**: 34 of 36 in
our labelled sample. Neither MathPix nor the customer can see those, and no
amount of per-symbol improvement changes that, because the next rare symbol
behaves the same way.

Hence the ask is about **routing, not recognition**: publish the confidence you
already compute, flag the low-confidence equations, and let correction happen
where the evidence is available. The customer wants correct OCR output, not a
conversation about harpoons.

---

## Appendix — evidence, if asked

| claim | measurement |
|---|---|
| 24 rows, 43 instances of ⌋ misread in one book | glyph census vs reading, per row |
| 30 as `\downharpoonleft`, 13 dropped | same |
| five readings of one glyph | `\rfloor`, `\jmath`, `」`, `\downarrow`, `\downharpoonleft` |
| 34 of 36 wrong equations render | `out/682-goldens-mielke.json`, field `renders` |
| confidence 0.052 on EQ0293 | model prop, published report |
| 604 distinct glyph names, 267 outside the AGL | 20 published documents |
| 961 / 64 / 334 document split | `pdfinfo` producer + text-layer probe, 1,359 docs |

Also available, if a worked example helps: `mielke-geometrodynamics_EQ0974`,
where MathPix reads π once and the page carries it twice. pix2tex reads it
twice and is correct. The glyph census agrees with pix2tex, so the
disagreement is settleable without preferring either tool.
