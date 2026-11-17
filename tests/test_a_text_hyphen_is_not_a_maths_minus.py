r"""A hyphen stays a hyphen, even when the span around it is maths.

lib:c9daf79960c3 p68: 4 of its 10 invented rules are one glyph. The page reads
"p-group"; our reading typed the span as maths and emitted `$p-\mathrm{group}$`,
where LaTeX sets `-` as a BINARY MINUS -- a wider glyph with its own spacing --
so the judge found ink we had invented. `texmap._TEXT_MATHS["hyphen"]` was `"-"`
and both the maths-italic and the text-face paths read it.

`\text{-}` is a hyphen in either mode, so the one entry serves both. inkdrill-10
measured the page at invented rules 10 -> 6 and residual 0.0364, against
MathPix's 0.0370.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import texmap


def test_a_hyphen_is_not_set_as_a_minus():
    tok = texmap.project("text-cm", "hyphen", -1, "CMR10")
    assert tok.latex is not None, "the glyph must still be identified"
    assert tok.latex != "-", "a bare - inside maths is a binary minus"
    assert tok.latex == r"\text{-}"


def test_the_maths_italic_face_says_the_same():
    """Both paths read the one entry, so both must give the hyphen."""
    tok = texmap.project("maths-italic", "hyphen", -1, "CMMI10")
    if tok.latex is not None:
        assert tok.latex == r"\text{-}"


def test_the_dashes_are_untouched():
    """An em dash and an en dash are text punctuation and were never minuses."""
    assert texmap.project("text-cm", "emdash", -1, "CMR10").latex == "---"
    assert texmap.project("text-cm", "endash", -1, "CMR10").latex == "--"


def test_a_real_minus_is_still_a_minus():
    for name in ("minus",):
        tok = texmap.project("maths-symbol", name, -1, "CMSY10")
        if tok.latex is not None:
            assert "text" not in tok.latex, "%s must stay a maths minus" % name
