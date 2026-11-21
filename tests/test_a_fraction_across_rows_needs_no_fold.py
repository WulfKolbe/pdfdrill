r"""A fraction split across rows is joined by the bar's own role, not by a fold.

T-0154. This file used to assert `_fold_fraction_operands`, a pass added in
a9be8375 to join a fraction's operand rows to the row its bar sits in. The
motivating defect was real: lib:c57ac038ae5f p293 wrote `α1 = ,` — the VALUE
LOST — against MathPix's and reader B's `\alpha_{1}=\frac{1}{2}`, with the
three parts of that one fraction on three different reader rows:

    row 28   `α1 =` and the `,`      baseline 71.2    + the bar, y 73.5
    row 29   `1`  the numerator      baseline 78.1
    row 30   `2`  the denominator    baseline 64.1

THE FOLD WAS NOT WHAT FIXED IT, and the measurement that says so came later.
Projected over all 30 board52 pages with the fold disabled, the output is
IDENTICAL — p293's `\alpha_{1} = \frac{1}{2}` and its eleven `\frac` included.
The fold was not idle either: it fired on 6 of those pages and merged 24 rows,
6 of them on p293 itself. Every one of those merges was already being made by
the fraction row-merge in `build` (`_near_rows`), which joins the rows above
and below a bar for EVERY rule whose role is `fraction`.

What actually recovered α1 was the `_rule_role` delimiter exclusion in the same
commit: a tall `\bigr]` drawn raised sat within 0.1 em of the numerator's
baseline, so the bar was called an `overline` and the row-merge never ran. Make
the bar a `fraction` and the existing pass does the work. The fold rode along
in the same commit and took the credit for eight days.

`_group_lines` now records THREE folds that stood in that spot and were
removed. The first two measured worse. This one measured as nothing at all,
which is the harder case to notice: it had tests, they passed, and they tested
a function whose output never reached the page.

So these tests assert the BEHAVIOUR — a fraction whose parts lie on separate
rows is read as a fraction — and never the pass that performs it.
"""
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")

#: The board page, when this machine happens to hold a board run. NEVER a
#: literal home directory: `test_an_install_outside_the_owners_tree` fails the
#: suite for naming one machine's tree, and it is right to — a path that
#: locates one checkout measures that checkout wherever it is run.
_BOARD = os.environ.get("DRILLGROUP_WORK") or os.path.join(
    os.path.expanduser("~"), "drillgroup", "work")


def _p293():
    found = sorted(glob.glob(os.path.join(
        _BOARD, "board*", "lib_c57ac038ae5f-p0293", "*.pdf")))
    if not found:
        pytest.skip("no board run on this machine (set DRILLGROUP_WORK)")
    return found[-1]


def test_the_fold_is_gone_and_stays_gone():
    """A pass that changes no page is not kept because it has tests."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfreader" / "docmodel_six.py").read_text()
    assert "def _fold_fraction_operands" not in src
    assert "_FRAC_OPERAND_EM" not in src
    #: and the note that says why, so the next reader does not re-add it
    assert "A THIRD FOLD STOOD HERE AND IS GONE" in src


def test_group_lines_does_not_take_rules_any_more():
    """The parameter existed only to carry the bar to the fold."""
    import inspect
    assert "rules" not in inspect.signature(D._group_lines).parameters


def test_alpha_one_keeps_its_value():
    r"""The defect the fold was written for, measured on the page itself:
    `\alpha_{1} = \frac{1}{2}`, not `α1 = ,`."""
    js = D.to_lines_json(D.build(_p293()))
    text = "\n".join(ln.get("text") or ""
                     for pg in js["pages"] for ln in pg["lines"])
    assert r"\alpha_{1} = \frac{1}{2}" in text, (
        "p293's alpha_1 lost its value again")


def test_the_page_keeps_its_fractions():
    """Eleven, the count a9be8375 reached and this must not fall below."""
    js = D.to_lines_json(D.build(_p293()))
    text = "\n".join(ln.get("text") or ""
                     for pg in js["pages"] for ln in pg["lines"])
    assert text.count(r"\frac") >= 11, text.count(r"\frac")


def test_a_bar_with_one_operand_row_is_not_a_fraction():
    r"""The rule the fold also encoded, and which `_rule_role` holds on its
    own: a bar with a row on ONE side is an `\overline` or a minus, and
    nothing joins across it."""
    from pdfreader.texmap import UNKNOWN

    def g(x0, text, baseline, size=10.0):
        return D.GlyphNode(
            id="g%s_%s" % (x0, baseline), page=1,
            rect=(x0, baseline - size, x0 + 0.5 * size, baseline),
            text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
            family="math-italic", size=size, tex=UNKNOWN,
            matrix=(size, 0, 0, size, x0, baseline))

    rule = D.RuleNode(id="r", page=1, rect=(60.0, 100.0, 70.0, 100.4))
    glyphs = [g(61.0, "x", 108.0)]            # above only: an overline
    role = D._rule_role(rule, glyphs, 10.0, [rule], page_width=600.0)
    assert role != "fraction", role
