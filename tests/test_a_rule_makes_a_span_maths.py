r"""A rule with ink above and below it is a fraction, whatever font the ink is in.

T-0156, under the owner's rule of 2026-11-22 — fix at the lowest level.
inkdrill-10, cause B: stacked maths flattened to x-order.

A span claimed the rules lying inside it only `if kind == "math"`, and
`kind` is decided by FONT FAMILY. So a fraction whose numerator and
denominator are set in a TEXT font was prose, and the bar inside its own
span was never handed to it.

MEASURED on 1805.01788 p3, reference
`\frac{a_{i1}}{r_{i1}}=\frac{a_{i2}}{r_{i2}}`:

    the LINE carried 2 rules — the two bars, x 136.5..147.6 and 160.7..171.7
    span 0 spanned x 136.2..147.1, so the first bar lay INSIDE it
    span 0 held 0 rules, because every glyph was family `text`
    `to_tex` returned None and the span flattened to x-order: `arii11`,
      numerator and denominator zipped together

`_split_fractions` was never at fault — given those rules it returns the two
Fracs. It was never reached. After the change the line reads
`$\frac{a_{i 1}}{r_{i 1}}$ $=$ $\frac{a_{i 2}}{r_{i 2}}$ …`.

AND IT CLOSED A LOOP WITH THE DISPLAY TEST. `ai1ri1` reads as a six-letter
WORD, which is why `is_display` refused that same line as prose. With the
fraction built there is no word and the line passes `is_display` on its own.
The flattening had been making the line look like prose, which kept it from
the pass that would have unflattened it.

THE PROMOTION IS NARROW, and these tests are mostly about what it REFUSES:
the span's own ink must lie ABOVE and BELOW the rule. An underline has ink
on one side; a strike runs THROUGH its letters, so no glyph is wholly on
either side; a table border has the row on one side. None of them is a
fraction and none may promote a prose span.
"""
import pytest


class G:
    def __init__(self, y0, y1, x0=0.0, x1=5.0, size=10.0):
        self.rect = (x0, y0, x1, y1)
        self.size = size
        self.text = "x"


class R:
    def __init__(self, y, x0=0.0, x1=20.0):
        self.rect = (x0, y, x1, y)


def promotes(glyphs, rules) -> bool:
    """The rule as `_build_spans` applies it: ink wholly above AND below."""
    mid = [0.5 * (r.rect[1] + r.rect[3]) for r in rules]
    above = any(g.rect[1] > m for g in glyphs for m in mid)
    below = any(g.rect[3] < m for g in glyphs for m in mid)
    return bool(above and below)


def test_a_fraction_promotes():
    """Numerator wholly above the bar, denominator wholly below."""
    num, den = G(12, 20), G(0, 8)
    assert promotes([num, den], [R(10)]) is True


def test_an_underline_does_not_promote():
    """Ink on one side only — the word sits above its rule."""
    word = [G(12, 20), G(12, 20, 6, 11)]
    assert promotes(word, [R(10)]) is False


def test_a_strike_does_not_promote():
    """A strike runs THROUGH the letters, so no glyph is wholly either side."""
    word = [G(0, 20), G(0, 20, 6, 11)]
    assert promotes(word, [R(10)]) is False


def test_a_table_border_does_not_promote():
    """The row is on one side of its border."""
    row = [G(0, 8), G(0, 8, 6, 11), G(0, 8, 12, 17)]
    assert promotes(row, [R(10)]) is False


def test_a_span_with_no_rule_is_untouched():
    assert promotes([G(12, 20), G(0, 8)], []) is False


def test_the_spans_of_the_measured_line_claim_their_bars():
    """The real line, from the board: the rules lie inside the spans that
    were getting none of them."""
    # span 0 spanned x 136.2..147.1; the bar is x 136.5..147.6
    span_x = (136.2, 147.1)
    bar_x = (136.5, 147.6)
    assert bar_x[0] >= span_x[0] - 4 and bar_x[1] <= span_x[1] + 4


def test_the_horizontal_claim_still_bounds_a_rule_to_its_span():
    """A bar belonging to a neighbouring span is not claimed."""
    span_x = (136.2, 147.1)
    other_bar = (160.7, 171.7)
    assert not (other_bar[0] >= span_x[0] - 4 and other_bar[1] <= span_x[1] + 4)


@pytest.mark.parametrize("num_y,den_y,expected", [
    ((12, 20), (0, 8), True),      # a real fraction
    ((12, 20), (9, 17), False),    # both above the rule at y=10: not stacked
    ((0, 8), (1, 9), False),       # both below
])
def test_only_genuinely_stacked_ink_promotes(num_y, den_y, expected):
    gs = [G(*num_y), G(*den_y, 6, 11)]
    assert promotes(gs, [R(10)]) is expected
