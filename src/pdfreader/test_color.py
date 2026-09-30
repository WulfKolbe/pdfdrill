"""Tests for colour captured from the PDF colour operators.

    Gray   g / G      one number
    RGB    rg / RG    three numbers
    CMYK   k / K      four numbers

Lower case sets the non-stroking colour -- the fill, which paints text --
and upper case the stroking colour, which paints rules and borders.
"""
import docmodel_six as D
import project_mmd as M
import texpackages as T


class TestColourOperands:
    def test_gray_operand(self):
        assert D.to_rgb(0.5) == (0.5, 0.5, 0.5)

    def test_gray_black_is_none(self):
        """Black is the overwhelmingly common case and costs nothing."""
        assert D.to_rgb(0.0) is None
        assert D.to_rgb([0.0]) is None

    def test_rgb_operand(self):
        """Measured on a real page: 435 glyphs of ISL set notation."""
        assert D.to_rgb((0.58, 0.0, 0.82)) == (0.58, 0.0, 0.82)

    def test_rgb_black_is_none(self):
        assert D.to_rgb((0.0, 0.0, 0.0)) is None

    def test_cmyk_operand(self):
        """c=0 m=1 y=1 k=0 is red."""
        assert D.to_rgb((0.0, 1.0, 1.0, 0.0)) == (1.0, 0.0, 0.0)

    def test_cmyk_black_is_none(self):
        assert D.to_rgb((0.0, 0.0, 0.0, 1.0)) is None

    def test_junk_is_none(self):
        for v in (None, "x", (), (1, 2, 3, 4, 5)):
            assert D.to_rgb(v) is None


class TestColourInLatexNotMarkdown:
    """Markdown has no way to say colour, so it says nothing -- which is what
    Mathpix does with its .md as well. The LaTeX carries it."""

    def _page(self, color=None, fill=None):
        from texmap import project
        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        gl = []
        x = 100.0
        for c in "abc":
            gl.append(D.GlyphNode(
                id=f"g{x}", page=1, rect=(x, 200.0, x + 5.0, 210.0),
                text=c, cid=0, glyphname=None, fontname="ABC+Helv",
                family="text", size=10.0, tex=project("text", None),
                matrix=(10.0, 0, 0, 10.0, x, 200.0), color=color))
            x += 5.0
        page.lines = [D.LineNode(id="l", page=1, rect=(100, 200, x, 210),
                                 type="text", glyphs=gl)]
        if fill:
            page.fills = [D.FillNode(rect=(90, 195, 130, 215), color=fill)]
        return page

    def test_textcolor_in_latex(self):
        tex = M.to_latex([self._page(color=(0.58, 0.0, 0.82))], preamble=False)
        assert r"\textcolor[rgb]{0.58,0,0.82}" in tex

    def test_no_colour_in_markdown(self):
        md = M.to_markdown([self._page(color=(0.58, 0.0, 0.82))])
        assert "textcolor" not in md and "colorbox" not in md

    def test_black_text_is_not_wrapped(self):
        tex = M.to_latex([self._page(color=None)], preamble=False)
        assert "textcolor" not in tex

    def test_colorbox_for_a_background(self):
        tex = M.to_latex([self._page(fill=(0.6, 1.0, 0.6))], preamble=False)
        assert r"\colorbox[rgb]{0.6,1,0.6}" in tex

    def test_xcolor_is_required(self):
        assert "xcolor" in T.packages_for(r"\textcolor[rgb]{1,0,0}{x}")
        assert "xcolor" in T.packages_for(r"\colorbox[rgb]{1,1,0}{x}")

    def test_xcolor_not_required_without_colour(self):
        assert "xcolor" not in T.packages_for(r"$\alpha + \beta$")
