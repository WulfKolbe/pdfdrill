# Refine Propose — with the page's own glyph census

**Sent by** refine.propose_one when `census=` is given (688).

Formatted with conf, latex, census and notes.

The third arm. The other two ask a model to repair LaTeX from the LaTeX alone
(TEXT) or from the LaTeX and a picture of the line (CROP). This one adds what
the PDF itself records: the characters its text layer decodes, the names its
fonts give to glyphs Unicode cannot map, and any place where two glyphs are
drawn at ONE position and are therefore one symbol.

It exists because that last fact is unguessable from a crop at the sizes we
have, and decisive once known: 1510.06699_EQ0241 prints a slashed J as a J at
x 207.84 and a solidus at x 208.56 — the same place — and an OCR that drops
both leaves a fraction with an empty half.

NO LITERAL BRACES BELOW THE SEPARATOR. The body is formatted with str.format,
so a brace that is not a named slot raises. Rules are therefore worded rather
than shown.

---
This LaTeX came from OCR of a printed equation and its confidence is {conf}.
It may have lost or merged rows, dropped cells, or dropped a symbol entirely.

Below the OCR reading you are given the PAGE'S OWN GLYPH CENSUS: what the PDF
records as actually printed in this region, in reading order, grouped by
baseline. It carries no structure -- it cannot tell you what is a superscript,
a fraction or a delimiter -- so use the OCR reading for structure and the
census as the authority on WHICH SYMBOLS ARE PRESENT.

Return a corrected LaTeX body for the SAME equation. Rules:
  - return the body only, with no dollar signs, no display delimiters and no
    code fence
  - keep every environment balanced
  - account for every symbol the census lists, and introduce nothing it does
    not show
  - change only what is damaged; leave every correct symbol exactly as it is
  - return ONE reading of ONE expression: never continue into a neighbouring
    equation or into surrounding prose
  - never emit a CJK character, a CJK bracket, or an ideographic description
    character; if the OCR contains one it is a decomposition of a symbol the
    recogniser could not name, so name the symbol instead
  - a command whose mandatory argument is left empty is always wrong, and a
    dropped symbol is usually the reason one appears; if the census shows a
    symbol the OCR lacks, put it back rather than leaving the argument empty

OCR READING (confidence {conf}):
{latex}

PAGE GLYPH CENSUS:
{census}

{notes}
