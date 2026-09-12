r"""What the PDF itself says is on the page, glyph by glyph.

A MathPix reading is one opinion about some ink. For a born-digital document
there is a SECOND, INDEPENDENT opinion available for free, and it is the
typesetter's own: the page's text layer, plus the font `/Encoding` that names
every glyph the text layer cannot map to Unicode. This module reads that.

WHY IT EXISTS
-------------
679. Nineteen of 44,633 published equation/formula rows cannot be typeset at
all, and eight of those are a MathPix GLYPH DECOMPOSITION: the recogniser met
a symbol it could not name and emitted CJK radicals or ideographic
DESCRIPTION characters (⿰ ⿱ ⿺ ⿻ — whose only purpose is to describe how a
character is composed) in its place. Asking a language model to guess the
intended symbol works, but it guesses; the PDF knows.

Measured on the three rows of mielke-geometrodynamics, against MathPix:

    row      MathPix wrote              the PDF's glyphs say
    EQ0857   \mathbf{匕}                 Ł  (Times-Roman /Lslash, code 173)
    EQ0472   \stackrel{十}{\Omega}       + (a literal plus)
    FO0431   \jmath  AND  」            /floorright BOTH TIMES — one symbol,
                                        two different wrong guesses

FO0431's own surrounding prose, from the same text layer, reads "covariant
Lie derivative ... on M with respect to an arbitrary vector field": the
document names its own symbol.

TWO SOURCES, AND THE SECOND IS THE USEFUL ONE
---------------------------------------------
A glyph with a `/ToUnicode` entry arrives as a character and needs nothing.
A glyph WITHOUT one arrives as the literal string `(cid:N)` — and that is not
a failure, it is the signal: it marks exactly the glyphs where the producer
supplied no Unicode and an OCR therefore had to invent. For those, the font's
`/Encoding /Differences` still names the glyph, and TeX's names are
self-describing: `floorright` is ⌋, `lscript` is ℓ, `parenleftbigg` is `\bigg(`,
`similarequal` is ≅, `negationslash` is the `\not` overlay.

Measured over the 20 published documents: 604 distinct glyph names, of which
267 are outside the Adobe Glyph List — i.e. 267 names that arrive as
`(cid:N)` and would otherwise be lost. They are overwhelmingly the Computer
Modern / MathTime / AMS conventions, not arbitrary strings.

WHAT THIS IS NOT
----------------
Not a transcriber. It reports evidence — characters, glyph names, fonts,
sizes, positions — and never assembles LaTeX. Turning a census into a reading
is a separate judgement, made with this in hand.

LIMITS, NAMED
-------------
* A SCANNED page has no text layer and no fonts; the census is empty and says
  so. That is where ink measurement is the only evidence.
* A symbolic font declaring a text encoding (`WinAnsi`) with no `/ToUnicode`
  yields PLAUSIBLE BUT WRONG characters rather than `(cid:N)`, which is worse
  than silence. `mielke`'s 15 `Adv*` fonts are this shape (15 of 230, absent
  from every page measured here). `suspect_fonts()` names them so a caller can
  distrust their characters while still trusting their glyph NAMES.
* Coordinates come in as MathPix's 250-dpi CropBox pixels (654) because that
  is what the model stores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: MathPix renders every page at 250 dpi of the CropBox (654), and PDF user
#: space is 72 dpi. One scale, stated once.
MATHPIX_DPI = 250.0
_PT_PER_PX = 72.0 / MATHPIX_DPI

#: poppler/pdfminer render an unmapped glyph as this literal string.
CID = re.compile(r"^\(cid:(\d+)\)$")

#: A font that declares a TEXT encoding and supplies no `/ToUnicode` while
#: actually holding symbols. Its characters cannot be trusted; its glyph
#: names still can.
_SUSPECT_NAME = re.compile(r"Adv(TT|P|SPRING|GTIMES|MSBM)", re.I)


@dataclass(frozen=True)
class Glyph:
    """One glyph as the PDF describes it."""
    char: str                      # the decoded character, or "(cid:N)"
    name: Optional[str]            # the /Differences glyph name, when unmapped
    font: str
    size: float
    x: float
    line: int                      # rounded `top`, so a caller can group rows

    @property
    def token(self) -> str:
        """What to show a reader: the glyph name wins, because a name is
        specific where a character is absent."""
        return ("/" + self.name) if self.name else self.char

    @property
    def unmapped(self) -> bool:
        return bool(CID.match(self.char))


def _lit(x):
    """A PSLiteral's name, or the value unchanged."""
    return getattr(x, "name", x)


def font_differences(pdf_path) -> dict:
    """{BaseFont: {code: glyph name}} for every font carrying /Differences.

    Walks the xref rather than the page tree: a font dictionary is reachable
    from several pages and this is read once per document.
    """
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdftypes import resolve1

    out: dict = {}
    with open(pdf_path, "rb") as fh:
        doc = PDFDocument(PDFParser(fh))
        for xref in doc.xrefs:
            for objid in xref.get_objids():
                try:
                    obj = resolve1(doc.getobj(objid))
                except Exception:
                    continue                      # a damaged object is not fatal
                if not isinstance(obj, dict) or _lit(obj.get("Type")) != "Font":
                    continue
                enc = resolve1(obj.get("Encoding"))
                diffs = resolve1(enc.get("Differences")) if isinstance(enc, dict) else None
                if not isinstance(diffs, list):
                    continue
                table, code = {}, 0
                for item in diffs:
                    item = resolve1(item)
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        code = int(item)
                    else:
                        nm = _lit(item)
                        if isinstance(nm, str):
                            table[code] = nm
                        code += 1
                if table:
                    out.setdefault(str(_lit(obj.get("BaseFont")) or ""), {}).update(table)
    return out


def suspect_fonts(names) -> list:
    """Those font names whose CHARACTERS should not be trusted (see LIMITS)."""
    return sorted({n for n in names if _SUSPECT_NAME.search(n or "")})


def region_to_points(region: dict) -> tuple:
    """MathPix 250-dpi CropBox pixels -> (x0, y0, x1, y1) in PDF points."""
    x, y = float(region["top_left_x"]), float(region["top_left_y"])
    w, h = float(region["width"]), float(region["height"])
    return (x * _PT_PER_PX, y * _PT_PER_PX,
            (x + w) * _PT_PER_PX, (y + h) * _PT_PER_PX)


def census(page, region: dict, differences: dict, *, pad: float = 4.0) -> list:
    """Every Glyph inside `region`, in reading order.

    `page` is a pdfplumber page; `differences` is `font_differences()`'s
    result. `pad` widens the box by a few points because a MathPix region is
    a tight box around ink and a glyph's declared origin can sit just outside
    it.
    """
    x0, y0, x1, y1 = region_to_points(region)
    out = []
    for c in page.chars:
        if not (x0 - pad <= c["x0"] <= x1 + pad and y0 - pad <= c["top"] <= y1 + pad):
            continue
        char, name = c["text"], None
        m = CID.match(char)
        if m:
            name = (differences.get(c["fontname"]) or {}).get(int(m.group(1)))
        out.append(Glyph(char=char, name=name, font=c["fontname"],
                         size=float(c["size"]), x=float(c["x0"]),
                         line=int(round(c["top"]))))
    out.sort(key=lambda g: (g.line, g.x))
    return out


def as_line(glyphs) -> str:
    """The census as one readable line — what a prompt or a report shows."""
    return " ".join(g.token for g in glyphs)


def unmapped_names(glyphs) -> list:
    """The distinct glyph names the PDF had to supply because Unicode did not."""
    return sorted({g.name for g in glyphs if g.name})


def contradicts(latex: str, glyphs, *, own_region: bool,
                minimum: int = 3) -> "str | None":
    r"""A one-line reason when `latex` cannot be a reading of `glyphs`.

    NOT a transcription check — LaTeX and glyphs are different alphabets and
    a faithful reading legitimately adds `\frac`, `^`, `_` and braces that no
    glyph carries. This asks only the question a wrong answer fails loudly:
    do the glyphs the PDF actually places on the page APPEAR in the proposed
    reading at all?

    679 — this exists because the ink gate accepted a proposal that replaced
    mielke-geometrodynamics_EQ0378's mathematics with a sentence of English
    prose about the Pontryagin index, on the strength of the ink distance
    falling 106 -> 10. Ink distance measures how MUCH ink a rendering makes,
    not whether it is the same ink; a short wrong line beats a long damaged
    one. The letters and digits the PDF puts in that region are not in that
    sentence, and this would have said so.

    `own_region` IS REQUIRED AND IS NOT A CONVENIENCE. The test is only valid
    when `glyphs` came from the object's OWN region. An inline Formula has no
    region of its own, so a caller reaches for its HOST LINE's — and a host
    line is a whole line of prose. Measured on
    mielke-geometrodynamics_FO0431: its host-line census holds 92 glyphs, 84
    of them literal, because the line reads "covariant Lie derivative on M
    with respect to an arbitrary vector field" around the formula. Judged
    against that, MathPix's perfectly reasonable 8-character reading is
    "missing" 49 of 84 glyphs — a false refusal, and a confident one.

    So this declines rather than guesses when the region is not the object's,
    and the parameter is positional-by-keyword and has no default so that
    declining is a decision a caller makes on purpose.

    `minimum` is the floor below which the test declines to judge: a region
    holding one or two glyphs carries no evidence worth refusing on.
    """
    if not own_region:
        return None
    literal = [g.char for g in glyphs
               if not g.unmapped and len(g.char) == 1 and g.char.isalnum()]
    if len(literal) < minimum:
        return None
    missing = [ch for ch in literal if ch not in latex]
    if len(missing) > len(literal) / 2:
        return ("%d of %d literal glyph(s) the PDF places in this region are "
                "absent from the reading (%s)"
                % (len(missing), len(literal),
                   "".join(sorted(set(missing))[:12])))
    return None
