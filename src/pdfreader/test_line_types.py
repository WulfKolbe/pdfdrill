r"""The line CLASSIFIER behind the lines.json — 784/796.

pdfdrill's docmodel is built by twenty modules that turn TYPED lines into
`Table`, `Section`, `CodeListing`, `Formula` objects, and they key off SIXTEEN
types. `LineNode.type` has two — "text" and "formula" — so a stream carrying
only those can produce paragraphs and nothing else. Measured on 1107.2723:

    before   554 lines   text 531, formula 23
    after    554 lines   text 515, math 23, section_header 15, equation 1

and the geometry is untouched: 554 of 554 lines keep their rectangle, which is
the half that was already right and must stay right.
"""
import collections

import docmodel_six as docmodel
import project_mmd as mmd
from docmodel_six import GlyphNode, LineNode, PageNode
from texmap import project


def g(ch, x, y=700.0, size=10.0, font="TEST+NimbusRomNo9L-Regu"):
    return GlyphNode(
        id=f"g{ch}{x:.0f}", page=1, rect=(x, y, x + 0.5 * size, y + size),
        text=ch, cid=ord(ch), glyphname=None, fontname=font,
        family="text", size=size, tex=project("text", None),
        matrix=(size, 0, 0, size, x, y))


def line(text, *, x0=72.0, y=700.0, size=10.0, kind="text"):
    gs, x = [], x0
    for i, w in enumerate(text.split()):
        if i:
            x += 0.5 * size
        for ch in w:
            gs.append(g(ch, x, y, size))
            x += 0.5 * size
    return LineNode(id=f"l{y:.0f}", page=1, rect=(x0, y, x, y + size),
                    type=kind, glyphs=gs)


def page(lines, w=595.0, h=842.0):
    return PageNode(page=1, rect=(0.0, 0.0, w, h), lines=lines)


def content(recs):
    """The emitted records that are LINES, not containers. `to_lines_json`
    now puts the column containers first, so a test that means "the first
    line" has to say so."""
    return [r for r in recs if r["type"] != "column"]


class TestTheFallback:
    def test_a_formula_line_keeps_its_verdict(self):
        """THE REGRESSION THIS EXISTS FOR. The glyph-family count asks whether
        60% of a line is set in a maths font, which a sentence with one inline
        expression in it is not. Dropping to a literal "text" when that test
        fails lost all 23 formula lines of 1107.2723 — a classifier that knew
        less than the node it was classifying. `formula` is spelled `math`
        because that is the word pdfdrill's modules read."""
        p = page([line("x plus y", kind="formula")])
        assert mmd.classify_lines([p])[(1, 0)][0] == "math"

    def test_ordinary_prose_stays_text(self):
        p = page([line("We propose a method that learns a metric")])
        assert mmd.classify_lines([p])[(1, 0)][0] == "text"

    def test_a_line_with_no_glyphs_is_text_not_a_crash(self):
        p = page([LineNode(id="x", page=1, rect=(0, 0, 1, 1), type="text")])
        assert mmd.classify_lines([p])[(1, 0)] == ("text", {})


class TestTheVocabulary:
    def test_every_type_emitted_is_one_pdfdrill_reads(self):
        """A type nothing measures would produce a Section the document does
        not contain, and every projection would carry it."""
        p = page([line("We propose a method that learns a metric"),
                  line("x plus y", y=680.0, kind="formula")])
        for (t, _extra) in mmd.classify_lines([p]).values():
            assert t in mmd.LINE_TYPES, t


class TestTheEmitter:
    def test_the_type_reaches_the_lines_json(self):
        p = page([line("x plus y", kind="formula")])
        out = docmodel.to_lines_json([p])
        assert content(out["pages"][0]["lines"])[0]["type"] == "math"

    def test_every_line_still_carries_a_rectangle(self):
        """The geometry is the half that was always right. A classifier that
        costs it is a regression however good its types are."""
        p = page([line("We propose a method that learns a metric"),
                  line("x plus y", y=680.0, kind="formula")])
        lines = content(docmodel.to_lines_json([p])["pages"][0]["lines"])
        assert len(lines) == 2
        for ln in lines:
            r = ln["region"]
            assert r["width"] > 0 and r["height"] > 0

    def test_a_classifier_failure_costs_the_types_not_the_geometry(self, monkeypatch):
        """`to_lines_json` falls back to the node's own type when the
        classifier raises, because a lines.json with weak types is a working
        document and a lines.json with no rectangles is not."""
        monkeypatch.setattr(mmd, "classify_lines",
                            lambda pages: (_ for _ in ()).throw(RuntimeError("boom")))
        p = page([line("x plus y", kind="formula")])
        out = content(docmodel.to_lines_json([p])["pages"][0]["lines"])[0]
        assert out["type"] == "formula"          # the node's own verdict
        assert out["region"]["width"] > 0


class TestContainment:
    """The one level of nesting MathPix has and we had none of: 1244 lines
    with a `parent_id` against our 0. It is not decoration — it is the reading
    order of a two-column paper, stated rather than left for each consumer to
    rediscover from x-coordinates."""

    def _two_columns(self):
        # Every threshold in `columns()` is corpus-measured and this fixture
        # has to clear all of them: FIVE lines before a cluster of line-starts
        # is a column at all (a stray equation number at the right margin is
        # three), and then EIGHT before it is a real share of the page
        # (wzlxjtu-009 put 4 lines in its supposed second column against 29 in
        # the first, and reading that page as two-column cost 3 equations).
        # …and each column must be at least a fifth of the page WIDE, because
        # a run of equation numbers at the right margin clusters like a column
        # and is 15pt across. So the fixture needs real line lengths, not
        # labels.
        body = "running text of a real column that is wide enough to be one"
        left = [line(f"{body} left {i}", x0=54.0, y=700.0 - 12 * i)
                for i in range(10)]
        right = [line(f"{body} right {i}", x0=331.0, y=700.0 - 12 * i)
                 for i in range(10)]
        return page(left + right)

    def test_a_column_container_is_emitted_with_its_children(self):
        p = self._two_columns()
        recs = docmodel.to_lines_json([p])["pages"][0]["lines"]
        cols = [r for r in recs if r["type"] == "column"]
        assert len(cols) == 2, [r["type"] for r in recs]
        assert sum(len(c["children_ids"]) for c in cols) == 20

    def test_every_content_line_names_a_parent_that_exists(self):
        """A dangling parent is worse than a flat list: a reader building a
        tree in one pass silently drops the child."""
        p = self._two_columns()
        recs = docmodel.to_lines_json([p])["pages"][0]["lines"]
        ids = {r["id"] for r in recs}
        content = [r for r in recs if r["type"] != "column"]
        assert content and all(r.get("parent_id") in ids for r in content)

    def test_the_container_carries_a_real_rectangle(self):
        """A container is a MEASUREMENT, not a label — the union of the lines
        it holds, so a reader can draw it and check it against the page."""
        p = self._two_columns()
        recs = docmodel.to_lines_json([p])["pages"][0]["lines"]
        for c in (r for r in recs if r["type"] == "column"):
            assert c["region"]["width"] > 0 and c["region"]["height"] > 0
            assert c["text"] == "" and c["conversion_output"] is False

    def test_the_parent_comes_before_its_children(self):
        """MathPix orders them this way and a one-pass tree builder needs it:
        meet the parent before the children it names."""
        p = self._two_columns()
        recs = docmodel.to_lines_json([p])["pages"][0]["lines"]
        first_content = next(i for i, r in enumerate(recs) if r["type"] != "column")
        assert all(r["type"] == "column" for r in recs[:first_content])

    def test_a_page_with_no_lines_gets_no_container(self):
        assert docmodel.to_lines_json([page([])])["pages"][0]["lines"] == []


class TestRunningHeaders:
    """`Signal & Image Processing … Vol.2, No.2, June 2011` stands at the top of
    all 16 pages of 1107.2723 and arrived as 16 Paragraphs, because nothing
    typed it and `text` becomes prose."""

    def _doc(self, n=6, header="Journal of Measured Things Volume 2 Number 2"):
        pages = []
        for k in range(1, n + 1):
            body = [line(f"body line {i} of page {k}", y=600.0 - 12 * i)
                    for i in range(10)]
            hdr = line(header, y=820.0)
            folio = line(str(100 + k), x0=300.0, y=30.0)
            p = page(body + [hdr, folio])
            p.page = k
            for ln in p.lines:
                ln.page = k
            pages.append(p)
        return pages

    def test_a_repeating_header_is_page_info(self):
        t = mmd.classify_lines(self._doc())
        hdr = [v for (pg, i), v in t.items() if pg == 1 and v[0] == "page_info"]
        assert hdr, "the header repeated on every page is still prose"

    def test_a_bare_folio_is_page_info_even_though_it_never_repeats(self):
        """The repeat test cannot see a page number — it differs on every page.
        A line in the margin band that is nothing but digits is one anyway."""
        pages = self._doc()
        t = mmd.classify_lines(pages)
        folio = t[(3, len(pages[2].lines) - 1)]
        assert folio[0] == "page_info", folio

    def test_body_text_in_the_middle_of_the_page_is_never_page_info(self):
        t = mmd.classify_lines(self._doc())
        assert t[(1, 0)][0] != "page_info"

    def test_two_pages_abstain(self):
        """A line on both pages of a two-page document is as likely to be a
        coincidence as a header, and being wrong deletes a paragraph."""
        assert all(v[0] != "page_info"
                   for v in mmd.classify_lines(self._doc(n=2)).values())


class TestTitle:
    """796 typed a title set on three lines as THREE `Section`s. A title on
    three lines is one title."""

    def _front(self):
        big = [line("TOPOGRAPHIC FEATURE EXTRACTION", y=800.0, size=18.0),
               line("FOR", y=778.0, size=18.0),
               line("BENGALI AND HINDI CHARACTER IMAGES", y=756.0, size=18.0)]
        rest = [line(f"body line {i} set in the document text size", y=700.0 - 12 * i)
                for i in range(10)]
        return [page(big + rest)]

    def test_the_run_of_largest_lines_is_the_title(self):
        t = mmd.classify_lines(self._front())
        assert [t[(1, i)][0] for i in range(3)] == ["title"] * 3

    def test_the_run_stops_at_the_first_smaller_line(self):
        """Consecutive is what makes it ONE title rather than every large line
        on the page."""
        t = mmd.classify_lines(self._front())
        assert t[(1, 3)][0] != "title"

    def test_a_page_with_no_size_contrast_has_no_title(self):
        """Calling the first lines of a uniformly-set page a title deletes them
        from the prose."""
        flat = [page([line(f"body line {i} all one size", y=700.0 - 12 * i)
                      for i in range(10)])]
        assert all(v[0] != "title" for v in mmd.classify_lines(flat).values())

    def test_a_whitespace_line_neither_starts_nor_ends_the_title(self):
        """Two of them bracketed 1107.2723's title and arrived as `title` lines
        with a body of " "."""
        pages = self._front()
        pages[0].lines.insert(0, line("   ", y=810.0, size=18.0))
        t = mmd.classify_lines(pages)
        assert t[(1, 0)][0] != "title"
        assert [t[(1, i)][0] for i in (1, 2, 3)] == ["title"] * 3


class TestRotatedText:
    """An arXiv identifier stamped down the left margin belongs to the ARCHIVE,
    not to the paper. Typed `text`, it arrived inside the running prose of the
    section it sits beside — and on the readers that group by baseline it
    arrived as single-character lines, an extra column of nonsense."""

    def _sideways(self, text="arXiv:1909.00741v1", deg=90):
        gs, y = [], 300.0
        for ch in text:
            g_ = g(ch, 20.0, y)
            # the CTM is the whole test: rotation lives in b and c
            g_.matrix = (0, 10.0, -10.0, 0, 20.0, y) if deg == 90 else \
                        (0, -10.0, 10.0, 0, 20.0, y)
            gs.append(g_)
            y += 6.0
        ln = LineNode(id="rot", page=1, rect=(16.0, 300.0, 36.0, y),
                      type="text", glyphs=gs)
        ln.rotated = True
        body = [line(f"body line {i} of ordinary prose", y=700.0 - 12 * i)
                for i in range(10)]
        return [page([ln] + body)]

    def test_sideways_text_is_its_own_type(self):
        t = mmd.classify_lines(self._sideways())
        assert t[(1, 0)][0] == "rotated_text"

    def test_the_angle_rides_along(self):
        """A reader cropping the region needs it, and cannot recover it from a
        rectangle."""
        assert mmd.classify_lines(self._sideways(deg=90))[(1, 0)][1]["rotation"] == 90
        assert mmd.classify_lines(self._sideways(deg=270))[(1, 0)][1]["rotation"] == 270

    def test_upright_prose_is_never_rotated_text(self):
        t = mmd.classify_lines(self._sideways())
        assert all(v[0] != "rotated_text" for k, v in t.items() if k != (1, 0))

    def test_it_reaches_the_lines_json_with_its_rectangle(self):
        recs = docmodel.to_lines_json(self._sideways())["pages"][0]["lines"]
        rot = [r for r in recs if r["type"] == "rotated_text"]
        assert len(rot) == 1
        r = rot[0]
        assert r["region"]["height"] > r["region"]["width"], \
            "a 90-degree stamp is taller than it is wide"
        assert r["rotation"] == 90


class TestFrontMatter:
    """`authors` and `abstract` are each defined by what SURROUNDS them, which
    is why `title` had to come first: the title is the upper bound and the next
    heading is the lower one."""

    def _paper(self, with_heading=True, label="ABSTRACT"):
        lines = [line("A TITLE SET LARGE", y=800.0, size=18.0),
                 line("Ada Lovelace and Alan Turing", y=770.0, size=11.0),
                 line("Department of Computing, Somewhere", y=756.0, size=11.0)]
        if with_heading:
            # 14pt against a 10pt body: `heading_level` ranks type SIZES, and
            # 13pt does not clear the rank against this body. The fixture has
            # to be a document the classifier could actually meet.
            lines.append(line(label, y=730.0, size=14.0))
            lines += [line(f"abstract sentence number {i} of the summary",
                           y=710.0 - 12 * i) for i in range(4)]
            lines.append(line("1. INTRODUCTION", y=640.0, size=14.0))
        lines += [line(f"body line {i} of the paper proper", y=600.0 - 12 * i)
                  for i in range(10)]
        return [page(lines)]

    def test_the_author_block_is_bounded_by_the_next_heading(self):
        t = mmd.classify_lines(self._paper())
        assert [t[(1, i)][0] for i in (1, 2)] == ["authors", "authors"]

    def test_the_abstract_runs_from_its_label_to_the_next_heading(self):
        t = mmd.classify_lines(self._paper())
        assert t[(1, 3)][0] == "section_header", "the label is not the abstract"
        assert [t[(1, i)][0] for i in (4, 5, 6, 7)] == ["abstract"] * 4
        assert t[(1, 8)][0] == "section_header"
        assert t[(1, 9)][0] != "abstract", "the abstract ended at the heading"

    def test_a_german_label_is_recognised(self):
        t = mmd.classify_lines(self._paper(label="Zusammenfassung"))
        assert t[(1, 4)][0] == "abstract"

    def test_without_a_closing_heading_both_abstain(self):
        """A front matter with no heading after the title has no measurable end
        to its author block, and taking 'the rest of the page' would swallow
        the first section of the paper."""
        t = mmd.classify_lines(self._paper(with_heading=False))
        assert all(v[0] not in ("authors", "abstract") for v in t.values())

    def test_a_page_with_no_title_has_no_author_block(self):
        flat = [page([line(f"body line {i} all one size", y=700.0 - 12 * i)
                      for i in range(10)])]
        assert all(v[0] != "authors" for v in mmd.classify_lines(flat).values())


class TestCaptionsAndTables:
    """MathPix crops a table to an image; the goal is a LaTeX `tabular`. The
    logical first step is a correct rectangle and the caption that belongs to
    it — measured on 1909.00741 page 7, six tables in two columns."""

    def test_a_caption_needs_its_separator(self):
        """`Table 2 shows that …` in running prose is a sentence. Without the
        separator a sentence becomes a figure."""
        assert mmd._caption_of(line("Table 2: Pool CL Conservative Assessment"))
        assert mmd._caption_of(line("Figure 3. Images with labels"))
        assert mmd._caption_of(line("Abbildung 4 - Ergebnisse"))
        assert mmd._caption_of(line("Table 2 shows that the method works")) is None

    def test_an_unknown_first_word_is_not_a_caption(self):
        assert mmd._caption_of(line("Equation 7: the field tensor")) is None

    def test_the_label_and_number_are_carried(self):
        c = mmd._caption_of(line("Tabelle 3.1: Messwerte"))
        assert c == {"label": "table", "number": "3.1"}

    def test_a_rule_cluster_with_no_caption_is_not_a_table(self):
        """A form, a letterhead, a signature line. Calling it a table would put
        an empty tabular into every projection of a letter."""
        p = page([line(f"body line {i} of a plain page", y=700.0 - 12 * i)
                  for i in range(10)])
        assert mmd.table_regions(p) == []

    def test_one_rule_is_a_separator_not_a_table(self):
        from docmodel_six import RuleNode
        p = page([line("Table 1: a caption above one rule", y=700.0)] +
                 [line(f"body {i}", y=680.0 - 12 * i) for i in range(6)])
        p.lines[0].rules = [RuleNode(id="r", page=1,
                                     rect=(54.0, 690.0, 294.0, 690.6),
                                     role="fraction")]
        assert mmd.table_regions(p) == []


class TestFootnotes:
    """A footnote is not where its MARKER is. The marker sits mid-paragraph and
    the body sits at the foot of the column, so reading order places it wrongly
    and text matching places it on whatever prose is nearest. On 2510.04618 the
    footnote `We mention IBM CUGA as a rough contextual reference…` was absorbed
    into a Paragraph.

    Measured there: body 10.0pt, footnote 8.97pt, last body line top y 123, the
    footnote at y 99 and 79 — and NO footnote rule anywhere on the page, its
    only rules being the table's 300pt higher. So the rule the specification
    assumed cannot be required.
    """

    def _page_with_footnote(self, fn_size=8.0, n_body=10):
        body = [line(f"body line {i} of the running prose", y=700.0 - 12 * i,
                     size=10.0) for i in range(n_body)]
        fn = [line("We mention IBM CUGA as a rough contextual reference",
                   y=99.0, size=fn_size),
              line("direct comparisons. CUGA's internal design differs",
                   y=79.0, size=fn_size)]
        return [page(body + fn)]

    def test_smaller_text_below_the_last_body_line_is_a_footnote(self):
        t = mmd.classify_lines(self._page_with_footnote())
        assert [t[(1, 10)][0], t[(1, 11)][0]] == ["footnote", "footnote"]

    def test_the_body_is_not_a_footnote(self):
        t = mmd.classify_lines(self._page_with_footnote())
        assert all(t[(1, i)][0] != "footnote" for i in range(10))

    def test_a_uniform_page_has_no_footnote(self):
        """Calling the last lines of a uniformly-set page a footnote deletes
        them from the prose."""
        t = mmd.classify_lines(self._page_with_footnote(fn_size=10.0))
        assert all(v[0] != "footnote" for v in t.values())

    def test_no_rule_is_required(self):
        """2510.04618 draws none, and requiring one missed every footnote in
        it. A rule corroborates; it is not the evidence."""
        pages = self._page_with_footnote()
        assert not any(ln.rules for ln in pages[0].lines)
        t = mmd.classify_lines(pages)
        assert any(v[0] == "footnote" for v in t.values())

    def test_a_caption_at_the_page_foot_stays_a_caption(self):
        """A figure at the foot of a page puts its caption below the last body
        line at a smaller size too. The caption has a LABEL, which is the
        harder evidence, so it is tested first."""
        pages = self._page_with_footnote()
        pages[0].lines.insert(10, line("Figure 3: the apparatus", y=110.0, size=8.0))
        t = mmd.classify_lines(pages)
        assert t[(1, 10)][0] == "caption"
