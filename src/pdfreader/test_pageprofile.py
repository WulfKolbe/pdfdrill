"""Tests for the page profile — 781o.

The instrument exists because COUNTING MISLEADS: `pdftc_900k_1018.pdf`
carries 10,368 monospace glyphs and 170 rows of listing, so a count of
glyphs calls it code and a count of rows calls it prose.
"""
import pageprofile as pr
from docmodel_six import FillNode, GlyphNode, LineNode, PageNode
from texmap import project


def g(ch, x, font="TEST+NimbusMonL-Regu", size=8.0, y=100.0):
    return GlyphNode(id="g%s%.0f" % (ch, x), page=1,
                     rect=(x, y, x + 0.6 * size, y + size), text=ch, cid=ord(ch),
                     glyphname=None, fontname=font, family="text", size=size,
                     tex=project("text", None), matrix=(size, 0, 0, size, x, y))


def line(text, x0=50.0, y=100.0, font="TEST+NimbusMonL-Regu"):
    gs = [g(c, x0 + i * 4.23, font, y=y) for i, c in enumerate(text) if c != " "]
    return LineNode(id="l%.0f" % y, page=1,
                    rect=(x0, y, x0 + len(text) * 4.23, y + 8.0),
                    type="text", glyphs=gs)


def page(lines, **kw):
    p = PageNode(page=1, rect=(0, 0, 595, 842), lines=lines, **kw)
    import listings
    p.listings = listings.accumulate(p)
    return p


class TestTheDistinctionACountCannotMake:
    def test_monospace_in_prose_is_inline_code_not_a_listing(self):
        """The 781o case: many monospace glyphs, no block."""
        p = page([line("run the fetch_page command now", y=300.0,
                       font="TEST+NimbusRomNo9L-Regu")]
                 + [line("call parse_header() to start", y=290.0)])
        f = pr.page_profile(p)
        assert "inline-code" in f
        assert "listing" not in f

    def test_a_grid_run_is_a_listing(self):
        p = page([line("for (i in 0..N)", y=300.0),
                  line("  for (j in 0..M)", y=290.0),
                  line("    b1[j] = a*f1[i,j]", y=280.0)])
        f = pr.page_profile(p)
        assert "listing" in f
        assert "rows" in f.props["listing"]

    def test_one_stray_monospace_word_is_not_a_property(self):
        """A single \\texttt{n} in a paragraph is not 'inline code'."""
        gs = [g(c, 50.0 + i * 4.23, "TEST+NimbusRomNo9L-Regu", y=300.0)
              for i, c in enumerate("the value of ")]
        gs += [g(c, 110.0 + i * 4.23, y=300.0) for i, c in enumerate("n")]
        ln = LineNode(id="x", page=1, rect=(50, 300, 200, 308), type="text",
                      glyphs=gs)
        assert "inline-code" not in pr.page_profile(page([ln]))


class TestEvidenceNotABoolean:
    def test_every_property_carries_its_measurement(self):
        p = page([line("for (i in 0..N)", y=300.0),
                  line("  b1[j] = 1", y=290.0)])
        for value in pr.page_profile(p).props.values():
            assert value and not isinstance(value, bool)


class TestAbsentRatherThanFalse:
    def test_a_page_with_nothing_says_nothing(self):
        p = page([line("plain prose here", y=300.0,
                       font="TEST+NimbusRomNo9L-Regu")])
        assert pr.page_profile(p).props == {}

    def test_no_glyphs_asks_for_ocr(self):
        f = pr.page_profile(PageNode(page=1, rect=(0, 0, 595, 842)))
        assert "no-text-layer" in f


class TestWhereTheDocumentCarriesIt:
    def test_the_rollup_keeps_the_page_numbers(self):
        """A 132-page manual whose listings live on 37 pages is not a
        132-page listing problem, and a boolean would hide that."""
        a = page([line("for (i in 0..N)", y=300.0),
                  line("  b1[j] = 1", y=290.0)])
        b = PageNode(page=2, rect=(0, 0, 595, 842),
                     lines=[line("plain prose", y=300.0,
                                 font="TEST+NimbusRomNo9L-Regu")])
        where = pr.document_profile([a, b])
        assert where["listing"] == [1]
        assert 2 not in where.get("listing", [])


class TestColouredFrame:
    def test_a_box_with_a_fill_behind_it(self):
        p = page([line("for (i in 0..N)", y=300.0),
                  line("  b1[j] = 1", y=290.0)],
                 fills=[FillNode(rect=(40, 280, 400, 320), color=(0.9, 0.9, 0.7))])
        p.frames = [(40.0, 280.0, 400.0, 320.0)]
        f = pr.page_profile(p)
        assert "coloured-frame" in f and "frame" in f and "coloured-fill" in f
