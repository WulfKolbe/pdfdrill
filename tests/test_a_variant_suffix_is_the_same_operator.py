r"""`summationdisplay.1` is a `\sum`, to the limit tables as to everything else.

T-0199. `texmap.project` states the rule and acts on it -- "A NAME WITH A
VARIANT SUFFIX IS THE SAME GLYPH", PostScript's `<name>.<variant>` -- so a
txfonts `\sum` is named and projected correctly. `may_take_limits` and
`takes_limits` are keyed by the base name too, but were handed the RAW name,
so `summationdisplay.1` answered False to both and the limit machinery in
`structure.py` was simply off on every txfonts document: no limit claimed back
from the operator's left (741), no owner decided by the stream (760), no
`\limits` where the page sets the condition underneath.

MEASURED over the corpus, by asking pdfminer's font objects for the names the
font states:

    board52      30 documents,    9 carry a large operator,   1 suffixed
    library   5,445 documents, 4,245 carry a large operator,  98 suffixed

Every one of the 98 is `txexs`; 41 arXiv e-prints, 57 library books. On the
board it moves exactly the one page the census predicts -- 1805.01788 p3,
`\limits` 0 -> 19, content characters lost 0 and gained 0 on all 30.

WHAT THIS FILE OWNS is that the two questions are asked of the glyph and not
of its spelling, and that stripping the suffix does not blur the three
distinctions the tables exist to make: display from text style, the sum class
from named operators, and either from an integral.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

T = pytest.importorskip("pdfreader.texmap")


@pytest.mark.parametrize("name", [
    "summationdisplay", "productdisplay", "coproductdisplay", "uniondisplay",
    "intersectiondisplay", "circleplusdisplay", "logicalanddisplay",
])
def test_a_display_operator_takes_limits_with_or_without_a_suffix(name):
    """Both spellings, both questions, same answer."""
    for spelling in (name, name + ".1"):
        assert T.takes_limits(glyphname=spelling), spelling
        assert T.may_take_limits(glyphname=spelling), spelling


@pytest.mark.parametrize("name", ["summationtext", "producttext",
                                  "uniontext", "intersectiontext"])
def test_a_text_style_operator_keeps_its_own_answer(name):
    r"""The `display`/`text` suffix is the size TeX chose, and that IS the
    statement of which style the row is in -- so `summationtext` MAY carry
    limits (measured: `producttext` 31 under against 9 beside) but does not
    take them by default. Stripping the VARIANT suffix must not collapse that
    distinction, which is carried by a different part of the same name."""
    for spelling in (name, name + ".1"):
        assert not T.takes_limits(glyphname=spelling), spelling
        assert T.may_take_limits(glyphname=spelling), spelling


@pytest.mark.parametrize("spelling", ["integraldisplay", "integraldisplay.1",
                                      "integraltext", "contintegraldisplay"])
def test_an_integral_is_not_in_the_class_whatever_its_spelling(spelling):
    r"""`\int` is `\nolimits` even in display style -- 2 under against 21
    beside over the 102 documents -- so `_LARGE_OP_STEMS` leaves integrals
    out. A looser suffix rule must not let one back in."""
    assert not T.takes_limits(glyphname=spelling), spelling
    assert not T.may_take_limits(glyphname=spelling), spelling


def test_a_named_operator_is_still_answered_by_its_control_sequence():
    r"""The other half of both functions: `\max`, `\sup`, `\lim` come from
    `amsopn.sty`'s own list and are asked by LaTeX name, not by glyph."""
    for cmd in (r"\max", r"\sup", r"\lim", r"\limsup", r"\det", r"\Pr"):
        assert T.takes_limits(latex=cmd), cmd
        assert T.may_take_limits(latex=cmd), cmd
    for cmd in (r"\log", r"\sin", r"\cos", r"\tanh", r"\exp"):
        assert not T.takes_limits(latex=cmd), cmd
        assert not T.may_take_limits(latex=cmd), cmd


def test_a_suffix_does_not_invent_an_operator():
    """Stripping is not matching. A name whose base is not in the tables
    answers False, suffix or no suffix, and so does a name that is only a
    suffix or nothing at all."""
    for spelling in ("summation", "summationdisplay2", "sum", "sumdisplay",
                     "radical.alt", "y.alt", "f_i.1", ".1", "", None):
        assert not T.takes_limits(glyphname=spelling), repr(spelling)
        assert not T.may_take_limits(glyphname=spelling), repr(spelling)


def test_the_base_name_is_what_the_tables_are_keyed_by():
    """The helper itself: everything up to the first dot, and nothing clever.

    `uni222B.dsp` and `summationdisplay.1` are both real names out of
    `txexs`; `.alt`, `.sc` and `.1` are all PostScript variant spellings and
    none of them is a different glyph.
    """
    assert T._operator_basename("summationdisplay.1") == "summationdisplay"
    assert T._operator_basename("summationdisplay") == "summationdisplay"
    assert T._operator_basename("uni222B.dsp") == "uni222B"
    assert T._operator_basename("radical.alt") == "radical"
    assert T._operator_basename("a.b.c") == "a"
    assert T._operator_basename(".1") is None
    assert T._operator_basename("") is None
    assert T._operator_basename(None) is None
