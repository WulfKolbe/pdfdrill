r"""A span boundary must not fall inside a fraction bar.

T-0154, rule 4, and the regression is mine: `a9be8375` raised 1805.01788 p3
from 0.0215 to 0.0229 (unpaired_A 27 -> 30, unpaired_B 39 -> 42, glyph
findings 19 -> 21).

WHAT ACTUALLY CAUSED IT, measured by reverting each half of that commit on its
own: NOT the fraction-operand fold, which refuses this page (the denominator
row starts at x 437.6, left of the bar's 451.7, so `below` is None). It was the
other half, the `_rule_role` delimiter exclusion, which correctly re-read the
DCG display's bar as a `fraction` where it had been an `overline`. That woke
the fraction row-merge at `docmodel_six.py:4035`, which had never fired here.

So the commit found a real fraction that had been missed for as long as the
page has been read, and what it exposed was that nothing downstream could
build it:

    page       DCG@k(r) = \sum_{i=1}^{k} \frac{2^{r(i)} - 1}{\log_2(i+1)}
    board50    DCG@k $(r$ $) =$ $\sum^{k}$ \textit{r} ${}^{(i}$ ${}^{)}$
               2 $-$ 1
               \textit{i} ${}^{=1}$ \textit{loд} ${}_{2}(i$ $+ 1)$
    board51    DCG@k $(r$ $) =$ $\sum^{k}$ i=1 2r ${}^{(i}$ ${}^{)} -$ 1loд2 $(i$ $+ 1)$

A span claims a rule only when the rule lies ENTIRELY within it, so a bar cut
across two runs is claimed by NEITHER and the fraction is lost without a word:
the line carried the bar and not one of its eleven spans did.

The whole-line guard in `_spans` refuses this line because it is 43% letters
(`DCG`, `log`, the variables), which is ordinary for a display. That guard
protects prose from being swallowed and is left alone — it is the BAR'S OWN
EXTENT that needs protecting, which is what the typesetter drew and what
`_split_fractions` already partitions by.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(x0, text, baseline, size=10.0, stream=0, family="math-italic"):
    return D.GlyphNode(
        id="g%s_%s_%s" % (x0, baseline, text), page=1,
        rect=(x0, baseline - size, x0 + 0.5 * size, baseline),
        text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
        family=family, size=size, tex=UNKNOWN, stream=stream,
        matrix=(size, 0, 0, size, x0, baseline))


def _bar(x0, x1, y, role="fraction"):
    return D.RuleNode(id="r", page=1, rect=(x0, y, x1, y + 0.4), role=role)


def _line(glyphs, rules):
    xs = [g.rect[0] for g in glyphs] + [g.rect[2] for g in glyphs]
    ys = [g.rect[1] for g in glyphs] + [g.rect[3] for g in glyphs]
    return D.LineNode(id="l1", page=1,
                      rect=(min(xs), min(ys), max(xs), max(ys)),
                      type="formula", glyphs=glyphs, rules=rules)


def _fraction_line():
    r"""The shape of 1805 p3's DCG display: a name set in a TEXT font, then a
    fraction over a bar at x 60..90.

    The letters must outnumber the whole-line guard's 35%, or `_spans` keeps
    the line whole and this pass is never reached -- which is exactly the
    case the real page presents (`DCG`, `log` and the variables are 43% of
    it) and exactly why the fraction was lost there."""
    bar = _bar(61.0, 85.0, 100.0)
    glyphs = [
        _g(4.0, "D", 100.0, stream=0, family="text"),
        _g(12.0, "C", 100.0, stream=1, family="text"),
        _g(20.0, "G", 100.0, stream=2, family="text"),
        _g(28.0, "k", 100.0, stream=3, family="text"),
        _g(40.0, "=", 100.0, stream=4),
        #: The families ALTERNATE inside the fraction, as they do on the real
        #: page -- `2r` from a text font, `(i)` from a maths one -- which is
        #: what makes the run splitter cut between the bar's two halves.
        _g(62.0, "n", 108.0, stream=5, family="text"),     # numerator
        _g(70.0, "(", 108.0, stream=6, family="math-symbol"),
        _g(78.0, "i", 108.0, stream=7, family="text"),
        _g(62.0, "d", 94.0, stream=8, family="text"),      # denominator
        _g(70.0, "+", 94.0, stream=9, family="math-symbol"),
        _g(78.0, "2", 94.0, stream=10, family="text"),
    ]
    return _line(glyphs, [bar])


def test_one_span_holds_the_whole_bar():
    """Not two spans with the bar between them, and not zero."""
    spans = D._spans(_fraction_line())
    holders = [s for s in spans if s.rules]
    assert len(holders) == 1, (
        "the bar is claimed by %d span(s) of %d; it must be exactly one"
        % (len(holders), len(spans)))
    sp = holders[0]
    assert sp.rect[0] <= 62.0 and sp.rect[2] >= 83.0, (
        "the claiming span must cover the bar, got x %.1f..%.1f"
        % (sp.rect[0], sp.rect[2]))


def test_the_claiming_span_holds_both_halves():
    """A fraction cannot be built from a span that has only one of them."""
    sp = [s for s in D._spans(_fraction_line()) if s.rules][0]
    texts = [g.text for g in sp.glyphs]
    for want in ("n", "i", "d", "2"):
        assert want in texts, (
            "%r is missing from the span that carries the bar: %r"
            % (want, texts))


def test_the_merged_span_keeps_the_order_the_pdf_drew():
    r"""NOT x-order. A fraction's two halves share a column, so sorting the
    merged run by x interleaves them -- which is the defect the whole-line
    branch of `_spans` is written against. Sorted by x, 1805 p3 fell back to
    `$lo2дr2(i()i −+ 11)$`; `to_tex` does not care about the order but the
    FALLBACK does, and the fallback is what a reader sees when `to_tex`
    refuses."""
    sp = [s for s in D._spans(_fraction_line()) if s.rules][0]
    streams = [g.stream for g in sp.glyphs]
    assert streams == sorted(streams), (
        "the merged run must stay in drawn order, got %r" % (streams,))
    #: The two halves in the order drawn, numerator before denominator. The
    #: span may also carry what the run splitter had already put beside them
    #: (here the `=`), which is not this test's business.
    texts = [g.text for g in sp.glyphs]
    want = ["n", "(", "i", "d", "+", "2"]
    assert [t for t in texts if t in want] == want, (
        "the bar's two halves are out of drawn order: %r" % (texts,))


def test_prose_either_side_is_still_split_off():
    """The bar's extent is protected, not the whole line. The guard that
    keeps a mostly-prose line segmented is untouched, so a run that does not
    touch the bar must not be swallowed into the fraction's span."""
    spans = D._spans(_fraction_line())
    assert len(spans) > 1, "the left-hand side was swallowed into the fraction"
    sp = [s for s in spans if s.rules][0]
    assert "D" not in [g.text for g in sp.glyphs]


def test_a_line_whose_bar_lies_in_one_run_is_untouched():
    """No merge where there is nothing to merge: the pass must be a no-op
    unless a boundary actually falls inside a bar."""
    bar = _bar(61.0, 68.0, 100.0)
    glyphs = [_g(62.0, "n", 108.0, stream=0), _g(62.0, "d", 94.0, stream=1)]
    spans = D._spans(_line(glyphs, [bar]))
    assert len(spans) == 1 and spans[0].rules
