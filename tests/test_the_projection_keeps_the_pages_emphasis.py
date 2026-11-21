r"""Bold, italic and typewriter reach the LaTeX, because the page set them.

T-0156. The projected `.tex` carried NO emphasis at all: grepping
`\textbf|\textit|\emph|\bfseries|\itshape` over any `.glyphs.tex` returned
nothing. Every bold heading, every italicised term and every line of
typewriter code was rendered upright and plain.

MEASURED on the board-18 judge outputs, which flag a glyph whose style in the
ink differs from its style in the re-render. `style` is the dominant part of
`flagged` on every page of the set, and on several the glyph term is 0 while
style is in the hundreds:

    page                      style   ours   judge   our side's fonts
    lib:d68e p334              1045   1181       0   CMTT8:1181   typewriter
    1511.08771 p2709           1509   1360     603   CMBX10:1360  bold
    1805.01788 p3               584    589       6   TI:393 TB:138
    2311.09533v3 p10            353    355       0   ReguItal:330
    2103.01507 p118             187    191       3   CMTI10:170
    lib:b21e554b9232 p201       159    158      18   CMTI10:139
    lib:88d76967110e p170        70     70       0   Optima-Bold:70

    TOTAL  4,804 glyphs ours (ink emphasised, our render plain)
           1,145 glyphs the judge's (ink plain, our render emphasised —
                  MathTime subset fonts, which are italic by construction;
                  that half went to inkdrill-10)

IT MOVES NO RESIDUAL, and this test is not evidence that it does. The judge
computes the residual from glyph findings, unpaired glyphs and rules
(`board_run.py:841`); `style` has a column of its own, `style_rate`. The
reason to do it is T-0156's own requirement — a projection that drops bold,
italic and typewriter is not a faithful rendering of the page — and the number
it moves is `style_rate`, not the residual.

THE SPAN IS THE UNIT, and the span's glyphs must AGREE. This is the shape the
colour already uses two lines above it in the emitter (`len(cols) == 1`): a
property every glyph of the span shares is wrapped once around the span's
text, and a span whose glyphs disagree is left alone rather than guessed at.
`texmap.is_bold` / `is_italic` / `is_monospace` are the authority, unchanged —
they already know `NimbusRomNo9L-Medi` is Times bold (814) and `CMTT8` is
typewriter.

NOT IN THE MARKDOWN in this commit. Markdown can say bold and italic, unlike
colour, so it should eventually; the `.tex` is what T-0156 asks for and what
the judge reads, and one artefact at a time is reviewable.
"""
from pdfreader import docmodel_six as D
from pdfreader import project_mmd as M
from pdfreader.texmap import project


def _page(font="ABC+Helv", text="abc"):
    """One line of one span, every glyph in `font`."""
    page = D.PageNode(page=1, rect=(0, 0, 612, 792))
    gl, x = [], 100.0
    for c in text:
        gl.append(D.GlyphNode(
            id=f"g{x}", page=1, rect=(x, 200.0, x + 5.0, 210.0),
            text=c, cid=0, glyphname=None, fontname=font,
            family="text", size=10.0, tex=project("text", None),
            matrix=(10.0, 0, 0, 10.0, x, 200.0)))
        x += 5.0
    page.lines = [D.LineNode(id="l", page=1, rect=(100, 200, x, 210),
                             type="text", glyphs=gl)]
    return page


def _mixed(fonts):
    """One span whose glyphs do NOT agree about their face."""
    page = D.PageNode(page=1, rect=(0, 0, 612, 792))
    gl, x = [], 100.0
    for c, f in zip("abc", fonts):
        gl.append(D.GlyphNode(
            id=f"g{x}", page=1, rect=(x, 200.0, x + 5.0, 210.0),
            text=c, cid=0, glyphname=None, fontname=f,
            family="text", size=10.0, tex=project("text", None),
            matrix=(10.0, 0, 0, 10.0, x, 200.0)))
        x += 5.0
    page.lines = [D.LineNode(id="l", page=1, rect=(100, 200, x, 210),
                             type="text", glyphs=gl)]
    return page


def test_bold_reaches_the_latex():
    """`CMBX10` is 1,360 glyphs on one board page alone."""
    tex = M.to_latex([_page("ABC+CMBX10")], preamble=False)
    assert r"\textbf{" in tex, tex


def test_times_bold_under_its_urw_name_reaches_the_latex():
    """814 — pdfLaTeX's default Times bold embeds as `NimbusRomNo9L-Medi`,
    the commonest bold face in this corpus. `is_bold` already knows it; the
    projection has to ask."""
    tex = M.to_latex([_page("ABC+NimbusRomNo9L-Medi")], preamble=False)
    assert r"\textbf{" in tex, tex


def test_italic_reaches_the_latex():
    tex = M.to_latex([_page("ABC+CMTI10")], preamble=False)
    assert r"\textit{" in tex, tex
    tex = M.to_latex([_page("ABC+NimbusRomNo9L-ReguItal")], preamble=False)
    assert r"\textit{" in tex, tex


def test_typewriter_reaches_the_latex():
    """1,181 glyphs on lib:d68e p334 — a page of code set in CMTT8."""
    tex = M.to_latex([_page("ABC+CMTT8")], preamble=False)
    assert r"\texttt{" in tex, tex


def test_plain_text_is_not_wrapped():
    """The common case must cost nothing. `CMR10` is upright roman."""
    tex = M.to_latex([_page("ABC+CMR10")], preamble=False)
    for cmd in (r"\textbf{", r"\textit{", r"\texttt{"):
        assert cmd not in tex, (cmd, tex)


def test_a_span_whose_glyphs_disagree_is_left_alone():
    """The colour rule, applied to the face: a span is wrapped only when
    every glyph of it says the same thing. Guessing would set a word bold
    because one letter of it came from a different subset."""
    tex = M.to_latex([_mixed(["A+CMBX10", "A+CMR10", "A+CMR10"])],
                     preamble=False)
    assert r"\textbf{" not in tex, tex


def test_bold_italic_nests_both():
    """A bold italic face is both, and the wrappers compose."""
    tex = M.to_latex([_page("ABC+CMBXTI10")], preamble=False)
    assert r"\textbf{" in tex and r"\textit{" in tex, tex


def test_the_markdown_is_unchanged_by_this_commit():
    """Markdown CAN say bold and italic, unlike colour, and should
    eventually. It is not part of this change, and this test says so rather
    than leaving it unstated."""
    md = M.to_markdown([_page("ABC+CMBX10")])
    assert "**" not in md, md


#: ------------------------------------------------------------------
#: SMALL CAPS, AND THE TWO FAMILIES THIS DOES *NOT* ADD.
#:
#: With the emitter carrying emphasis, 4,067 of the 4,804 ours-side glyphs on
#: the board set are recognised. The other 737 are three naming conventions
#: none of `is_bold`/`is_italic`/`is_monospace` covers:
#:
#:     LinLibertineTI 393, LinLibertineTB 138, LinLibertineI 58
#:     SFBX1440/1200/1000/0900 103, SFTI1000 8
#:     Times-RomanSmallCaps 45
#:
#: Widening `is_bold`/`is_italic` for the first two was tried and REVERTED:
#: the reader's own classification reads those two functions, so the change
#: is not confined to the projection. Measured with it in — 1805.01788 p3
#: gained 9 correct section headers and lib:5a5c76391c9c p4 gained 3, and
#: 1805 p3 also typed four lines of body prose as `authors` and lost 936
#: characters. That is a gain and a regression in one change; it needs its
#: own commit and its own measurement.
#:
#: Small caps IS added, because `is_small_caps` is new: nothing in the reader
#: reads it, so it cannot move a line's type, and `\textsc` is the only
#: wrapper here that is neither bold nor italic.


def test_small_caps_get_textsc():
    """45 glyphs on the board set. The real name is
    `YNAJWO+LnrnjhTimes-RomanSmallCaps`; the judge's font column truncates
    it to `...SmallCa`, which is why it first looked undetected."""
    tex = M.to_latex([_page("YNAJWO+LnrnjhTimes-RomanSmallCaps")],
                     preamble=False)
    assert r"\textsc{" in tex, tex
    assert r"\textbf{" not in tex, tex


def test_a_plain_roman_face_gets_no_small_caps():
    tex = M.to_latex([_page("ABC+Times-Roman")], preamble=False)
    assert r"\textsc{" not in tex, tex


def test_the_emphasis_commands_need_no_package():
    """All four are LaTeX kernel commands. `\textsc` was missing from the
    table, so the one board page that uses it gained a spurious
    "commands with no known package" warning in its preamble."""
    from pdfreader import texpackages as T
    for cmd in (r"\textbf{x}", r"\textit{x}", r"\texttt{x}", r"\textsc{x}"):
        assert not T.packages_for(cmd), (cmd, T.packages_for(cmd))


def test_the_two_reverted_families_are_still_not_detected():
    """Pins the revert, so the regression cannot come back by accident:
    these faces stay plain until the heading-classification effect has been
    measured in a commit of its own."""
    for font in ("ABC+LinLibertineTB", "ABC+LinLibertineTI", "ABC+SFBX1440",
                 "ABC+SFTI1000"):
        tex = M.to_latex([_page(font)], preamble=False)
        for cmd in (r"\textbf{", r"\textit{"):
            assert cmd not in tex, (font, cmd)
