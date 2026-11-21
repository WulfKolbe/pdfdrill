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


def test_linux_libertine_italic_and_bold_are_recognised():
    """T-0156, second commit. 589 glyphs on the board set, 560 of them on
    1805.01788 p3. The `libertine` package's suffix carries the face."""
    assert r"\textit{" in M.to_latex([_page("ABC+LinLibertineTI")],
                                     preamble=False)
    assert r"\textbf{" in M.to_latex([_page("ABC+LinLibertineTB")],
                                     preamble=False)
    assert r"\textit{" in M.to_latex([_page("ABC+LinLibertineI")],
                                     preamble=False)


def test_the_libertine_upright_text_face_is_not_emphasised():
    """`LinLibertineT` is the upright text face. A rule on the family name
    alone would set the whole document bold."""
    tex = M.to_latex([_page("ABC+LinLibertineT")], preamble=False)
    for cmd in (r"\textbf{", r"\textit{"):
        assert cmd not in tex, (cmd, tex)


def test_the_cm_sans_members_are_recognised():
    """`sfbx`/`sfti` are the sans members of the family whose `cmbx`/`cmti`
    the regexes already knew. `SFRM` is the upright sans and stays plain."""
    assert r"\textbf{" in M.to_latex([_page("ABC+SFBX1440")], preamble=False)
    assert r"\textit{" in M.to_latex([_page("ABC+SFTI1000")], preamble=False)
    tex = M.to_latex([_page("ABC+SFRM1000")], preamble=False)
    assert r"\textbf{" not in tex and r"\textit{" not in tex, tex


def test_a_subset_prefix_without_a_plus_is_still_read():
    """Some producers write the subset tag with no `+`; the board's judge
    output carries `WrcvyxSFBX0900`, which `split("+")[-1]` cannot help
    with. Both forms are offered and a match on either counts, because
    stripping six letters unconditionally would turn
    `NimbusRomNo9L-Medi` into `RomNo9L-Medi` and lose the one entry written
    for it (814)."""
    assert r"\textbf{" in M.to_latex([_page("WrcvyxSFBX0900")],
                                     preamble=False)
    assert r"\textbf{" in M.to_latex([_page("ABC+NimbusRomNo9L-Medi")],
                                     preamble=False)


#: ------------------------------------------------------------------
#: AND THE TITLE RULE, because widening `is_bold` reached it.
#:
#: `_front_matter` bounds the author block by the first heading AFTER the
#: title, so a heading taken for a title makes every line between it and the
#: next heading an `authors` line. Recognising Libertine bold gave
#: 1805.01788 p3 a heading it had not had, and 4 lines of body prose became
#: `authors`.
#:
#: MEASURED on the 24 board-14 extracts: 11 are given a title and ALL ELEVEN
#: ARE WRONG — every one is a mid-document extract with no title on it, and
#: the defect is pre-existing, not the widening's. 0864 p4 was already
#: exporting 20 `authors` lines and lib:88d76967110e p170 eighty-four.
#: Seven of the 11 open with a section number and are refused here; the other
#: four ('Index', 'Chapter 37', 'DIETARY NITRATE AND CARDIOVASCULAR …',
#: 'pm :4 34. 44,') need a different rule and are left alone.


def _sized_page(lines):
    """A page of (text, size) lines, in one column, top to bottom."""
    page = D.PageNode(page=1, rect=(0, 0, 612, 792))
    out, y = [], 700.0
    for text, size in lines:
        gl, x = [], 100.0
        for c in text:
            gl.append(D.GlyphNode(
                id=f"g{y}{x}", page=1, rect=(x, y, x + size * 0.5, y + size),
                text=c, cid=0, glyphname=None, fontname="ABC+CMR10",
                family="text", size=size, tex=project("text", None),
                matrix=(size, 0, 0, size, x, y)))
            x += size * 0.5
        out.append(D.LineNode(id=f"l{y}", page=1,
                              rect=(100, y, x, y + size), type="text",
                              glyphs=gl))
        y -= size * 2
    page.lines = out
    return page


def _body(n):
    return [("some running prose on this line here", 10.0) for _ in range(n)]


def test_a_largest_line_opening_with_a_section_number_is_no_title():
    """'2 EQUITY-OF-ATTENTION FAIRNESS' on 1805.01788 p3, and six more."""
    from pdfreader.project_mmd import _title_lines
    page = _sized_page([("2 EQUITY OF ATTENTION FAIRNESS", 14.0)] + _body(6))
    assert _title_lines([page]) == set()


def test_a_dotted_section_number_too():
    """'5.1.2 GCC' and '14.4.1 NUT Solution with Dual Mass'."""
    from pdfreader.project_mmd import _title_lines
    page = _sized_page([("5.1.2 GCC and more words", 14.0)] + _body(6))
    assert _title_lines([page]) == set()


def test_a_real_title_is_still_found():
    """The rule must not cost a document its title."""
    from pdfreader.project_mmd import _title_lines
    page = _sized_page([("Equity of Attention in Rankings", 14.0)] + _body(6))
    assert _title_lines([page]) == {(1, 0)}


def test_a_title_that_merely_starts_with_a_digit_is_still_a_title():
    """`3D Convolutional Networks` has no space after the digit, so it is
    not a section counter. This is the false refusal the pattern is scoped
    to avoid."""
    from pdfreader.project_mmd import _title_lines
    page = _sized_page([("3D Convolutional Networks for Video", 14.0)]
                       + _body(6))
    assert _title_lines([page]) == {(1, 0)}


#: ------------------------------------------------------------------
#: AND AN AUTHOR BLOCK IS SHORT.
#:
#: `_front_matter` bounds the block by the first heading AFTER the title, and
#: where that heading is far down the page the block swallows everything
#: between. lib:88d76967110e p170 exported EIGHTY-FOUR lines as `authors`,
#: beginning "In 2006 Larsen et al. tested the effects of …".
#:
#: FIVE DISCRIMINATORS DIED BEFORE THE ONE THAT SHIPPED, measured, so they
#: are not re-invented:
#:
#:   size contrast        real titles 1.91 and 1.43 x body; the spurious
#:                        ones 1.76, 2.24, 2.07, 1.20 — `Index` and
#:                        `Chapter 37` are MORE contrasty than either title
#:   any number in a      a real title page carries them too: 1805 page 1
#:   running line         prints "SIGIR '18, July 8-12, 2018"
#:   a BARE folio         0864 page 1 prints `6208`, its folio in the
#:                        proceedings, so this refuses a real title
#:   `_is_not_a_sentence` needs no word of three letters; author names are
#:                        long words
#:   THE BODY MARGIN      separates the measured cases perfectly — 0 of 4 and
#:                        0 of 5 real author lines start at the margin
#:                        against 80 of 84 of p170's — and still breaks,
#:                        because a FLUSH-LEFT front matter sets its authors
#:                        AT the margin. `test_line_types.py::TestFrontMatter`
#:                        is that document and the rule deleted its author
#:                        block. Two positives could not see it; the suite
#:                        could.
#:
#: What ships is a length cap, which is a threshold and is written as one:
#: real blocks of 5, 4 and 2 lines against runaways of 10 and 84. A real
#: block longer than the cap loses its `authors` type and stays `text`,
#: which is what it was before the type existed.


def test_an_author_block_of_eighty_four_lines_is_not_one():
    """lib:88d76967110e p170's shape: a title, body prose, then a heading
    far below. The block is refused whole, not cut at an arbitrary line."""
    from pdfreader.project_mmd import (_front_matter, _title_lines,
                                       _running_lines, profile)
    page = _sized_page([("DIETARY NITRATE AND HEALTH", 14.0)]
                       + [("In 2006 Larsen et al tested the effects", 10.0)] * 12
                       + [("2 Methods and materials here", 14.0)]
                       + _body(4))
    pages = [page]
    authors, _ = _front_matter(pages, profile(pages), _title_lines(pages),
                               _running_lines(pages))
    assert authors == set(), len(authors)


def test_a_short_author_block_survives_even_flush_left():
    """The shape the margin rule would have deleted: authors AT the margin.
    `test_line_types.py::TestFrontMatter` is the same document and is what
    caught that rule."""
    from pdfreader.project_mmd import (_front_matter, _title_lines,
                                       _running_lines, profile)
    page = _sized_page([("A Title Set Large", 14.0),
                        ("Ada Lovelace and Alan Turing", 10.0),
                        ("Department of Computing Somewhere", 10.0),
                        ("1 Introduction and related work", 14.0)]
                       + _body(6))
    pages = [page]
    authors, _ = _front_matter(pages, profile(pages), _title_lines(pages),
                               _running_lines(pages))
    assert authors == {(1, 1), (1, 2)}, authors
