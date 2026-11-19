r"""A fraction bar claims the rows BESIDE it, not the whole column.

Traced by inkdrill-10 on the board's worst ours row.

1. `_off_row_by_rule` asks that a glyph's centre fall in the bar's x-range and
   that its baseline be off the bar's axis by more than 0.12 em. It bounds the
   distance BELOW and not above, so a glyph 200 pt away still counts as a
   numerator. On 2312.11532 p7 `_rule_role` calls the table's booktabs midrule
   and six 126.6 pt chart axes "fraction", and whole body rows in their
   x-range were then moved into the stream-preceding row:

       "...in ETM, which" + "also utilizes Word2Vec." as one line

   ours 0.5290 against MathPix 0.0917, unpaired 773/758. A bar belongs to the
   rows next to it: the bound is 1.5 em, the same window `_near_rows` uses.

NOT FIXED HERE, AND NOT FOR WANT OF TRYING: the second half of the same
trace. `_off_row_band` calls a row a band of scripts when every glyph is
smaller than 0.95 em, so 0864 p4's small-caps method names -- GREEDY at
7.2 pt -- are taken for scripts and moved into the line ABOVE. Two rules were
written for "a band of scripts holds no prose word" and both are wrong:

  1. letters closer than 1.5 em apart. inkdrill-10 measured it: scripts on
     NEIGHBOURING BASES are that close, so lib:b21e554b9232 p201 lost
     `f_{ab}`'s subscript (0.0021 -> 0.0126) and lib:3fe71b4ef018 p328 split
     eq. 14.4.17's numerator (0.0631 -> 0.0906).
  2. letters that TOUCH, share a size and share a baseline. That is also what
     a multi-letter SUBSCRIPT is -- `spc`, `mon`, `ir` -- and
     `TestACodeListingIsNotABandOfScripts` already holds the contract it
     breaks: a proportional row of that size is still a band.

So the discriminator is not geometric, and a third threshold is not the
answer. 0864 p4 keeps its caption defect until there is a real one.

What must not break, and is tested here: a real fraction, a numerator just
above its bar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.docmodel_six import RuleNode, _off_row_by_rule  # noqa: E402
from pdfreader.texmap import TexToken  # noqa: E402

SPAN = 10.0


class _G:
    """Only what these two predicates read."""
    def __init__(self, x0, x1, baseline, size=10.0, text="x",
                 fontname="NimbusRomNo9L-Regu", family="text"):
        self.rect = (x0, baseline, x1, baseline + size * 0.7)
        self.baseline = baseline
        self.size = size
        self.text = text
        self.fontname = fontname
        self.family = family
        self.tex = TexToken(None, "unknown", None, "none")


def _bar(x0=57.1, x1=289.4, y=349.0):
    return RuleNode(id="r", page=1, rect=(x0, y - 0.3, x1, y + 0.3),
                    role="fraction")


def test_a_numerator_just_above_its_bar_is_off_row():
    """The clause's own purpose, unchanged."""
    g = _G(100.0, 110.0, 349.0 + 5.0)
    assert _off_row_by_rule(g, [_bar()], SPAN) is True


def test_a_denominator_just_below_its_bar_is_off_row():
    g = _G(100.0, 110.0, 349.0 - 5.0)
    assert _off_row_by_rule(g, [_bar()], SPAN) is True


def test_a_body_row_200pt_away_is_not_a_fraction_part():
    """2312.11532 p7: a booktabs midrule reaching the whole column."""
    g = _G(100.0, 110.0, 349.0 + 200.0)
    assert _off_row_by_rule(g, [_bar()], SPAN) is False


def test_a_row_just_outside_the_window_is_not_a_fraction_part():
    g = _G(100.0, 110.0, 349.0 + 1.6 * SPAN)
    assert _off_row_by_rule(g, [_bar()], SPAN) is False
