"""Tests for the equation evidence entries.

pdfdrill builds a table per document -- Identifier, Page, Conf., LaTeX
source, Rendered, Image -- and inkdrill compares the rendered LaTeX against
the crop as INK. Every row has to be honest about what it is, because a
comparison is only as good as the row it is given.
"""
import docmodel_six as D
import equations as E
from texmap import project


_GREEK = {"a": "alpha", "b": "beta", "c": "gamma", "d": "delta",
          "e": "epsilon", "f": "zeta", "x": "xi", "y": "eta", "z": "chi"}


def _line(page_no, x0, y, texts, size=10.0, math=True):
    gl = []
    x = x0
    for t in texts:
        n = D.GlyphNode(
            id=f"g{page_no}-{x}", page=page_no,
            rect=(x, y, x + 5.0, y + size), text=t, cid=0,
            glyphname=_GREEK.get(t, "alpha") if math else None,
            fontname="ABC+CMMI10" if math else "ABC+CMR10",
            family="math-italic" if math else "text", size=size,
            tex=project("math-italic" if math else "text",
                        _GREEK.get(t, "alpha") if math else None),
            matrix=(size, 0, 0, size, x, y))
        gl.append(n)
        x += 5.0
    return D.LineNode(id=f"p{page_no}l{y}", page=page_no,
                      rect=(x0, y, x, y + size), type="text", glyphs=gl)


def _page(lines, page_no=1):
    """A page with a BODY line at the left margin.

    `is_display` requires a line indented past the body margin, so a page
    holding only the display lines has no margin to be indented from.
    """
    p = D.PageNode(page=page_no, rect=(0, 0, 612, 792))
    # SEVERAL body lines: the margin is the MODAL left edge, so one body
    # line is outvoted by two display lines and the margin comes out at the
    # display indent.
    body = [_line(page_no, 72.0, 760.0 - i * 12.0, "prose text here",
                  math=False) for i in range(4)]
    p.lines = body + list(lines)
    return p


class TestRowShape:
    def test_a_row_has_the_table_s_columns(self):
        page = _page([_line(1, 200.0, 700.0, "abc")])
        rows = [e.as_row() for e in E.equations([page], "doc")]
        assert rows
        for key in ("identifier", "page", "confidence", "latex", "region",
                    "kind", "structural_ok"):
            assert key in rows[0], key

    def test_the_label_is_sequential_and_padded(self):
        page = _page([_line(1, 200.0, 700.0, "a"),
                      _line(1, 200.0, 680.0, "b")])
        eqs = E.equations([page], "doc")
        assert eqs[0].label == "EQ0001"

    def test_the_identifier_is_content_addressed(self):
        """Sequential ids turn every diff between two runs into noise."""
        page = _page([_line(1, 200.0, 700.0, "abc")])
        a = E.equations([page], "doc")[0].ident
        b = E.equations([_page([_line(1, 200.0, 700.0, "abc")])], "doc")[0]
        assert a == b.ident and a.startswith("eq_")

    def test_different_content_gives_a_different_identifier(self):
        a = E.equations([_page([_line(1, 200.0, 700.0, "abc")])], "d")[0]
        b = E.equations([_page([_line(1, 200.0, 700.0, "xyz")])], "d")[0]
        assert a.ident != b.ident

    def test_the_region_is_in_pixels(self):
        """Same 250-dpi space as lines.json, so the Image column needs no
        rescaling."""
        page = _page([_line(1, 200.0, 700.0, "abc")])
        r = E.equations([page], "doc")[0].region
        assert r["top_left_x"] > 600 and r["width"] > 0


class TestConfidence:
    def test_everything_projected_is_one(self):
        page = _page([_line(1, 200.0, 700.0, "abc")])
        assert E.equations([page], "doc")[0].confidence == 1.0

    def test_confidence_is_projection_only(self):
        """A structural defect is reported SEPARATELY. Collapsing two
        different facts into one score is what makes a benchmark unable to
        see its own errors."""
        page = _page([_line(1, 200.0, 700.0, "abc")])
        eq = E.equations([page], "doc")[0]
        assert eq.confidence == 1.0 and eq.structural_ok


class TestStructuralCheck:
    def test_an_unmatched_opener_is_flagged(self):
        """A `cases` construct reaches the page as a fence line plus one
        line per branch. Scored by projection alone each part came out at
        1.000 while the construct was never assembled."""
        assert E._structural_penalty(r"\Biggl\{ x \in Nat") > 0

    def test_a_matched_pair_is_not(self):
        assert E._structural_penalty(r"\left( x \right)") == 0.0

    def test_plain_maths_is_not(self):
        assert E._structural_penalty(r"\alpha + \beta") == 0.0

    def test_no_latex_is_not_a_structural_failure(self):
        """An equation that produced nothing is an empty row, not an
        unbalanced one."""
        assert E._structural_penalty(None) == 0.0


class TestDisplayRuns:
    def test_consecutive_display_lines_are_one_equation(self):
        """The reference table shows a multi-line `cases` as ONE row."""
        page = _page([_line(1, 200.0, 700.0, "abc"),
                      _line(1, 200.0, 688.0, "def")])
        eqs = [e for e in E.equations([page], "doc") if e.kind == "display"]
        assert len(eqs) == 1

    def test_a_gap_starts_a_new_equation(self):
        page = _page([_line(1, 200.0, 700.0, "abc"),
                      _line(1, 200.0, 600.0, "def")])
        eqs = [e for e in E.equations([page], "doc") if e.kind == "display"]
        assert len(eqs) == 2


class TestSummary:
    def test_the_counts_add_up(self):
        page = _page([_line(1, 200.0, 700.0, "abc")])
        d = E.to_json([page], "doc")
        c = d["counts"]
        assert c["total"] == len(d["equations"])
        assert c["display"] + c["inline"] == c["total"]
