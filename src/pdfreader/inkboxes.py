"""Exact glyph INK boxes from the PDF, without rendering.

CR-pdfminer-single-version R4. This is psred's `tools/inkboxes.py`, moved here
as the single version; psred imports it rather than keeping a copy, because a
second copy is the copy that does not get fixed when the first one is.

WHAT IT IS FOR. pdfminer's own char box is the FONT's box, not the glyph's:
-0.194..0.806 em for every CM glyph, identical for an `x` and a `g`. So it
cannot say where ink actually is. The embedded font program can — Type 1
(`/FontFile`) and CFF (`/FontFile3`) carry outlines, and fontTools' BoundsPen
reports their exact extrema. The font matrix and the text state then put those
on the page. Measured against TFM ht/dp, an independent source: median 0.011
em, 95% 0.022 em.

CONTRACT
    ink_boxes(pdf, page_no) -> [dict, ...]   one per glyph, in drawing order
      name         the glyph's name, or None
      font         the font's base name
      ink          (x0, y0, x1, y1) in PDF points, or None
      pdfminer     pdfminer's own char box (font-wide, same for every glyph)
      size         the font size
      base         the baseline (text matrix f)
      cid          the character code
      render_mode  the `Tr` in force (3/7 = invisible), or None on a pdfminer
                   without the glyph-identity patch

    `ink` is None rather than a guess whenever the answer is not known: no
    embedded program, a Type 3 or TrueType font, or an unresolved glyph name.

WHAT R2 AND R3 REMOVED FROM IT. The version this came from carried two
workarounds, and moving it without deleting them would have carried the
duplication the change request exists to end:

  * a `PDFResourceManager` subclass whose only job was `f.spec = spec`,
    because stock pdfminer drops the font dictionary. R3 keeps `font.spec`,
    so the subclass is gone. It also never ran for a font resolved before the
    subclass was installed, which is how psred's /Differences source silently
    never fired.
  * a local `^a\\d+$` filter for pdfTeX bitmap-font pseudo-names. R2 computes
    `LTChar.glyphname_reliable` in the fork, so there is one rule.

Both degrade rather than break on an older pdfminer, because psred must be
able to import this while its environment is still catching up.

NOT COVERED, deliberately and stated rather than returned as a guess: Type 3
fonts (the `d1` operands in each CharProc) and TrueType (`glyf` bounds).
"""
from __future__ import annotations

import io
import re

from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import resolve1

#: Fallback for a pdfminer without R2. The fork's rule is the authority.
_PSEUDO = re.compile(r"^[a-zA-Z]\d+$")

try:                                                         # pragma: no cover
    from pdfminer.layout import glyphname_reliable as _reliable
except Exception:                                            # noqa: BLE001
    _reliable = None


def _name_is_usable(name: str | None, fontname: str | None) -> bool:
    if not name:
        return False
    if _reliable is not None:
        return _reliable(name, fontname)
    return not _PSEUDO.match(name)


def _program(font):
    """(bounds(name), font_matrix_scale, code->name) for the embedded program.

    CACHED ON THE FONT OBJECT, never in a dict keyed by `id(font)`. A freed
    font's id is reused, and the recycled id then served its program to a
    different PDF's font — wrong boxes, and only after another document had
    been read, so the failure was order-dependent and looked random.
    `test_u46_result_does_not_depend_on_a_previous_document` is the guard.
    """
    if hasattr(font, "_inkboxes_program"):
        return font._inkboxes_program
    desc = resolve1(_spec_of(font).get("FontDescriptor")) or {}
    res = None
    if desc.get("FontFile3") is not None:                    # CFF / Type 1C
        from fontTools.cffLib import CFFFontSet
        cff = CFFFontSet()
        cff.decompile(io.BytesIO(resolve1(desc["FontFile3"]).get_data()), None)
        top = cff[cff.fontNames[0]]
        cs = top.CharStrings
        fm = getattr(top, "FontMatrix", [0.001])[0]

        def bounds(n, _cs=cs):
            if n not in _cs:
                return None
            from fontTools.pens.boundsPen import BoundsPen
            p = BoundsPen(_cs)
            _cs[n].draw(p)
            return p.bounds

        enc = top.Encoding if isinstance(top.Encoding, list) else None
        res = (bounds, fm, enc)
    elif desc.get("FontFile") is not None:                   # Type 1 (pdfTeX CM)
        from fontTools.t1Lib import T1Font
        data = resolve1(desc["FontFile"]).get_data()
        t = T1Font.__new__(T1Font)
        t.data = data
        t.encoding = "ascii"
        t.parse()
        cs = t.font["CharStrings"]
        fm = t.font["FontMatrix"][0]

        def bounds(n, _cs=cs):
            if n not in _cs:
                return None
            from fontTools.pens.boundsPen import BoundsPen
            p = BoundsPen(_cs)
            _cs[n].draw(p)
            return p.bounds

        # THE PROGRAM'S BUILT-IN ENCODING. pdfTeX's CM fonts carry no
        # /Encoding in the PDF at all, so this is the only place the names
        # exist — which is also why R3 had to keep the font dictionary.
        enc = t.font.get("Encoding")
        res = (bounds, fm, enc if isinstance(enc, list) else None)
    font._inkboxes_program = res
    return res


def _spec_of(font):
    """The font's PDF dictionary. Native since R3; `{}` on an older build."""
    return getattr(font, "spec", None) or {}


def build_gap() -> str | None:
    """Why this pdfminer cannot produce ink boxes at all, or None.

    THE TRAP THIS CLOSES. The version of this module that lived in psred
    carried a `PDFResourceManager` subclass that supplied `font.spec` itself,
    so it WORKED on a pdfminer without R3. This one relies on the native
    field, which is the point of the move — but on an older build that means
    `ink=None` for every glyph, and an all-None result with no explanation is
    indistinguishable from a document of Type 3 fonts.

    So the reason is reported. "Never a guess" was already true; "never a
    guess, and always a reason" is what a caller can act on.
    """
    try:
        from pdfminer.pdffont import PDFFont
    except Exception:                                        # noqa: BLE001
        return "pdfminer is not importable"
    if not hasattr(PDFFont, "spec"):
        return ("this pdfminer build has no `PDFFont.spec` (R3): the font "
                "dictionary is dropped, so no embedded font program is "
                "reachable. Rebuild the fork — "
                "vendor/install-pdfminer-fork.sh --rebuild (the installer "
                "SILENTLY REUSES an existing venv without that flag)")
    return None


def _name_from_differences(font, cid: int) -> str | None:
    enc = resolve1(_spec_of(font).get("Encoding"))
    if not isinstance(enc, dict) or "Differences" not in enc:
        return None
    code = 0
    for t in resolve1(enc["Differences"]) or ():
        if isinstance(t, int):
            code = t
        else:
            if code == cid:
                return t.name
            code += 1
    return None


def ink_boxes(pdf, page_no: int) -> list:
    """One record per glyph drawn on `page_no`, in drawing order.

    Each record carries `ink_reason` when `ink` is None, so an absent box says
    why it is absent instead of leaving the caller to guess between an
    uncovered font, an unresolved name and a pdfminer that cannot answer.
    """
    rec: list = []
    gap = build_gap()

    class _Recorder(PDFLayoutAnalyzer):
        def render_char(self, matrix, font, fontsize, scaling, rise, cid,
                        ncs, gs):
            adv = super().render_char(matrix, font, fontsize, scaling, rise,
                                      cid, ncs, gs)
            it = self.cur_item._objs[-1]
            prog = _program(font)

            # The fork's name first — it is a superset of what the PDF states
            # — then /Differences, then the program's built-in encoding.
            name = getattr(it, "glyphname", None)
            fontname = getattr(it, "fontname", "") or ""
            if not _name_is_usable(name, fontname):
                name = _name_from_differences(font, cid)
            if name is None and prog and prog[2]:
                try:
                    name = prog[2][cid]
                except (IndexError, KeyError, TypeError):
                    name = None

            box = None
            why = None
            if gap:
                why = gap
            elif not prog:
                why = ("no embedded font program (/FontFile, /FontFile3): a "
                       "Type 3 or TrueType font, neither of which is covered")
            elif not name:
                why = "the glyph name could not be resolved"
            if prog and name:
                b = prog[0](name)
                if b:
                    a, bb, c, d, e, f = matrix     # text matrix x CTM, NO size
                    fm = prog[1]                   # glyph units -> text space
                    # `scaling` is ALREADY Tz/100 when render_char receives it
                    # (R3). Applying 0.01 again gave widths 100x too narrow —
                    # featjudge F10, invisible to any y-only check.
                    hs = scaling
                    pts = [((gx * fm * fontsize) * hs,
                            gy * fm * fontsize + rise)
                           for gx in (b[0], b[2]) for gy in (b[1], b[3])]
                    xs = [a * x + c * y + e for x, y in pts]
                    ys = [bb * x + d * y + f for x, y in pts]
                    box = (min(xs), min(ys), max(xs), max(ys))
                else:
                    why = f"the font program states no outline for {name!r}"

            rec.append({
                "ink_reason": None if box else why,
                "name": name,
                "font": font.fontname.split("+")[-1],
                "ink": box,
                "pdfminer": it.bbox,
                "size": it.size,
                "base": it.matrix[5],
                "cid": cid,
                "render_mode": getattr(it, "render_mode", None),
            })
            return adv

    rm = PDFResourceManager()
    dev = _Recorder(rm)
    with open(pdf, "rb") as fh:
        for i, page in enumerate(PDFPage.get_pages(fh)):
            if i == page_no - 1:
                PDFPageInterpreter(rm, dev).process_page(page)
                break
    return rec
