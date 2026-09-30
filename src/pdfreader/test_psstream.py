"""Tests for reading the content stream's ACTIONS.

Every other reader here takes `LTChar`: a glyph with a final position, after
the CTM, the text matrix and the font size have been composed into one
rectangle. That is the RESULT, and two different actions land in the same
place -- a superscript of this line and a subscript of the line above.

Measured on a real page (the-semantics-of-metaprogramming-in-prolog, p6),
dvips marks a script by setting the text matrix to a smaller scale and
restoring it afterwards:

    /F15 TD [-32.42,-1.89]    'T'      the base
    /F4  Tm a=6.97 f=404.27   'P'      scale drops: the script opens
    /F18 TD [0.89,0]          ',A'     still inside
    /F5  Tm a=9.96 f=405.76   ''       scale restored: the script closes
"""
import psstream


class TestTokenizer:
    def test_operands_then_operator(self):
        got = list(psstream.tokenize(b"1 0 0 1 72 720 cm"))
        assert got == [([1.0, 0.0, 0.0, 1.0, 72.0, 720.0], "cm")]

    def test_a_literal_string(self):
        got = list(psstream.tokenize(b"(hello) Tj"))
        assert got == [([b"hello"], "Tj")]

    def test_a_string_with_escaped_parens(self):
        got = list(psstream.tokenize(rb"(a\(b\)c) Tj"))
        assert got[0][0][0] == rb"a\(b\)c"

    def test_a_name(self):
        got = list(psstream.tokenize(b"/F14 9.96 Tf"))
        assert got == [(["/F14", 9.96], "Tf")]

    def test_a_tj_array_keeps_its_kerns(self):
        got = list(psstream.tokenize(b"[(D.)-357.7(S.)]TJ"))
        operands, op = got[0]
        assert op == "TJ"
        assert operands[-1] == [b"D.", -357.7, b"S."]

    def test_comments_are_skipped(self):
        got = list(psstream.tokenize(b"% a comment\n1 w"))
        assert got == [([1.0], "w")]


class TestShows:
    STREAM = (b"BT /F15 1 Tf 9.96 0 0 9.96 100 400 Tm (T) Tj "
              b"/F4 1 Tf 6.97 0 0 6.97 106 398.5 Tm (P) Tj "
              b"/F5 1 Tf 9.96 0 0 9.96 112 400 Tm (=) Tj ET")

    def test_each_show_is_recorded(self):
        shows = psstream.read(self.STREAM)
        assert [s.text for s in shows] == [b"T", b"P", b"="]

    def test_the_move_before_a_show_is_kept(self):
        shows = psstream.read(self.STREAM)
        assert shows[1].move[0] == "Tm"
        assert shows[1].move[1][0] == 6.97

    def test_the_font_in_force_is_kept(self):
        shows = psstream.read(self.STREAM)
        assert [s.font for s in shows] == ["/F15", "/F4", "/F5"]

    def test_stack_depth_is_tracked(self):
        shows = psstream.read(b"q BT (a) Tj ET Q BT (b) Tj ET")
        assert shows[0].depth == 1 and shows[1].depth == 0

    def test_a_pushed_scale_is_seen(self):
        """A large delimiter is drawn by pushing a scaled CTM and popping it;
        an ordinary glyph at the same size is not."""
        shows = psstream.read(b"q 3 0 0 3 0 0 cm BT (big) Tj ET Q BT (a) Tj ET")
        assert shows[0].scaled and shows[0].ctm_scale == 3.0
        assert not shows[1].scaled

    def test_text_rise_is_recorded(self):
        shows = psstream.read(b"BT 3 Ts (a) Tj ET")
        assert shows[0].rise == 3.0 and shows[0].raised


class TestScriptGroups:
    """The measured dvips pattern: scale down, show, scale back."""

    STREAM = (b"BT /F15 1 Tf 9.96 0 0 9.96 100 405.76 Tm (T) Tj "
              b"/F4 1 Tf 6.97 0 0 6.97 106 404.27 Tm (P) Tj "
              b"/F18 1 Tf 0.89 0 TD (,A) Tj "
              b"/F5 1 Tf 9.96 0 0 9.96 120 405.76 Tm () Tj ET")

    def test_a_script_group_is_found(self):
        shows = psstream.read(self.STREAM)
        groups = psstream.script_groups(shows)
        assert len(groups) == 1

    def test_it_attaches_to_the_show_before_it(self):
        shows = psstream.read(self.STREAM)
        gp = psstream.script_groups(shows)[0]
        assert shows[gp.base].text == b"T"

    def test_its_members_are_the_shows_inside(self):
        shows = psstream.read(self.STREAM)
        gp = psstream.script_groups(shows)[0]
        assert b"".join(shows[i].text for i in gp.members) == b"P,A"

    def test_a_lowered_group_is_a_subscript(self):
        shows = psstream.read(self.STREAM)
        gp = psstream.script_groups(shows)[0]
        assert gp.kind == "sub" and gp.drop == -1.49

    def test_a_raised_group_is_a_superscript(self):
        up = (b"BT /F15 1 Tf 9.96 0 0 9.96 100 400 Tm (x) Tj "
              b"/F4 1 Tf 6.97 0 0 6.97 106 403 Tm (2) Tj "
              b"/F5 1 Tf 9.96 0 0 9.96 112 400 Tm () Tj ET")
        gp = psstream.script_groups(psstream.read(up))[0]
        assert gp.kind == "sup" and gp.drop == 3.0

    def test_a_page_move_is_not_a_script(self):
        """A drop of several em is a new line or block set smaller -- measured,
        +75.17 between a running head and the body."""
        far = (b"BT /F15 1 Tf 9.96 0 0 9.96 100 400 Tm (x) Tj "
               b"/F4 1 Tf 6.97 0 0 6.97 106 480 Tm (h) Tj "
               b"/F5 1 Tf 9.96 0 0 9.96 112 400 Tm () Tj ET")
        assert psstream.script_groups(psstream.read(far)) == []

    def test_no_scale_change_means_no_group(self):
        flat = (b"BT /F15 1 Tf 9.96 0 0 9.96 100 400 Tm (a) Tj "
                b"9.96 0 0 9.96 110 400 Tm (b) Tj ET")
        assert psstream.script_groups(psstream.read(flat)) == []


class TestLineStructureFromTheStream:
    """A display equation has NO END MARKER.

    The producer saves the graphics state, draws the expression -- closing
    and reopening the text object around every fraction rule -- and pops the
    state, restoring the current point. What follows looks like ordinary
    text. So the equation's extent can only be known from the command that
    STARTS THE NEXT LINE.

    Measured on page 1 of 91.pdf: 1183 Td events, 22 of them line returns,
    all 22 also moving down. My geometric row clustering made 85 rows of the
    same page.

        doc   stream lines   geometric rows   gold equations
        91              22               85                2
        93              16               78                2
        95              16               87                4
    """

    def _shows(self, moves):
        out = []
        for i, (op, ops) in enumerate(moves):
            s = psstream.Show(op="Tj", text=b"x", index=i)
            s.move = (op, ops)
            s.text_object = 0
            out.append(s)
        return out

    def test_a_return_to_the_margin_is_a_line(self):
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [20.0, 0.0]),
                          ("Td", [-110.0, -14.0])])
        assert len(psstream.line_breaks(sh)) == 1

    def test_a_move_within_the_line_is_not(self):
        """Every glyph is placed with a Td; only the RETURN is a line."""
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [8.4, -1.8]),
                          ("Td", [7.6, 1.8])])
        assert psstream.line_breaks(sh) == []

    def test_a_return_that_does_not_descend_is_not_a_line(self):
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [-110.0, 0.0])])
        assert psstream.line_breaks(sh) == []

    def test_line_starts_are_absolute_and_descend(self):
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [20.0, 0.0]),
                          ("Td", [-110.0, -14.0])])
        ys = psstream.line_starts(sh)
        assert ys == [700.0, 686.0]

    def test_a_text_object_reset_is_NOT_a_new_line(self):
        """The producer opens a text object around every fraction rule -- 59
        on one page. What follows RESUMES the line it interrupted. Counting
        each reset as a line gave 81 starts where the returns say 22."""
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [20.0, 0.0])])
        sh[1].text_object = 1          # BT ... ET around a rule
        assert len(psstream.line_starts(sh)) == 1

    def test_the_move_operands_are_a_list(self):
        """`move` is (op, [dx, dy]), not (op, dx, dy). Reading it the second
        way found ZERO line breaks on a page that has twenty-two, and the
        zero looked exactly like 'this producer does not do that'."""
        sh = self._shows([("Td", [100.0, 700.0]), ("Td", [-110.0, -14.0])])
        assert sh[0].move[1] == [100.0, 700.0]
        assert len(psstream.line_breaks(sh)) == 1


class TestExpressionEndFromLookAhead:
    """Nothing INSIDE a display says where it stops.

    The producer pops the graphics state and the current point with it, so
    the expression has no terminator. The line AFTER it announces itself, by
    starting at the body margin instead of at the display indent. That is
    the only statement of the end that exists, and it is a look-ahead.

    `line_starts` returns only y, which bounds a LINE and not an
    EXPRESSION. `line_origins` keeps the x, and `display_runs` uses it.

    Measured on the 102 documents: gold 421 authored displays, 288 runs
    found this way -- 0.68x, exact 21%, within one 53%. Against the
    markdown's own 817 (1.94x, exact 9%).
    """

    def _o(self, xs_ys):
        return list(xs_ys)

    def test_the_margin_is_where_most_lines_begin(self):
        o = self._o([(72.0, 700), (72.0, 686), (72.0, 672), (200.0, 650)])
        runs = psstream.display_runs(o)
        assert [k for k, _ in runs] == ["body", "display"]

    def test_a_display_ends_at_the_return_to_the_margin(self):
        o = self._o([(72.0, 700), (200.0, 680), (72.0, 650)])
        runs = psstream.display_runs(o)
        assert [k for k, _ in runs] == ["body", "display", "body"]

    def test_consecutive_indented_lines_are_ONE_display(self):
        """A two-line aligned equation is one expression, not two."""
        o = self._o([(72.0, 700), (200.0, 680), (210.0, 660), (72.0, 630)])
        runs = psstream.display_runs(o)
        assert len(runs) == 3 and runs[1][1] == [1, 2]

    def test_a_page_with_no_display_has_no_run(self):
        o = self._o([(72.0, 700), (72.0, 686), (72.0, 672)])
        assert all(k == "body" for k, _ in psstream.display_runs(o))

    def test_no_origins_is_no_runs(self):
        assert psstream.display_runs([]) == []

    def test_origins_keep_the_x(self):
        """`line_starts` threw it away, which is why the end of an
        expression could not be found."""
        sh = []
        for i, (op, ops) in enumerate([("Td", [120.0, 700.0]),
                                       ("Td", [-110.0, -14.0])]):
            s = psstream.Show(op="Tj", text=b"x", index=i)
            s.move = (op, ops)
            s.text_object = 0
            sh.append(s)
        assert psstream.line_origins(sh) == [(120.0, 700.0), (10.0, 686.0)]
