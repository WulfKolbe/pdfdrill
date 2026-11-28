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
    # SPEED (EXACT) -- ONE PARSE PER DOCUMENT, NOT PER PAGE. `ink_boxes` runs a
    # fresh resource manager for every page, so the font objects, and the
    # program cached on them, lived one page: 43 Type 1 parses for 12 board
    # pages, 19 of 141 profiled seconds. The program is the FontFile stream,
    # and within one document its object number names it; `_DOC_PROGRAMS`
    # holds one document's programs at a time (keyed by path, size and
    # mtime), so no id from another PDF can ever reach it.
    ref = desc.get("FontFile3") if desc.get("FontFile3") is not None else desc.get("FontFile")
    key = (getattr(ref, "objid", None), getattr(ref, "genno", None))
    if key[0] is not None and key in _DOC_PROGRAMS["progs"]:
        res = _DOC_PROGRAMS["progs"][key]
        font._inkboxes_program = res
        return res
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
        _fast_eexec()
        data = resolve1(desc["FontFile"]).get_data()
        lean = _t1_program(data)
        if lean is not None:
            cs, fmat, lean_enc = lean
            fm = fmat[0]
        else:
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
        enc = lean_enc if lean is not None else t.font.get("Encoding")
        res = (bounds, fm, enc if isinstance(enc, list) else None)
    if res is not None:
        # SPEED (EXACT) -- a glyph's bounds once per program, not once per
        # occurrence: 14,875 charstring draws for 33,809 glyphs.
        _raw, _memo = res[0], {}

        def bounds(n, _raw=_raw, _memo=_memo):
            if n not in _memo:
                _memo[n] = _raw(n)
            return _memo[n]
        res = (bounds, res[1], res[2])
    if key[0] is not None:
        _DOC_PROGRAMS["progs"][key] = res
    font._inkboxes_program = res
    return res


#: The parsed font programs of the document `ink_boxes` last read.
_DOC_PROGRAMS: dict = {"doc": None, "progs": {}}


def _enter_document(pdf) -> None:
    """Start a new program cache unless `pdf` is the same file as last time."""
    import os
    try:
        st = os.stat(pdf)
        doc = (os.path.realpath(pdf), st.st_size, st.st_mtime_ns)
    except OSError:
        doc = None
    if doc is None or doc != _DOC_PROGRAMS["doc"]:
        _DOC_PROGRAMS["doc"] = doc
        _DOC_PROGRAMS["progs"] = {}


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



def ink_record(it, matrix, font, fontsize, scaling, rise, cid, gap) -> dict:
    """The record `ink_boxes` keeps for one drawn glyph `it` (pdfminer's
    LTChar, just made by `render_char` with these arguments). One function,
    so the build's own interpreter pass can make the same record (board 118,
    option (d)) without a second pass over the page."""
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

    return {
        "ink_reason": None if box else why,
        "name": name,
        "font": font.fontname.split("+")[-1],
        "ink": box,
        "pdfminer": it.bbox,
        "size": it.size,
        "base": it.matrix[5],
        "cid": cid,
        "render_mode": getattr(it, "render_mode", None),
    }


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
            rec.append(ink_record(self.cur_item._objs[-1], matrix, font,
                                  fontsize, scaling, rise, cid, gap))
            return adv

    _enter_document(pdf)
    rm = PDFResourceManager()
    dev = _Recorder(rm)
    with open(pdf, "rb") as fh:
        for i, page in enumerate(PDFPage.get_pages(fh)):
            if i == page_no - 1:
                PDFPageInterpreter(rm, dev).process_page(page)
                break
    return rec


def _eexec_decrypt(cipherstring, R):
    r"""fontTools' `eexec.decrypt`, one loop instead of a call per byte.

    SPEED (EXACT): the same recurrence -- `plain = (c ^ (R >> 8)) & 0xFF`,
    `R = ((c + R) * 52845 + 22719) & 0xFFFF` -- over the same bytes, so the
    plaintext and the returned key are identical (tests hold it to the
    original). fontTools spent 2.6 s of 1805.01788 p3's 22.9 s (board 118,
    under the profiler) in 663 k `_decryptChar` calls. Anything that is not
    bytes goes to the original.
    """
    if not isinstance(cipherstring, (bytes, bytearray)):
        return _EEXEC_ORIGINAL(cipherstring, R)
    out = bytearray(len(cipherstring))
    r = R
    for i, c in enumerate(cipherstring):
        out[i] = (c ^ (r >> 8)) & 0xFF
        r = ((c + r) * 52845 + 22719) & 0xFFFF
    return bytes(out), int(r)


_EEXEC_ORIGINAL = None


def _fast_eexec() -> None:
    """Install `_eexec_decrypt` as fontTools' `eexec.decrypt`, once."""
    global _EEXEC_ORIGINAL
    from fontTools.misc import eexec
    if _EEXEC_ORIGINAL is None:
        _EEXEC_ORIGINAL = eexec.decrypt
        eexec.decrypt = _eexec_decrypt


def _t1_program(data: bytes):
    r"""A Type 1 program's CharStrings, FontMatrix and Encoding, read lean.

    SPEED (EXACT), board 118's ink_boxes, option (a): fontTools' T1Font.parse
    runs the whole program through psLib (1805.01788 p3: 14 programs, 0.97 s
    of its 5.9 s). This reads the cleartext for FontMatrix and the built-in
    Encoding, decrypts the eexec section, and slices Subrs and CharStrings by
    their RD lengths; the bounds still come from fontTools' own T1CharString
    and BoundsPen. Identical to the full parse on every board-118 program
    (3,857 glyph bounds, 94 matrices and encodings), and held to it by a test.

    Returns (charstrings, fontmatrix, encoding) or None when the program does
    not have the expected shape; the caller then takes fontTools' full parse.
    """
    import re
    from fontTools.misc.psCharStrings import T1CharString
    k = data.find(b"eexec")
    if k < 0:
        return None
    clear, enc = data[:k], data[k + 5:]
    i = 0
    while i < len(enc) and enc[i:i + 1] in (b"\r", b"\n", b" ", b"\t"):
        i += 1
    enc = enc[i:]
    if enc[:4] and all(c in b"0123456789abcdefABCDEF" for c in enc[:4]):
        return None                       # hex eexec: leave it to fontTools
    m = re.search(rb"/FontMatrix\s*[\[{]\s*([^\]}]*)[\]}]", clear)
    if not m:
        return None
    try:
        fm = [float(x) if (b"." in x or b"e" in x.lower()) else int(x)
              for x in m.group(1).split()]
    except ValueError:
        return None
    if re.search(rb"/Encoding\s+StandardEncoding\s+def", clear):
        from fontTools.encodings.StandardEncoding import StandardEncoding
        encoding = list(StandardEncoding)
    elif re.search(rb"/Encoding\s+\d+\s+array", clear):
        encoding = [".notdef"] * 256
        for e in re.finditer(rb"dup\s+(\d+)\s*/(\S+)\s+put", clear):
            encoding[int(e.group(1))] = e.group(2).decode("latin-1")
    else:
        return None
    plain = _eexec_decrypt(enc, 55665)[0][4:]
    m = re.search(rb"/lenIV\s+(-?\d+)", plain)
    leniv = int(m.group(1)) if m else 4
    cs_at = plain.find(b"/CharStrings")
    if cs_at < 0:
        return None

    def body(raw):
        return _eexec_decrypt(raw, 4330)[0][leniv:] if leniv >= 0 else raw

    subrs = []
    s_at = plain.find(b"/Subrs")
    if 0 <= s_at < cs_at:
        n = re.match(rb"/Subrs\s+(\d+)", plain[s_at:])
        if not n:
            return None
        subrs = [None] * int(n.group(1))
        pat = re.compile(rb"dup\s+(\d+)\s+(\d+)\s+(?:RD|-\|) ")
        pos = s_at
        while True:
            e = pat.search(plain, pos, cs_at)
            if not e:
                break
            idx, ln, st = int(e.group(1)), int(e.group(2)), e.end()
            if idx >= len(subrs):
                return None
            subrs[idx] = T1CharString(body(plain[st:st + ln]))
            pos = st + ln
    charstrings = {}
    pat = re.compile(rb"/(\S+)\s+(\d+)\s+(?:RD|-\|) ")
    pos = cs_at + len(b"/CharStrings")
    while True:
        e = pat.search(plain, pos)
        if not e:
            break
        name, ln, st = e.group(1).decode("latin-1"), int(e.group(2)), e.end()
        charstrings[name] = T1CharString(body(plain[st:st + ln]), subrs=subrs)
        pos = st + ln
    if not charstrings:
        return None
    return charstrings, fm, encoding
