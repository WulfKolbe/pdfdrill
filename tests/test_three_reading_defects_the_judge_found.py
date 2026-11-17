r"""Three defects the ink judge found, each costing whole lines of a page.

Board-wide, 16 of our lines did not compile in the judge's snippet against
MathPix's 1, and a line that does not compile pairs no glyphs at all.

1. A COMMAND MUST END. `_merge_operator_names` collapses the upright letters of
   `\lg` into one glyph whose text IS the command; the letters after it are a
   separate run, so concatenation spelled `\lgcRn`. Measured on
   lib:c9daf79960c3 p68: `functor G : CA\lgcRn Ñ ...`, one of 6 lines on that
   page the judge could not set, costing 307 of its 1,703 glyphs.

2. PROSE IS NOT MATHS. The absorption rules pull a short letter run into a
   neighbouring maths span, right for a variable and wrong for a word. On
   lib:c57ac038ae5f p293 the line opens "are orthogonal" and came out
   `$\mathrm{are} \mathrm{o}$ rthogonal` -- a word split across two spans, with
   unbalanced maths behind it and 56 unpaired glyphs on that line.

3. A BAR IS A DELIMITER UNLESS THE PAGE SPACED IT. `\mid` is a relation and
   sets a thick space each side; the page prints `|x|=x` flush. On
   lib:4859edad9294 p1287 everything after the first bar shifted and 28 glyphs
   unpaired. Measured over 122 bar glyphs on the board: flush up to the 75th
   percentile (0.003 em), 0.278 and 0.518 em at the 90th and 100th, so the cut
   is 0.15 em.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _g(text, x0, x1, *, size=10.0, baseline=100.0, family="text-cm",
       name=None, latex=None, kind="atom"):
    tex = texmap.TexToken(latex, kind, None, "corpus") if latex else texmap.UNKNOWN
    return docmodel.GlyphNode(
        id="g%d" % int(x0 * 10), page=1, rect=(x0, baseline, x1, baseline + size),
        text=text, cid=0, glyphname=name, fontname="CMR10", family=family,
        size=size, tex=tex)


# ---- 1. a command must end -------------------------------------------

def test_a_command_glyph_is_separated_from_a_following_letter():
    # INSIDE MATHS the command is not wrapped, so a space is what ends it.
    out = docmodel._run_text([_g(r"\lg", 0, 12), _g("c", 12, 17), _g("R", 17, 23)],
                             maths_mode=True)
    assert r"\lgc" not in out
    assert out.startswith(r"\lg ")


def test_a_command_in_a_text_run_gets_its_maths_mode():
    # In a TEXT run the command needs `$...$` or pdflatex answers "Missing $
    # inserted" -- and the closing `$` ends the command, so no space is needed.
    out = docmodel._run_text([_g(r"\lg", 0, 12), _g("c", 12, 17)])
    assert out.startswith("$" + chr(92) + "lg$")
    assert r"\lgc" not in out


def test_a_command_before_a_non_letter_still_needs_no_space():
    out = docmodel._run_text([_g(r"\lg", 0, 12), _g("(", 12, 15)], maths_mode=True)
    assert out == r"\lg("


def test_two_ordinary_letters_are_not_separated():
    assert docmodel._run_text([_g("a", 0, 5), _g("b", 5, 10)]) == "ab"


# ---- 2. prose is not maths -------------------------------------------

def _span(kind, glyphs, line_size=10.0):
    xs = [g.rect[0] for g in glyphs] + [g.rect[2] for g in glyphs]
    return docmodel.Span(id="s", kind=kind, rect=(min(xs), 0, max(xs), 10),
                         glyphs=glyphs, line_size=line_size)


def test_a_span_of_upright_letters_is_retyped_as_text():
    sp = _span("math", [_g("a", 0, 5), _g("r", 5, 10), _g("e", 10, 15)])
    out = docmodel._prose_is_not_maths([sp])
    assert out[0].kind == "text"


def test_the_split_word_is_put_back_together():
    a = _span("math", [_g("a", 0, 5), _g("r", 5, 10), _g("e", 10, 15)])
    b = _span("text", [_g("o", 15.5, 20), _g("k", 20, 25)])
    out = docmodel._prose_is_not_maths([a, b])
    assert len(out) == 1 and [g.text for g in out[0].glyphs] == list("areok")


def test_a_span_with_scripts_stays_maths():
    # `\mathrm{Mod}_{\mathrm{Z}}` is upright throughout; its script is smaller.
    glyphs = [_g("M", 0, 7), _g("o", 7, 13), _g("d", 13, 19),
              _g("Z", 19, 23, size=7.0)]
    out = docmodel._prose_is_not_maths([_span("math", glyphs)])
    assert out[0].kind == "math"


def test_a_single_letter_span_stays_maths():
    out = docmodel._prose_is_not_maths([_span("math", [_g("x", 0, 5)])])
    assert out[0].kind == "math"


def test_a_span_holding_a_symbol_stays_maths():
    glyphs = [_g("a", 0, 5), _g("+", 5, 10, family="math-symbol", latex="+")]
    out = docmodel._prose_is_not_maths([_span("math", glyphs)])
    assert out[0].kind == "math"


# ---- 3. a bar is a delimiter unless spaced ---------------------------

def _bar(x0, size=10.0, baseline=100.0):
    return _g("|", x0, x0 + 1.5, size=size, baseline=baseline,
              family="math-symbol", name="bar", latex=r"\mid", kind="atom")


def test_a_flush_bar_becomes_a_delimiter():
    gl = [_g("x", 0, 5, family="math-italic"), _bar(5.0),
          _g("x", 6.5, 11.5, family="math-italic")]
    docmodel._bar_by_its_spacing(gl)
    assert gl[1].tex.latex == "|"


def test_a_spaced_bar_stays_a_relation():
    gl = [_g("x", 0, 5, family="math-italic"), _bar(9.0),
          _g("y", 14.0, 19.0, family="math-italic")]
    docmodel._bar_by_its_spacing(gl)
    assert gl[1].tex.latex == r"\mid"


def test_a_bar_with_no_neighbour_is_left_alone():
    gl = [_bar(5.0)]
    docmodel._bar_by_its_spacing(gl)
    assert gl[0].tex.latex == r"\mid"


# ---- 4. a deferred maths span keeps its delimiter pairs together -------

def test_an_untypeable_maths_span_is_one_maths_group():
    r"""`\bigl[` must meet its `\bigr]` inside the SAME group.

    A maths span `span_latex` cannot express falls back to its characters. In a
    text run those land outside maths mode ("Missing $ inserted", 13 of the
    board's 14 non-compiling lines); wrapped one command at a time,
    `3\bigl[-11/2\bigr]` became `3$\bigl[$-11/2$\bigr]$` and the pair was
    broken. One group round the whole span is what keeps them together.
    """
    glyphs = [_g("3", 0, 5, family="math-symbol"),
              _g(r"\bigl[", 5, 11, family="math-symbol", name="bracketleftbig",
                 latex=r"\bigl[", kind="delimiter"),
              _g("1", 11, 16, family="math-symbol"),
              _g(r"\bigr]", 16, 22, family="math-symbol", name="bracketrightbig",
                 latex=r"\bigr]", kind="delimiter")]
    sp = _span("math", glyphs)
    out = docmodel.span_reading_text(sp)
    assert out.startswith("$") and out.endswith("$"), out
    assert out.count("$") == 2, out
    assert r"\bigl[" in out and r"\bigr]" in out
