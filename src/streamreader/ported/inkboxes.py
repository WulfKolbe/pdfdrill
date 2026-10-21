# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from pdfdrill (github.com/WulfKolbe/pdfdrill), src/pdfreader/inkboxes.py
# at 9502bfee (itself psred's tools/inkboxes.py, moved there as the single
# version). pdf2mmd2: the recorder device is gone - the glyph reader calls
# `box` from its own device - and outline bounds are cached per font.
"""Exact glyph INK boxes from the PDF, without rendering.

pdfminer's own char box is the FONT's box, not the glyph's: -0.194..0.806 em
for every CM glyph, identical for an `x` and a `g`. The embedded font
program can say where the ink is - Type 1 (`/FontFile`) and CFF
(`/FontFile3`) carry outlines, and fontTools' BoundsPen reports their exact
extrema. The font matrix and the text state then put those on the page.
Measured against TFM ht/dp, an independent source: median 0.011 em, 95%
0.022 em.

CONTRACT
    box(font, glyphname, fontname, cid, matrix, fontsize, scaling, rise)
        -> (name, ink, reason)
      name    the glyph's name: the fork's when reliable, else the PDF's
              /Differences, else the font program's built-in encoding
      ink     (x0, y0, x1, y1) in PDF points, or None
      reason  why `ink` is None, else None

    `ink` is None rather than a guess whenever the answer is not known: no
    embedded program, a Type 3 or TrueType font, an unresolved glyph name,
    or fontTools not installed.

NOT COVERED, deliberately and stated rather than returned as a guess: Type 3
fonts (the `d1` operands in each CharProc) and TrueType (`glyf` bounds).
"""
from __future__ import annotations

import io
import re

from pdfminer.pdftypes import resolve1

#: Fallback for a pdfminer without R2. The fork's rule is the authority.
_PSEUDO = re.compile(r"^[a-zA-Z]\d+$")

try:                                                         # pragma: no cover
    from pdfminer.layout import glyphname_reliable as _reliable
except Exception:                                            # noqa: BLE001
    _reliable = None


def fonttools_available() -> bool:
    try:
        import fontTools  # noqa: F401
    except ImportError:
        return False
    return True


def _name_is_usable(name: str | None, fontname: str | None) -> bool:
    if not name:
        return False
    if _reliable is not None:
        return _reliable(name, fontname)
    return not _PSEUDO.match(name)


def _spec_of(font):
    """The font's PDF dictionary. Native since R3; `{}` on an older build."""
    return getattr(font, "spec", None) or {}


def _program(font):
    """(bounds(name), font_matrix_scale, code->name) for the embedded program.

    CACHED ON THE FONT OBJECT, never in a dict keyed by `id(font)`. A freed
    font's id is reused, and the recycled id then served its program to a
    different PDF's font - wrong boxes, and only after another document had
    been read, so the failure was order-dependent and looked random.
    """
    if hasattr(font, "_inkboxes_program"):
        return font._inkboxes_program
    desc = resolve1(_spec_of(font).get("FontDescriptor")) or {}
    res = None
    cs = fm = enc = None
    try:
        if desc.get("FontFile3") is not None:                # CFF / Type 1C
            from fontTools.cffLib import CFFFontSet
            cff = CFFFontSet()
            cff.decompile(
                io.BytesIO(resolve1(desc["FontFile3"]).get_data()), None)
            top = cff[cff.fontNames[0]]
            cs = top.CharStrings
            fm = getattr(top, "FontMatrix", [0.001])[0]
            enc = top.Encoding if isinstance(top.Encoding, list) else None
        elif desc.get("FontFile") is not None:               # Type 1 (pdfTeX)
            from fontTools.t1Lib import T1Font
            t = T1Font.__new__(T1Font)
            t.data = resolve1(desc["FontFile"]).get_data()
            t.encoding = "ascii"
            t.parse()
            cs = t.font["CharStrings"]
            fm = t.font["FontMatrix"][0]
            # THE PROGRAM'S BUILT-IN ENCODING. pdfTeX's CM fonts carry no
            # /Encoding in the PDF at all, so this is the only place the
            # names exist.
            enc = t.font.get("Encoding")
            enc = enc if isinstance(enc, list) else None
    except Exception:                                        # noqa: BLE001
        cs = None           # pdf2mmd2: a font program fontTools cannot read
    if cs is not None:
        cache: dict = {}    # pdf2mmd2: an outline is traced once per font

        def bounds(n, _cs=cs, _cache=cache):
            if n not in _cache:
                found = None
                if n in _cs:
                    from fontTools.pens.boundsPen import BoundsPen
                    try:
                        p = BoundsPen(_cs)
                        _cs[n].draw(p)
                        found = p.bounds
                    except Exception:                        # noqa: BLE001
                        found = None
                _cache[n] = found
            return _cache[n]

        res = (bounds, fm, enc)
    font._inkboxes_program = res
    return res


def build_gap() -> str | None:
    """Why this pdfminer cannot produce ink boxes at all, or None."""
    try:
        from pdfminer.pdffont import PDFFont
    except Exception:                                        # noqa: BLE001
        return "pdfminer is not importable"
    if not hasattr(PDFFont, "spec"):
        return ("this pdfminer build has no `PDFFont.spec` (R3): the font "
                "dictionary is dropped, so no embedded font program is "
                "reachable. Rebuild it with scripts/install-pdfminer.sh")
    return None


def _name_from_differences(font, cid: int) -> str | None:
    if hasattr(font, "_inkboxes_differences"):   # pdf2mmd2: resolved once
        return font._inkboxes_differences.get(cid)
    table: dict[int, str] = {}
    enc = resolve1(_spec_of(font).get("Encoding"))
    if isinstance(enc, dict) and "Differences" in enc:
        code = 0
        for t in resolve1(enc["Differences"]) or ():
            if isinstance(t, int):
                code = t
            else:
                table.setdefault(code, t.name)
                code += 1
    font._inkboxes_differences = table
    return table.get(cid)


_GAP = None if fonttools_available() else "fontTools is not installed"


def box(font, glyphname, fontname, cid, matrix, fontsize, scaling, rise):
    """(name, ink, reason) for one glyph as pdfminer's render_char sees it.
    `matrix` is text matrix x CTM without the font size; `scaling` is
    already Tz/100."""
    gap = _GAP or build_gap()
    prog = None if gap else _program(font)
    # The fork's name first - it is a superset of what the PDF states - then
    # /Differences, then the program's built-in encoding.
    name = glyphname
    if not _name_is_usable(name, fontname or ""):
        name = _name_from_differences(font, cid)
    if name is None and prog and prog[2]:
        try:
            name = prog[2][cid]
        except (IndexError, KeyError, TypeError):
            name = None
    if gap:
        return name, None, gap
    if not prog:
        return name, None, ("no embedded font program (/FontFile, "
                            "/FontFile3): a Type 3 or TrueType font, neither "
                            "of which is covered")
    if not name:
        return name, None, "the glyph name could not be resolved"
    b = prog[0](name)
    if not b:
        return name, None, f"the font program states no outline for {name!r}"
    a, bb, c, d, e, f = matrix
    fm = prog[1]                               # glyph units -> text space
    pts = [((gx * fm * fontsize) * scaling, gy * fm * fontsize + rise)
           for gx in (b[0], b[2]) for gy in (b[1], b[3])]
    xs = [a * x + c * y + e for x, y in pts]
    ys = [bb * x + d * y + f for x, y in pts]
    return name, (min(xs), min(ys), max(xs), max(ys)), None
