r"""
B12, lib:6d90e8d27b8b p174: the running head is set in cm-super sans
(SFSS0900, the page number in SFSX0900). Nothing told a sans face, so the
reading carried it as plain text, the judge set it in the body's serif and
all 13 glyphs were flagged. A sans face is `\textsf` (outermost with
`\texttt`, which it excludes); SFSX is also bold. Judge (pin f78391d) 6d90
p174: 0.0096 -> 0.0000.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import texmap as T


def test_cm_super_sans_is_textsf():
    assert T.emphasis_for({"PxfrfpSFSS0900"}) == [r"\textsf"]
    assert T.emphasis_for({"JywkbpSFSX0900"}) == [r"\textsf", r"\textbf"]


def test_other_sans_faces():
    for f in ("ABC+CMSS10", "ABC+Helvetica", "ABC+NimbusSanL-Regu", "ABC+ArialMT"):
        assert T.emphasis_for({f})[:1] == [r"\textsf"], f


def test_serif_and_typewriter_are_not_sans():
    assert T.emphasis_for({"ABC+NimbusRomNo9L-Regu"}) == []
    assert T.emphasis_for({"ABC+CMR10"}) == []
    assert T.emphasis_for({"ABC+DejaVuSansMono"}) == [r"\texttt"]


def test_the_wrapper_comes_off_again():
    assert T.unwrap_emphasis(r"\textsf{33.2 Lösungen} \textsf{\textbf{165}}") == "33.2 Lösungen 165"
