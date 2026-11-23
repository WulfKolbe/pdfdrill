r"""T-0159 — `\right)^2` was read as `\bigr)_{2}`: a superscript became a sub.

Measured against the author with the frozen labeller (drillgroup
scripts/eq_calibrate.py at 1ae04df, work/run-files/t0159/confirm3b), on
arxiv.1710.04811 page 37 — which that run labels as its page 1:

    author     \left(S_R^2\right)^2\left(S_L^2 S_R^2+\sin^2\theta_H\right)^2=0
    pdfdrill   \bigl(S_{R}^{2} \bigr)_{2} \bigl(S_{L}^{2} S_{R}^{2}
               + \sin^{2} \theta_{H} \bigr)_{2} = 0 .      correct 0
    pdf2mmd2   \bigl(S_{R}^{2}\bigr)^{2} ...                correct 1

and BOTH rows score residual 0.0000, which is the T-0158 judge blindness the
coordinator recorded: sub and super are not identical ink, so a 0 there is a
defect in the judge, not a pass for the reading. The author check is what sees
this.

THE CAUSE, from the page's own geometry (line p37l23):

    parenrightbig   baseline 372.50   +9.70 from the row
    the `2` after   baseline 369.82   +7.02 from the row

    against the DELIMITER's baseline   369.82 - 372.50 = -2.68  -> subscript
    against the ROW's baseline         +7.02                    -> superscript

A `\big` delimiter is drawn RAISED — grown about the maths axis, not set on
the line — and `_attach_scripts` says so itself two comments above the test
that then uses the delimiter's own baseline as the reference. For a big
OPERATOR that is right: `\sum_j^n` centres its limits on its own axis. For a
DELIMITER it is wrong: the exponent of `\right)` is an ordinary script of the
bracketed group and sits on the row's levels. The inner exponents on this
line, at +4.95 over an `S` at +0.02, were never affected — only a script
after a raised delimiter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader.docmodel_six import GlyphNode, TexToken        # noqa: E402
from pdfreader.structure import _attach_scripts               # noqa: E402

ROW = 362.82          # the measured row baseline of p37l23


def _g(x0, base, w, text, name, *, size=12.0, kind="atom",
       family="text-cm"):
    return GlyphNode(
        id=f"g{x0}", page=37,
        rect=(x0, base - 0.2 * size, x0 + w, base + 0.7 * size),
        text=text, cid=1, glyphname=name, fontname="CMR12", family=family,
        size=size, tex=TexToken(text, kind, None, "corpus"),
        matrix=(1, 0, 0, 1, x0, base))


def _p37l23_head():
    r"""`\left(S_R^2\right)^2` as the page draws it, to the measurement above."""
    return [
        _g(222.3, 372.50, 5.5, "(", "parenleftbig", kind="delimiter"),
        _g(227.8, ROW, 7.2, "S", "S"),
        _g(235.0, 359.86, 0.7, "R", "R", size=8.0),
        _g(235.7, 367.75, 6.2, "2", "two", size=8.0),
        _g(241.9, 372.50, 5.5, ")", "parenrightbig", kind="delimiter"),
        _g(247.4, 369.82, 6.7, "2", "two", size=8.0),
        _g(349.8, ROW, 12.4, "=", "equal"),
        _g(362.2, ROW, 9.8, "0", "zero"),
    ]


def _triple_for(out, name):
    for main, sup, sub in out:
        if main is not None and main.glyphname == name:
            return sup, sub
    raise AssertionError(f"no triple whose base is {name}: "
                         f"{[(m.glyphname if m else None) for m, _s, _b in out]}")


def test_the_exponent_of_a_big_delimiter_is_a_superscript():
    """THE RED. 2 objects on 1710.04811 p37, both `correct 0` against the
    author purely because of the side."""
    out = _attach_scripts(_p37l23_head())
    assert out is not None, "the row refused outright"
    sup, sub = _triple_for(out, "parenrightbig")
    assert [g.text for g in sup] == ["2"], (
        f"the exponent is not a superscript of the delimiter: "
        f"sup={[g.text for g in sup]} sub={[g.text for g in sub]}")
    assert not sub


def test_the_inner_exponent_is_unaffected():
    """It follows an `S` on the row, so it was always right. The guard that
    the fix does not move what already worked."""
    out = _attach_scripts(_p37l23_head())
    sup, sub = _triple_for(out, "S")
    assert "2" in [g.text for g in sup]
    assert [g.text for g in sub] == ["R"]


def test_a_big_operator_still_measures_against_its_own_baseline():
    r"""The asymmetry, and the reason this is not a blanket change.
    `\sum_j^n` is grown about the maths axis and its limits centre on IT, so
    a limit below the operator's raised baseline but above the row's is a
    SUBSCRIPT -- the opposite reading from the delimiter case."""
    row = [
        _g(100.0, ROW, 9.0, "x", "x"),
        _g(112.0, ROW + 9.7, 12.0, "∑", "summationdisplay", kind="bigop"),
        _g(115.0, ROW + 7.0, 5.0, "j", "j", size=8.0),   # below the sum's axis
        _g(130.0, ROW, 9.0, "y", "y"),
    ]
    out = _attach_scripts(row)
    assert out is not None
    sup, sub = _triple_for(out, "summationdisplay")
    assert [g.text for g in sub] == ["j"], (
        f"a big operator's limit was re-referenced to the row: "
        f"sup={[g.text for g in sup]} sub={[g.text for g in sub]}")
    assert not sup


def test_a_subscript_after_a_big_delimiter_is_still_a_subscript():
    """The other side of the same test: `\\bigr)_{i}` exists too, and it sits
    BELOW the row's baseline, not merely below the delimiter's."""
    row = _p37l23_head()
    row[5] = _g(247.4, ROW - 2.9, 6.7, "i", "i", size=8.0)
    out = _attach_scripts(row)
    assert out is not None
    sup, sub = _triple_for(out, "parenrightbig")
    assert [g.text for g in sub] == ["i"], (
        f"sup={[g.text for g in sup]} sub={[g.text for g in sub]}")
