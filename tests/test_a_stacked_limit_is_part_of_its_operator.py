r"""A big operator's lower limit belongs to the operator's span.

T-0199. The queue's gate was "1805 p3 reads \sum_{i=1}^{k}, and no page loses
characters". What the page showed before:

    page       DCG@k(r) = \sum_{i=1}^{k} \frac{2^{r(i)} - 1}{\log_2(i+1)}
    board54    DCG@k $(r$ $) =$ $\sum^{k}$ i=1 $\frac{2^{r (i )} - 1}{...}$

`i=1` -- the condition -- sat OUTSIDE the mathematics as plain text, and the
same shape cost the page's other display three more conditions:

    board54    ... $= \sum^{n}$ i=1 $\sum^{m}$ j=1 \textit{a} $- \sum^{m}$ ...

WHERE IT WAS LOST, measured. Not in the structure pass: `structure.to_tex` on
those same glyphs AS ONE GROUP already answers `\sum_{i=1}^{k}`, and likewise
`\sum_{i=1}^{n}|A_i - R_i| = ...` for the other display. It was the SPAN
BOUNDARY, and the gate that drew it is `_tight`, which requires two runs to
MEET ON THE PAGE:

    summationdisplay  x 437.2..449.0  y  99.96..111.61  base 102.65
    k   upper limit   x 440.8..444.6  y 102.75..110.03  base 104.44
    i = 1             x 437.6..448.5  y  81.24.. 88.52  base  82.93

The upper limit overlaps the operator's box, so it was absorbed. The lower
limit is 11.4pt clear of it -- which is not a defect in the page, it is how
TeX sets a limit -- so it failed `_tight` and stayed prose. `_tight` is right
about what it was built for (a CMEX radical whose baseline is on this line and
whose ink is 30pt lower stole the `on` of `only`); a stacked limit simply has
the same shape and the opposite answer.

The rule added for it is the triple the band merge at 730/740 already uses to
tell a limit from a second equation -- script size, centred on the operator's
column, a baseline window scaled to the operator -- so the tests below are
mostly about what it must still REFUSE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import TexToken, UNKNOWN

SUM = TexToken("\\sum", "bigop", None, "corpus")
INT = TexToken("\\int", "bigop", None, "corpus")

BODY = 9.0            # the row's type size
SCRIPT = 7.3          # what TeX sets a limit at


def _g(x0, text, baseline, size=BODY, stream=0, family="math-italic",
       glyphname=None, tex=UNKNOWN, width=None, top=None):
    r"""One glyph, in the page's own convention: the baseline IS the origin.

    `rect[1]` is the baseline and `rect[3]` the top, which is how the real
    glyphs measure (`=` base 93.47, box 93.47..102.44 on 1805 p3) -- so a
    limit set clear of its operator really does fail to overlap it here.
    """
    w = 0.5 * size if width is None else width
    return D.GlyphNode(
        id="g%s_%s_%s" % (x0, baseline, text), page=1,
        rect=(x0, baseline, x0 + w, baseline + size if top is None else top),
        text=text, cid=0, glyphname=glyphname, fontname="ABC+txexs",
        family=family, size=size, tex=tex, stream=stream,
        matrix=(size, 0, 0, size, x0, baseline))


def _line(glyphs, rules=()):
    xs = [g.rect[0] for g in glyphs] + [g.rect[2] for g in glyphs]
    ys = [g.rect[1] for g in glyphs] + [g.rect[3] for g in glyphs]
    return D.LineNode(id="l1", page=1,
                      rect=(min(xs), min(ys), max(xs), max(ys)),
                      type="formula", glyphs=list(glyphs), rules=list(rules))


def _sum_glyph(glyphname="summationdisplay.1", tex=SUM):
    """The operator: x 40..52, drawn 106..118, origin on 109.

    The name carries the PostScript variant suffix on purpose -- it is what
    txfonts gives every `\\sum` on 1805.01788, and the limit tables are keyed
    by the base name.
    """
    return _g(40.0, "∑", 109.0, size=BODY, stream=5,
              family="math-extension", glyphname=glyphname, tex=tex,
              width=12.0, top=118.0)


def _display(glyphname="summationdisplay.1", tex=SUM, lower_base=89.0,
             lower_x=40.4, lower_size=SCRIPT):
    r"""`DCG = \sum_{i=1}^{k}` in TeX's own emission order.

    The three roman letters are deliberate: they are 43% of the real line and
    they are what keeps `_mostly_math` off it, so none of the relaxations that
    rule depends on can be what rescues the limit here.
    """
    return [
        _g(4.0, "D", 100.0, stream=0, family="text"),
        _g(10.0, "C", 100.0, stream=1, family="text"),
        _g(16.0, "G", 100.0, stream=2, family="text"),
        _g(26.0, "=", 100.0, stream=3, family="text"),
        # the upper limit, emitted before the operator (a vbox ships top-down)
        _g(43.5, "k", 111.0, size=SCRIPT, stream=4, family="text"),
        _sum_glyph(glyphname, tex),
        # and the lower limit, clear of the operator's box
        _g(lower_x, "i", lower_base, size=lower_size, stream=6, family="text"),
        _g(lower_x + 3.0, "=", lower_base, size=lower_size, stream=7,
           family="text"),
        _g(lower_x + 7.5, "1", lower_base, size=lower_size, stream=8,
           family="text"),
    ]


def _groups_after(tex, cmd):
    r"""The `_{...}` and `^{...}` groups attached to `cmd`, brace-matched.

    Written out rather than regexed because the groups nest: a limit may
    carry `\mathrm{i}` inside it.
    """
    i = tex.find(cmd)
    if i < 0:
        return None, None
    i += len(cmd)
    # `\limits` may stand between the operator and its scripts: the projector
    # emits it when the scripts are measured UNDER the operator rather than
    # beside it, which for a text-style `\sum` is the only way LaTeX can be
    # told what the page shows. It says nothing about the groups.
    for mod in ("\\limits", "\\nolimits"):
        if tex.startswith(mod, i):
            i += len(mod)
            break
    found = {}
    while i < len(tex) and tex[i] in "_^":
        mark, i = tex[i], i + 1
        if i >= len(tex) or tex[i] != "{":
            return None, None
        depth, j = 0, i
        while j < len(tex):
            if tex[j] == "{":
                depth += 1
            elif tex[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        found[mark] = tex[i + 1:j]
        i = j + 1
    return found.get("_"), found.get("^")


def _span_of(spans, text):
    for s in spans:
        if "".join(g.text for g in s.glyphs) == text:
            return s
    return None


def _kinds(spans):
    return [(s.kind, "".join(g.text for g in s.glyphs)) for s in spans]


def test_the_lower_limit_is_not_a_text_span_of_its_own():
    """The defect itself: `i=1` came out as prose beside the operator."""
    spans = D._spans(_line(_display()))
    assert _span_of(spans, "i=1") is None, _kinds(spans)
    assert not any(s.kind == "text" and "i" in "".join(g.text for g in s.glyphs)
                   and "1" in "".join(g.text for g in s.glyphs)
                   for s in spans), _kinds(spans)


def test_operator_and_both_limits_land_in_one_maths_span():
    """And they must be in the SAME span, or no pass can build the limits."""
    spans = D._spans(_line(_display()))
    holding = [s for s in spans
               if any(g.tex.kind == "bigop" for g in s.glyphs)]
    assert len(holding) == 1, _kinds(spans)
    span = holding[0]
    assert span.kind == "math", _kinds(spans)
    chars = "".join(g.text for g in span.glyphs)
    for ch in ("∑", "k", "i", "1"):
        assert ch in chars, (ch, _kinds(spans))


def test_the_span_reads_the_limits_as_limits():
    r"""What the gate asks for: `\sum_{i=1}^{k}`, not `\sum^{k}` and prose."""
    structure = pytest.importorskip("pdfreader.structure")
    spans = D._spans(_line(_display()))
    span = [s for s in spans
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    tex = structure.to_tex(sorted(span.glyphs, key=lambda g: g.rect[0]),
                           list(span.rules))
    assert tex is not None
    assert "\\sum" in tex
    # THE GROUPS, NOT THE SPELLING. These glyphs are set in a text font, so
    # the projection wraps them `\mathrm{...}` and spaces them `\!` -- which
    # is the fixture's font choice, not the shape under test. What this test
    # owns is that the condition is a SUBSCRIPT GROUP on the operator and
    # that `k` is its superscript, which is what `\sum^{k}` + prose was not.
    sub, sup = _groups_after(tex, "\\sum")
    assert sub is not None and sup is not None, tex
    for ch in ("i", "=", "1"):
        assert ch in sub, (ch, tex)
    assert "k" in sup, tex
    assert "1" not in sup, tex


def test_a_body_size_word_under_the_operator_is_still_prose():
    """A limit is set at SCRIPT size. Without that test this rule would take
    any word that happened to sit in the operator's column."""
    glyphs = _display(lower_size=BODY)       # `i=1` at body size, same place
    spans = D._spans(_line(glyphs))
    span = [s for s in spans
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    assert "i" not in "".join(g.text for g in span.glyphs), _kinds(spans)


def test_a_script_beside_the_operator_is_not_claimed_as_a_limit():
    """Centred on the operator's column, not merely on the same line. The
    operator spans x 40..52, so its window reaches 31..61; a script at 80 is
    the next term's and must stay there."""
    spans = D._spans(_line(_display(lower_x=80.0)))
    span = [s for s in spans
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    assert "i" not in "".join(g.text for g in span.glyphs), _kinds(spans)


def test_a_script_below_the_window_is_not_claimed_as_a_limit():
    """The window is 2.5 operator-sizes (22.5pt here). The real lower limit
    is 20pt below its operator, so a row 40pt below is another row."""
    spans = D._spans(_line(_display(lower_base=69.0)))
    span = [s for s in spans
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    assert "i" not in "".join(g.text for g in span.glyphs), _kinds(spans)


def test_an_integrals_condition_is_not_a_stacked_limit():
    r"""`\int` is `\nolimits` even in display -- 2 under against 21 beside over
    the 102 documents, which is why `_LARGE_OP_STEMS` leaves integrals out.
    This rule must inherit that measurement rather than restate it."""
    spans = D._spans(_line(_display(glyphname="integraldisplay", tex=INT)))
    span = [s for s in spans
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    assert "i" not in "".join(g.text for g in span.glyphs), _kinds(spans)


def test_the_variant_suffix_does_not_hide_the_operator():
    r"""`summationdisplay.1` and `summationdisplay` are the same glyph.

    txfonts names every `\sum` on 1805.01788 with the suffix, and the limit
    tables are keyed by the base name -- so a rule that passes the raw name
    through is simply off on every document that loads txfonts. Both spellings
    must reach the same reading.
    """
    plain = D._spans(_line(_display(glyphname="summationdisplay")))
    variant = D._spans(_line(_display(glyphname="summationdisplay.1")))
    assert _kinds(plain) == _kinds(variant)
    span = [s for s in variant
            if any(g.tex.kind == "bigop" for g in s.glyphs)][0]
    assert "i" in "".join(g.text for g in span.glyphs), _kinds(variant)
