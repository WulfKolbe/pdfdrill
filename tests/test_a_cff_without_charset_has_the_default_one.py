r"""A CFF Top DICT that states no `charset` has the ISOAdobe one (TN 5176).

fontTools raised AttributeError('charset'), and lib:6d90e8d27b8b p174 lost
its in-pass ink; pdfread applied the default and the two readers differed.
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("fontTools")
ib = pytest.importorskip("pdfreader.inkboxes")


def _cff_without_charset() -> bytes:
    from fontTools.cffLib import CFFFontSet
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    def cs(draw):
        p = T2CharStringPen(500, None)
        draw(p)
        return p.getCharString()

    def bar(p):
        p.moveTo((100, 0)); p.lineTo((200, 0)); p.lineTo((200, 700)); p.closePath()

    order = [".notdef", "space", "exclam"]        # ISOAdobe's first three
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({33: "exclam"})
    fb.setupCFF("T", {"FullName": "T"},
                {".notdef": cs(lambda p: None), "space": cs(lambda p: None),
                 "exclam": cs(bar)}, {})
    buf = io.BytesIO()
    fb.font["CFF "].cff.compile(buf, fb.font)
    raw = buf.getvalue()
    probe = CFFFontSet()
    probe.decompile(io.BytesIO(raw), None)
    off = probe.topDictIndex[0].rawDict["charset"]
    enc = (bytes([off + 139]) if -107 <= off <= 107 else
           bytes([247 + (off - 108) // 256, (off - 108) % 256]))
    at = raw.find(enc + b"\x0f")
    assert at > 0
    # operator 15 (charset) -> 13 (UniqueID): same length, no charset left
    return raw[:at + len(enc)] + b"\x0d" + raw[at + len(enc) + 1:]


def test_fonttools_alone_cannot_read_it():
    from fontTools.cffLib import CFFFontSet
    s = CFFFontSet()
    s.decompile(io.BytesIO(_cff_without_charset()), None)
    with pytest.raises(AttributeError):
        s.topDictIndex[0].CharStrings


def test_the_default_charset_names_the_glyphs():
    top = ib._cff_top(_cff_without_charset())
    cs = top.CharStrings
    assert "exclam" in cs
    from fontTools.pens.boundsPen import BoundsPen
    p = BoundsPen(cs)
    cs["exclam"].draw(p)
    assert p.bounds == (100, 0, 200, 700)
