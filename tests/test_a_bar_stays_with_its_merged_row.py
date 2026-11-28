r"""A fraction bar whose numerator and denominator are already one row.

lib:7e9f02b4f39f p287 (held-out draw): three fractions on one display line.
The first two bars merged the rows, so the third found its row on one side
only, was never assigned, and the general test dropped it: the display
flattened to `22\cos\sin22((tt))`. A row holding glyphs above and below the
bar, within its x-range, is the bar's.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")


def _g(x0, x1, base):
    return SimpleNamespace(rect=(x0, base, x1, base + 10), baseline=base)


BAR = SimpleNamespace(rect=(308.1, 308.0, 342.7, 308.0))


def test_a_row_with_numerator_and_denominator_holds_the_bar():
    row = [_g(310, 316, 314.5), _g(318, 340, 314.5),      # 2 sin^2(t)
           _g(310, 316, 300.4), _g(318, 340, 300.4),      # 2 cos^2(t)
           _g(150, 180, 306.0)]                           # the row's own text
    assert dm._row_holds_both_sides_of(row, BAR)


def test_a_row_on_one_side_does_not():
    row = [_g(310, 316, 300.4), _g(318, 340, 300.4), _g(150, 180, 306.0)]
    assert not dm._row_holds_both_sides_of(row, BAR)


def test_glyphs_outside_the_bar_do_not_count():
    row = [_g(310, 316, 300.4), _g(150, 160, 314.5)]
    assert not dm._row_holds_both_sides_of(row, BAR)
