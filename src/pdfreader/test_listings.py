r"""Tests for the listing grid -- 781.

The measurements quoted here are `lst-004` of the gold set (1804.10694v5,
`texsrc/archive.tex` line 18), read at 5pt `numberstyle` and 8pt `ttfamily`:

    cell 4.23pt    one space  8.47 (2 cells)
                   indent 2  16.83 (4 cells from the gutter glyph)
                   indent 4  25.31 (6 cells)
"""
import listings as L
import project_mmd as M
import texmap
from docmodel_six import GlyphNode, LineNode, PageNode
from texmap import project

CELL = 4.23


def g(ch, x, size=8.0, font="TEST+NimbusMonL-Regu", color=None, y=100.0):
    return GlyphNode(
        id="g%s%.0f" % (ch, x), page=1,
        rect=(x, y, x + 0.6 * size, y + size),
        text=ch, cid=ord(ch), glyphname=None, fontname=font,
        family="text", size=size, tex=project("text", None),
        matrix=(size, 0, 0, size, x, y), color=color)


def row(text, x0, y=100.0, size=8.0, color=None, font="TEST+NimbusMonL-Regu"):
    """A line of monospace glyphs laid out on the 4.23pt grid."""
    gs = [g(c, x0 + i * CELL, size, font, color, y)
          for i, c in enumerate(text) if c != " "]
    return LineNode(id="l%.0f" % y, page=1, rect=(x0, y, x0 + len(text) * CELL,
                                                  y + size),
                    type="text", glyphs=gs)


class TestTheCell:
    def test_cell_is_the_advance(self):
        ln = row("float b1", 56.69)
        assert abs(L.cell_width(ln.glyphs) - CELL) < 0.05

    def test_a_proportional_run_is_not_a_grid(self):
        """Advances that are not whole multiples of anything: abstain."""
        gs = []
        x = 50.0
        for i, c in enumerate("proportional text here"):
            if c == " ":
                x += 2.3
                continue
            gs.append(g(c, x))
            x += 3.1 + 0.9 * (i % 3)
        assert L.cell_width(gs) is None

    def test_too_few_advances_to_measure(self):
        assert L.cell_width(row("ab", 50.0).glyphs) is None


class TestTheSpacesTheGridShows:
    def test_one_space_is_one_empty_cell(self):
        assert L.grid_text(row("a = 1", 50.0).glyphs, CELL) == "a = 1"

    def test_a_run_of_spaces_is_counted(self):
        assert L.grid_text(row("a    b", 50.0).glyphs, CELL) == "a    b"

    def test_no_space_between_adjacent_glyphs(self):
        assert L.grid_text(row("float", 50.0).glyphs, CELL) == "float"


def _page(rows):
    p = PageNode(page=1, rect=(0, 0, 595, 842), lines=rows)
    p.listings = L.accumulate(p)
    return p


class TestTheIndentIsAMeasurement:
    def test_indent_counted_from_column_zero(self):
        """The very loss this module exists for: leading space is not a gap
        between glyphs, so `_run_text` could never see it."""
        p = _page([row("for (i in 0..N)", 56.69, y=300.0),
                   row("for (j in 0..M)", 56.69 + 2 * CELL, y=290.0),
                   row("b1[j] = a*f1[i,j]", 56.69 + 4 * CELL, y=280.0)])
        assert len(p.listings) == 1
        assert [x.indent for x in p.listings[0].lines] == [0, 2, 4]

    def test_the_block_text_carries_it(self):
        p = _page([row("for (i in 0..N)", 56.69, y=300.0),
                   row("b1[j] = 1", 56.69 + 2 * CELL, y=290.0)])
        assert p.listings[0].text() == "for (i in 0..N)\n  b1[j] = 1"


class TestTheGutterIsNotCode:
    def _numbered(self):
        rows = []
        for i, (text, ind) in enumerate([("for (i in 0..N)", 0),
                                         ("for (j in 0..M)", 2),
                                         ("b1[j] = 1", 4)]):
            y = 300.0 - 10 * i
            ln = row(text, 56.69 + ind * CELL, y=y)
            # the line number: SMALLER type, to the left of every code glyph
            ln.glyphs.insert(0, g(str(i + 1), 48.32, size=5.0, y=y))
            rows.append(ln)
        return rows

    def test_the_number_is_read_and_kept_apart(self):
        lst = _page(self._numbered()).listings[0]
        assert lst.numbers
        assert [x.number for x in lst.lines] == [1, 2, 3]
        assert lst.firstnumber == 1 and lst.stepnumber == 1

    def test_the_number_is_not_in_the_code(self):
        lst = _page(self._numbered()).listings[0]
        assert lst.lines[0].text == "for (i in 0..N)"

    def test_the_number_does_not_move_column_zero(self):
        """The gutter sits left of the code, so measuring the indent from it
        would make every line indented by the same wrong amount."""
        lst = _page(self._numbered()).listings[0]
        assert [x.indent for x in lst.lines] == [0, 2, 4]

    def test_a_listing_without_numbers_says_so(self):
        p = _page([row("for (i in 0..N)", 56.69, y=300.0),
                   row("b1[j] = 1", 56.69, y=290.0)])
        assert not p.listings[0].numbers


class TestColour:
    def test_a_coloured_run_is_located_in_the_text(self):
        ln = row("for (i in 0..N)", 56.69, y=300.0)
        for gl in ln.glyphs[:3]:
            gl.color = (1.0, 0.4, 0.0)
        p = _page([ln, row("b1[j] = 1", 56.69, y=290.0)])
        lst = p.listings[0]
        assert lst.colors == [(1.0, 0.4, 0.0)]
        r = lst.lines[0].colors[0]
        assert lst.lines[0].text[r.start:r.end] == "for"
        assert r.kind == "keyword"

    def test_black_is_not_a_colour(self):
        p = _page([row("for (i in 0..N)", 56.69, y=300.0),
                   row("b1[j] = 1", 56.69, y=290.0)])
        assert p.listings[0].colors == []


class TestTheBlock:
    def test_a_short_line_inside_a_block_does_not_end_it(self):
        """lst-001: two content lines with `%` between them produced no block
        at all, because `verbatim` wants three alphanumerics."""
        p = _page([row("for (i in 0..N)", 56.69, y=300.0),
                   row("%", 56.69, y=290.0),
                   row("b1[j] = 1", 56.69, y=280.0)])
        assert len(p.listings) == 1
        assert len(p.listings[0].lines) == 3

    def test_one_line_is_not_a_listing(self):
        p = _page([row("for (i in 0..N)", 56.69, y=300.0)])
        assert p.listings == []

    def test_prose_is_not_a_listing(self):
        p = _page([row("the quick brown fox", 56.69, y=300.0,
                       font="TEST+NimbusRomNo9L-Regu"),
                   row("jumped over the dog", 56.69, y=290.0,
                       font="TEST+NimbusRomNo9L-Regu")])
        assert p.listings == []


class TestTheLatexProjection:
    def _lst(self):
        ln = row("for (i in 0..N)", 56.69, y=300.0)
        for gl in ln.glyphs[:3]:
            gl.color = (1.0, 0.4, 0.0)
        return _page([ln, row("b1[j] = a*f1[i,j]", 56.69 + 2 * CELL,
                              y=290.0)]).listings[0]

    def test_it_is_a_listing_environment(self):
        tex = M._listing_tex(self._lst())
        assert r"\begin{lstlisting}" in tex and r"\end{lstlisting}" in tex

    def test_the_indent_reaches_the_file(self):
        tex = M._listing_tex(self._lst())
        assert "\n  b1[j] = a*f1[i,j]" in tex

    def test_keepspaces_or_latex_respaces_it(self):
        tex = M._listing_tex(self._lst())
        assert "keepspaces=true" in tex and "columns=fullflexible" in tex

    def test_the_style_is_a_header_property(self):
        """A listing is not an equation. The body is the PROGRAM, so the
        colouring goes in the options -- `morekeywords` with a
        `keywordstyle` -- and nothing is written into the code."""
        tex = M._listing_tex(self._lst())
        assert "morekeywords={[1]{for}}" in tex
        assert r"keywordstyle={[1]{\color{lstclr0}}}" in tex

    def test_nothing_is_written_into_the_body(self):
        tex = M._listing_tex(self._lst())
        body = tex.split(r"\begin{lstlisting}[", 1)[1]
        body = body.split("]\n", 1)[1].rsplit("\\end", 1)[0]
        assert body.startswith("for (i in 0..N)\n  b1[j] = a*f1[i,j]")
        for mark in ("!<", ">!", "moredelim", "textcolor"):
            assert mark not in body

    def test_the_code_is_what_a_compiler_would_get(self):
        assert self._lst().code == "for (i in 0..N)\n  b1[j] = a*f1[i,j]"


class TestTheFrame:
    """lst-027, `frame=single`, measured off the page:

        top    rule   56.69 729.33 555.31 729.33
        left   rule   52.91 714.39  52.91 725.34    one PER LINE
        left   rule   52.91 703.43  52.91 714.39
        left   rule   52.91 692.47  52.91 703.43
        right  rules  559.09, the same three bands
        bottom rule   56.69 688.48 555.31 688.48

        frame        52.91 688.48 559.09 729.33
        glyph extent 48.32 688.28 566.86 739.09
    """

    def _rules(self):
        from docmodel_six import RuleNode
        out = [RuleNode(id="t", page=1, rect=(56.69, 729.33, 555.31, 729.53)),
               RuleNode(id="b", page=1, rect=(56.69, 688.48, 555.31, 688.68))]
        for i, (lo, hi) in enumerate([(714.39, 725.34), (703.43, 714.39),
                                      (692.47, 703.43)]):
            out.append(RuleNode(id="l%d" % i, page=1, rect=(52.91, lo, 53.11, hi)))
            out.append(RuleNode(id="r%d" % i, page=1, rect=(559.09, lo, 559.29, hi)))
        return out

    def test_the_box_is_found(self):
        got = L.frames(self._rules(), span_pt=8.0)
        assert len(got) == 1
        x0, y0, x1, y1 = got[0]
        assert abs(x0 - 52.91) < 0.1 and abs(x1 - 559.09) < 0.1
        assert abs(y0 - 688.48) < 0.1 and abs(y1 - 729.53) < 0.1

    def test_a_side_is_one_rule_per_line_stacked(self):
        """No single segment is as tall as the box; stacked, they are."""
        cols = L._columns([r for r in self._rules() if L._vertical(r)])
        assert len(cols) == 2
        for _x, lo, hi in cols:
            assert abs(hi - lo - (725.34 - 692.47)) < 0.1

    def test_frame_tb_has_no_sides(self):
        """`frame=tb` draws the pair and nothing else; the width is theirs."""
        rules = [r for r in self._rules() if L._horizontal(r)]
        got = L.frames(rules, span_pt=8.0)
        assert len(got) == 1
        assert abs(got[0][0] - 56.69) < 0.1 and abs(got[0][2] - 555.31) < 0.1

    def test_two_rules_too_close_are_not_a_box(self):
        from docmodel_six import RuleNode
        rules = [RuleNode(id="a", page=1, rect=(56.0, 700.0, 555.0, 700.2)),
                 RuleNode(id="b", page=1, rect=(56.0, 695.0, 555.0, 695.2))]
        assert L.frames(rules, span_pt=8.0) == []

    def test_rules_of_different_widths_are_not_a_box(self):
        from docmodel_six import RuleNode
        rules = [RuleNode(id="a", page=1, rect=(56.0, 729.0, 555.0, 729.2)),
                 RuleNode(id="b", page=1, rect=(90.0, 688.0, 400.0, 688.2))]
        assert L.frames(rules, span_pt=8.0) == []


class TestAGutterTheSizeTestCannotSee:
    r"""`numberstyle` is `\tiny` by convention, so `_gutter` knows the
    line-number column by its SIZE. An author who sets `numbers=left` and
    leaves `numberstyle` alone gets numbers at the code's own size.
    2310.02304v3 does exactly that."""

    def _block(self, numbers, indents):
        """A listing whose gutter is the same size as its code."""
        rows = []
        for i, (num, ind) in enumerate(zip(numbers, indents)):
            y = 300.0 - 10 * i
            ln = row("for (i in 0..N)", 56.69 + ind * CELL, y=y)
            # RIGHT-ALIGNED, as `numbers=left` sets it: the digits end at
            # one x and begin at different ones.
            text = str(num)
            x = 48.32 - (len(text) - 1) * CELL
            for j, ch in enumerate(text):
                ln.glyphs.insert(j, g(ch, x + j * CELL, size=8.0, y=y))
            rows.append(ln)
        return _page(rows).listings[0]

    def test_a_same_size_gutter_is_still_a_gutter(self):
        lst = self._block([1, 2, 3, 4], [0, 0, 0, 0])
        assert lst.numbers
        assert [x.number for x in lst.lines] == [1, 2, 3, 4]
        assert lst.lines[0].text == "for (i in 0..N)"

    def test_two_digit_numbers_do_not_refuse_it(self):
        """The first fix required the gutter's LEFT edge to be constant.
        Right-aligned numbers move it -- ` 9`, `10` -- so every listing
        past line nine was refused, and the measurement went DOWN."""
        lst = self._block([8, 9, 10, 11], [0, 0, 0, 0])
        assert lst.numbers
        assert [x.number for x in lst.lines] == [8, 9, 10, 11]

    def test_indentation_does_not_refuse_it(self):
        """The second fix required the CODE's left edge to be constant.
        That moves with the indentation, which is the thing being
        measured."""
        lst = self._block([6, 7, 8, 9], [0, 4, 4, 8])
        assert lst.numbers
        assert [x.indent for x in lst.lines] == [0, 4, 4, 8]

    def test_a_leading_number_that_is_code_is_not_a_gutter(self):
        """`1 + 1` is not a line number: nothing separates it from the
        code, and the numbers do not increase."""
        rows = [row("1 + count(alpha) == total", 56.69, y=300.0),
                row("1 + count(beta) == total", 56.69, y=290.0),
                row("1 + count(gamma) == total", 56.69, y=280.0)]
        lst = _page(rows).listings[0]
        assert not lst.numbers
        assert lst.lines[0].text.startswith("1 +")


class TestTheHeader:
    """The header/body split: everything ABOUT the listing on the outside,
    and one plain-text program on the inside."""

    def _lst(self):
        ln = row("for (i in 0..N)", 56.69, y=300.0)
        for gl in ln.glyphs[:3]:
            gl.color = (1.0, 0.4, 0.0)
        return _page([ln, row("b1[j] = a*f1[i,j]", 56.69 + 2 * CELL,
                              y=290.0)]).listings[0]

    def test_the_keywords_carry_their_layout(self):
        assert self._lst().keywords == [("for", (1.0, 0.4, 0.0), False, False)]

    def test_a_comment_is_not_a_keyword(self):
        ln = row("// set the gain", 56.69, y=300.0)
        for gl in ln.glyphs:
            gl.color = (0.0, 0.6, 0.0)
        lst = _page([ln, row("b1[j] = 1", 56.69, y=290.0)]).listings[0]
        assert lst.keywords == []
        assert lst.style_of("comment") == ((0.0, 0.6, 0.0), False, False)

    def test_an_indented_line_is_sliced_at_the_right_place(self):
        """The runs count from the first CODE glyph, so classifying them
        against the indented row shifted every slice by the indent and
        filed `[`, `{` and `}` as keywords. That reached
        `morekeywords={[1]{[,{,}}}` and cost lst-095 its whole compile."""
        ln = row("    for (j in 0..M)", 56.69 + 4 * CELL, y=300.0)
        for gl in ln.glyphs[:3]:
            gl.color = (1.0, 0.4, 0.0)
        lst = _page([ln, row("b1[j] = 1", 56.69, y=290.0)]).listings[0]
        assert [w for w, *_ in lst.keywords] == ["for"]

    def test_the_projection_refuses_a_word_with_a_bracket(self):
        """Belt as well as braces: such a word does not make a bad listing,
        it makes an unreadable file."""
        lst = self._lst()
        lst.lines[0].text = "[ (i in 0..N)"
        lst.lines[0].colors[0].start, lst.lines[0].colors[0].end = 0, 1
        tex = M._listing_tex(lst)
        env = [l for l in tex.split("\n")
               if l.startswith(r"\begin{lstlisting}")][0]
        assert "morekeywords" not in env

    def test_a_run_of_keywords_is_not_a_literal(self):
        """`public static void` is three keywords in one style, and stays
        three: `listings` declares all three for Java, which is the test.
        (`main` is deliberately not here -- it is not a keyword in any
        list listings ships, so listings would never have coloured it.)"""
        ln = row("public static void", 56.69, y=300.0)
        for gl in ln.glyphs:
            gl.color = (1.0, 0.4, 0.0)
        lst = _page([ln, row("b1[j] = 1", 56.69, y=290.0)]).listings[0]
        assert [w for w, *_ in lst.keywords] == ["public", "static", "void"]

    def test_english_in_one_style_is_not_keywords(self):
        """lst-121 filed `You will be evaluated based on this score` as
        eight keywords, out of one prompt string. No single language
        declares those words, so they are not keywords."""
        ln = row("You will be evaluated based on this", 56.69, y=300.0)
        for gl in ln.glyphs:
            gl.color = (0.58, 0.0, 0.82)
        lst = _page([ln, row("b1[j] = 1", 56.69, y=290.0)]).listings[0]
        assert lst.keywords == []

    def test_the_rectangle_is_the_glyphs_when_nothing_is_drawn(self):
        lst = self._lst()
        assert lst.rect is not None and not lst.framed


class TestMarksThatTile:
    """A listing is set LINE BY LINE, so its marks stack; a figure's do not.

    Measured on a four-line `frame=single` listing with a background:

        LTRect  56.69 715.48 555.31 725.35    background, line 1
        LTRect  56.69 705.62 555.31 715.48    line 2, abutting exactly
        LTRect  56.69 695.76 555.31 705.62    line 3
    """

    def test_a_stack_of_equal_bands_is_tiling(self):
        import docmodel_six as D
        rects = [(56.69, 715.48, 555.31, 725.35),
                 (56.69, 705.62, 555.31, 715.48),
                 (56.69, 695.76, 555.31, 705.62)]
        assert D._tiles(rects) == {0, 1, 2}

    def test_two_bands_are_not_a_stack(self):
        import docmodel_six as D
        rects = [(56.69, 715.48, 555.31, 725.35),
                 (56.69, 705.62, 555.31, 715.48)]
        assert D._tiles(rects) == set()

    def test_a_gap_breaks_the_stack(self):
        import docmodel_six as D
        rects = [(56.0, 700.0, 555.0, 710.0),
                 (56.0, 690.0, 555.0, 700.0),
                 (56.0, 600.0, 555.0, 610.0)]
        assert D._tiles(rects) == set()

    def test_scattered_marks_do_not_tile(self):
        import docmodel_six as D
        rects = [(10.0, 700.0, 40.0, 710.0), (80.0, 660.0, 130.0, 690.0),
                 (200.0, 610.0, 260.0, 640.0), (35.0, 500.0, 300.0, 505.0),
                 (150.0, 520.0, 152.0, 600.0)]
        assert D._tiles(rects) == set()

    def test_the_two_sides_of_a_frame_are_two_stacks(self):
        import docmodel_six as D
        rects = []
        for lo, hi in ((715.48, 725.35), (705.62, 715.48), (695.76, 705.62)):
            rects.append((51.51, lo, 51.71, hi))
            rects.append((555.31, lo, 555.51, hi))
        assert D._tiles(rects) == set(range(6))


class TestTheFontNameThatOnlyTheMeasurementKnew:
    def test_sftt_is_typewriter(self):
        """cm-super's T1 typewriter. lst-278: 21,928 advances, 51 letters,
        advance/size 0.531 on 100.0% of them."""
        assert texmap.is_monospace("VWKTCM+SFTT0900")

    def test_sfrm_is_not(self):
        assert not texmap.is_monospace("XADWKO+SFRM0500")
