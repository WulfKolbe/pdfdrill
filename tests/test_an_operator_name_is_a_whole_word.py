r"""`klim` is not `k\lim`: an operator name needs a boundary on BOTH sides.

`math_assembler._match_operator_name` turns a run of letters in a math span
into the LaTeX operator it names — `lim` becomes `\lim`, which typesets
upright with the spacing an operator gets, instead of the product l*i*m.

It tested one side of the name only:

    after = pos + len(name)
    if after >= end or not text[after].isalpha():
        return (_OPERATOR_NAMES[name], len(name))

and the main loop walks the span one character at a time, so after emitting
`k` it asks again from the next position. In `klim` the tail `lim` passes:
nothing follows it, so the guard is satisfied, and the span is written
`k\lim`. Every name in the table has this shape — `xlog`, `Nmax`, `vdim`,
`slog` — and the operators are exactly the short letter runs most likely to
end a subscripted identifier.

The rule the code already states for the right-hand side is the rule; this
states it for the left as well, and symmetrically. `lim2` was already
`\lim 2` and stays so, so `2lim` stays `2\lim`: a DIGIT is a boundary on
either side, and only a letter is not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("pydantic")          # the layer pipeline's context model

from pdfdrill.nodes.math_assembler import _match_operator_name as match


def _hits(text):
    """Every position in `text` where an operator name is recognised."""
    return [(i, m[0]) for i in range(len(text))
            if (m := match(text, i, len(text)))]


def test_a_name_that_stands_alone_is_an_operator():
    assert _hits("lim") == [(0, "lim")]
    assert _hits("log") == [(0, "log")]
    assert _hits("arctan") == [(0, "arctan")]


def test_a_letter_before_the_name_is_not_a_boundary():
    """The defect: the tail of an identifier read as an operator."""
    assert _hits("klim") == [], "klim was written k\\lim"
    assert _hits("xlog") == [], "xlog was written x\\log"
    assert _hits("Nmax") == [], "Nmax was written N\\max"
    assert _hits("vdim") == [], "vdim was written v\\dim"


def test_a_letter_after_the_name_is_still_not_a_boundary():
    """The guard that was already there has not been weakened."""
    assert _hits("limit") == []
    assert _hits("logic") == []


def test_a_digit_is_a_boundary_on_either_side():
    """`lim2` was already an operator followed by a 2, so `2lim` is a 2
    followed by an operator. The two sides are stated the same way."""
    assert _hits("lim2") == [(0, "lim")]
    assert _hits("2lim") == [(1, "lim")]


def test_a_name_inside_a_longer_run_is_not_an_operator():
    """Both boundaries fail at once, which is the common case in prose-like
    glyph runs: nothing in `alimit` is an operator."""
    assert _hits("alimit") == []
    assert _hits("sloggy") == []


def test_the_longest_name_still_wins_at_a_real_boundary():
    """`arcsin` must not be read as `arc` + `sin`; the table is scanned
    longest-first and that ordering is load-bearing."""
    assert _hits(" arcsin ") == [(1, "arcsin")]
