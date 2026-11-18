r"""A row that already straddles the bar is a finished fraction.

The fraction-bar merge exists because baseline grouping necessarily puts a
numerator and a denominator in different rows: the bar is the evidence that
those two rows are one line, so it joins them, or no `\frac` could ever be
built.

But `_group_lines`' script fold runs first, and it sometimes ALREADY has both
halves in one row. The bar then merges that finished row with whatever sits
nearest above, which on lib:c57ac038ae5f p293 is a complete sentence:

    By (13.5) we have Q(xk + apk) = ... where rk :=b-Axk.SincepTk Apk >= 0...

-- two text rows run together, the second's spaces lost. The same happens
where `rTk rk / rTk Ark` pulls in "are orthogonal. Indeed, ...". The rows are
caught because the host row's own superscripts fall inside the bar's x-range.

THE GUARD: a row holding glyphs both ABOVE and BELOW the bar inside its
x-range is already the whole fraction, so it is not a merge candidate. A real
two-row fraction has each half on one side only, so it still merges -- which
is the second test here, and the one that must not be lost.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.docmodel_six import RuleNode, _row_straddles_bar  # noqa: E402


class _G:
    """Only what the predicate reads: an x-range and a baseline."""
    def __init__(self, x0, x1, baseline):
        self.rect = (x0, baseline, x1, baseline + 6.0)
        self.baseline = baseline


def _bar(x0=302.0, x1=311.0, y=523.0):
    return RuleNode(id="r", page=1, rect=(x0, y - 0.2, x1, y + 0.2),
                    role="fraction")


def test_a_row_with_glyphs_on_both_sides_of_the_bar_straddles_it():
    """The c57ac case: one row already holds numerator and denominator."""
    row = [_G(303.0, 309.0, 527.0), _G(303.0, 309.0, 519.0)]
    assert _row_straddles_bar(row, _bar(), 11.0) is True


def test_a_numerator_only_row_does_not_straddle():
    """A REAL two-row fraction must still merge: this is the half that would
    be lost if the guard were written too wide."""
    assert _row_straddles_bar([_G(303.0, 309.0, 527.0)], _bar(), 11.0) is False
    assert _row_straddles_bar([_G(303.0, 309.0, 519.0)], _bar(), 11.0) is False


def test_glyphs_outside_the_bars_x_range_do_not_count():
    """A row of prose crossing the page is not a fraction because it passes
    above and below some bar elsewhere on the line."""
    row = [_G(100.0, 120.0, 527.0), _G(400.0, 420.0, 519.0)]
    assert _row_straddles_bar(row, _bar(), 11.0) is False


def test_a_row_far_from_the_bar_does_not_straddle_it():
    """Two line-heights is the window `_near_rows` already uses."""
    row = [_G(303.0, 309.0, 523.0 + 40.0), _G(303.0, 309.0, 523.0 - 40.0)]
    assert _row_straddles_bar(row, _bar(), 11.0) is False
