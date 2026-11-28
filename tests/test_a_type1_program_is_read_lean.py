r"""The lean Type 1 reader gives what fontTools' full parse gives.

SPEED (EXACT), board 118, ink_boxes option (a): `inkboxes._t1_program` reads
FontMatrix and Encoding from the cleartext and slices Subrs and CharStrings
out of the decrypted section, where fontTools' T1Font.parse interprets the
whole program in psLib. The twin is fontTools itself: every glyph's bounds
(drawn with fontTools' own T1CharString and BoundsPen), the FontMatrix and
the Encoding must be equal. On board 118 that held for 94 programs and
3,857 glyph bounds; here it is held on cmr10 (OFL; see fixtures/type1).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

pytest.importorskip("fontTools")
from pdfreader import inkboxes  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "type1" / "cmr10.t1"


def test_the_lean_reader_equals_fonttools_on_cmr10():
    from fontTools.t1Lib import T1Font
    from fontTools.pens.boundsPen import BoundsPen
    data = FIX.read_bytes()
    inkboxes._fast_eexec()
    lean = inkboxes._t1_program(data)
    assert lean is not None, "cmr10 must take the lean path"
    cs, fm, enc = lean
    t = T1Font.__new__(T1Font)
    t.data, t.encoding = data, "ascii"
    t.parse()
    ref = t.font["CharStrings"]
    assert list(fm) == list(t.font["FontMatrix"])
    assert [type(v) for v in fm] == [type(v) for v in t.font["FontMatrix"]]
    assert enc == t.font["Encoding"]
    assert set(cs) == set(ref.keys())
    for name in ref.keys():
        a = BoundsPen(ref)
        ref[name].draw(a)
        b = BoundsPen(cs)
        cs[name].draw(b)
        assert a.bounds == b.bounds, name


def test_an_unexpected_program_falls_back_to_fonttools():
    assert inkboxes._t1_program(b"%!PS-AdobeFont-1.0 no eexec here") is None
    # hex eexec is left to fontTools
    data = FIX.read_bytes()
    k = data.find(b"eexec") + 5
    assert inkboxes._t1_program(data[:k] + b"\r\n" + data[k:k + 8].hex().encode()) is None
