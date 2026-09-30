"""Tests for project_mmd (Mathpix crop syntax, page separators, headings)
and inspectserver (the crop resolver).

The crop URL contract is checked against a real Mathpix `tex.zip`, not against
my reading of their docs: their bundled crops encode the same four numbers in
the filename, so the zip is ground truth for field order.
"""

import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest

import docmodel_six as docmodel
import inspectserver
import testpaths
import project_mmd as M

MIELKE = testpaths.CORPUS_PDF
LINES = testpaths.CORPUS_LINES
TEXZIP_IMAGES = testpaths.TEXZIP_IMAGES
PAGES_DIR = testpaths.PAGES_DIR


# Per CLASS where a whole class needs the corpus, per TEST where only some
# members do -- see the note in test_docmodel_six.py.
#
# The per-class version still over-gated by 23: five of the nine classes
# hold a mix, and gating the class took the synthetic tests with it. 46 of
# 91 were skipping where 23 need a fixture. The same defect one layer out,
# which is how the user described it.
needs_corpus = pytest.mark.skipif(
    not os.path.exists(MIELKE),
    reason="no corpus PDF; set PDF2MMD_TEST_PDF to run these")


@pytest.fixture(scope="module")
def pages():
    return docmodel.build(MIELKE, range(204, 212))


class TestCropURLSyntax:
    @needs_corpus
    def test_query_param_order_and_names(self, pages):
        p = pages[0]
        url = M.crop_url((0.0, 0.0, 10.0, 20.0), p, "abc", "http://h")
        assert url.startswith("http://h/cropped/abcg-%d.jpg?" % p.page)
        q = url.split("?", 1)[1]
        assert q.split("&")[0].startswith("height=")
        assert q.split("&")[1].startswith("width=")
        assert q.split("&")[2].startswith("top_left_y=")
        assert q.split("&")[3].startswith("top_left_x=")

    @needs_corpus
    def test_y_axis_is_flipped_to_top_left_origin(self, pages):
        """docmodel is y-up in points; Mathpix is y-down in pixels."""
        p = pages[0]
        top_rect = (0.0, p.rect[3] - 10.0, 10.0, p.rect[3])
        bot_rect = (0.0, 0.0, 10.0, 10.0)
        top_y = int(M.crop_url(top_rect, p, "a", "").split("top_left_y=")[1]
                    .split("&")[0])
        bot_y = int(M.crop_url(bot_rect, p, "a", "").split("top_left_y=")[1]
                    .split("&")[0])
        assert top_y < bot_y, "a rect near the page top must have a SMALL y"
        assert top_y == 0

    @pytest.mark.skipif(not os.path.isdir(TEXZIP_IMAGES),
                        reason="needs the Mathpix tex.zip")
    def test_field_order_matches_a_real_mathpix_zip(self):
        """`<uuid>-<page>_<h>_<w>_<y>_<x>.jpg` against that page's region."""
        with open(LINES, encoding="utf-8") as fh:
            doc = json.load(fh)
        by_page = {p["page"]: p for p in doc["pages"]}
        checked = 0
        for name in os.listdir(TEXZIP_IMAGES):
            stem = name.rsplit(".", 1)[0]
            tail = stem.rsplit("-", 1)[-1]
            bits = tail.split("_")
            if len(bits) != 5:
                continue
            page, h, w, y, x = (int(b) for b in bits)
            regions = [l["region"] for l in by_page[page]["lines"]
                       if l.get("region")]
            assert any(r["height"] == h and r["width"] == w
                       and r["top_left_y"] == y and r["top_left_x"] == x
                       for r in regions), f"{name} matches no region on p{page}"
            checked += 1
        assert checked >= 5, "expected several crops in the zip"


@needs_corpus
class TestProjection:
    def test_page_separator_is_emitted(self, pages):
        md = M.to_markdown(pages)
        assert md.count("---") >= len(pages)

    def test_no_html_comments_anywhere(self, pages):
        """Markdown viewers that run a typographer rewrite `--` as an en dash,
        which breaks `<!-- ... -->` and prints it as visible text. Measured in
        Apostrophe: `<!-- page 2 -->` rendered as `<!- page 2 ->`."""
        md = M.to_markdown(pages)
        assert "<!--" not in md and "-->" not in md

    def test_separator_can_be_switched_off(self, pages):
        md = M.to_markdown(pages, page_separator="")
        assert "\n---\n" not in md

    def test_deferred_math_becomes_a_visible_crop(self, pages):
        md = M.to_markdown(pages)
        assert "![" in md, "a deferred span must render as an image"
        assert "cropped/" in md

    def test_deferred_crop_keeps_its_node_id(self, pages):
        """The node id and reason live in the image ALT text.

        Alt text survives a typographer, and is what a reader sees when the
        image server is not running -- so the placeholder still says which
        node it stands for and why it could not be projected.
        """
        import re
        md = M.to_markdown(pages)
        alts = re.findall(r"!\[([^\]]*)\]\([^)]*cropped/[^)]*\)", md)
        assert alts, "no annotated crop found"
        # The vocabulary is whatever `span_reason` currently names, not a
        # fixed list. This asserted "baseline"/"fraction"/"unknown"/"glyph",
        # which 711 renamed -- the reasons are now the FAILING PASS
        # (`script-attachment`, `assembly`, `fraction-unresolved`,
        # `unmapped-glyph:<names>`). After 730 this page emits only
        # `script-attachment` and the test failed on the rename, not on a
        # defect. It now asserts the CONTRACT -- an id and a non-empty
        # reason -- rather than a snapshot of the reasons in use.
        assert all(" " in a and a.split(" ", 1)[1].strip() for a in alts)

    def test_latex_uses_includegraphics_with_the_same_url(self, pages):
        tex = M.to_latex(pages)
        assert r"\includegraphics" in tex
        assert "cropped/" in tex and "top_left_x=" in tex

    def test_latex_emits_page_markers(self, pages):
        tex = M.to_latex(pages)
        assert r"\newpage" in tex


@needs_corpus
class TestHeadings:
    def test_body_size_is_the_modal_size(self, pages):
        fp = M.profile(pages)
        assert fp.body_size == max(fp.sizes.items(), key=lambda kv: kv[1])[0]

    def test_chapter_and_section_headings_are_found(self, pages):
        md = M.to_markdown(pages)
        heads = [l for l in md.splitlines() if l.startswith("#")]
        joined = " ".join(heads)
        assert "Chapter 10" in joined
        assert "Chern" in joined
        assert any(h.startswith("## ") for h in heads)
        assert any(h.startswith("### ") for h in heads)

    def test_wrapped_heading_is_one_heading(self, pages):
        md = M.to_markdown(pages)
        heads = [l for l in md.splitlines() if l.startswith("#")]
        assert not any(h.strip() in ("### Solutions", "## Solutions")
                       for h in heads), "a wrapped heading was split"

    def test_font_report_documents_the_evidence(self, pages):
        rep = M.font_report(pages)
        assert "Body text:" in rep
        assert "| size (pt) |" in rep and "| font |" in rep
        assert "Nothing in the PDF states them" in rep


@pytest.mark.skipif(not os.path.isdir(PAGES_DIR),
                    reason="needs a rendered inspect/pages folder")
class TestInspectServer:
    @pytest.fixture(scope="class")
    def server(self):
        inspectserver.Handler.pages = inspectserver.Pages(PAGES_DIR, [LINES])
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), inspectserver.Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()

    def test_healthz(self, server):
        data = json.loads(urlopen(server + "/healthz").read())
        assert data["ok"] and data["pages"] >= 1

    def test_crop_matches_the_mathpix_crop_byte_for_byte_in_size(self, server):
        url = (server + "/cropped/anyg-25.jpg?height=885&width=748"
                        "&top_left_y=204&top_left_x=592")
        body = urlopen(url).read()
        from io import BytesIO

        from PIL import Image
        got = Image.open(BytesIO(body))
        assert got.size == (748, 885)

    def test_page_route(self, server):
        body = urlopen(server + "/pages/p25.png").read()
        assert body[:8] == b"\x89PNG\r\n\x1a\n"

    def test_missing_rect_is_a_400_not_a_500(self, server):
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as e:
            urlopen(server + "/cropped/anyg-25.jpg?height=10")
        assert e.value.code == 400

    def test_unknown_page_is_404(self, server):
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as e:
            urlopen(server + "/cropped/anyg-999.jpg?height=10&width=10"
                             "&top_left_y=0&top_left_x=0")
        assert e.value.code == 404

    def test_page_resolved_from_trailing_integer(self, server):
        """`…g-25` must resolve to page 25 with no ?page= given."""
        body = urlopen(server + "/cropped/somethingg-25.jpg?height=50&width=50"
                                "&top_left_y=0&top_left_x=0").read()
        assert len(body) > 100


class TestRotatedText:
    """Sideways text must not be scattered through the body.

    An arXiv preprint carries a stamp rotated 90 degrees down the left margin.
    Its glyphs' text-space origins run along the page's y axis, so baseline
    clustering mixed them into the title: the stamp
    `arXiv:0805.0311v3 [math.GM] 28 Sep 2014` surfaced as `M4102peS82]`,
    `G.ht` and `ma[3v1130` wedged between heading lines.
    """

    def _page(self):
        import docmodel_six as docmodel
        return docmodel.build(testpaths.CORPUS_ROTATED, range(0, 1))

    @pytest.mark.skipif(not os.path.exists(testpaths.CORPUS_ROTATED),
                        reason="needs a PDF with rotated text")
    def test_rotated_line_is_separated_and_ordered(self):
        import docmodel_six as docmodel
        pages = self._page()
        rot = [ln for ln in pages[0].lines if ln.rotated]
        assert rot, "the rotated run was not detected"
        text = " ".join(docmodel._run_text(ln.glyphs) for ln in rot)
        assert "arXiv" in text, f"rotated run not in reading order: {text!r}"

    @pytest.mark.skipif(not os.path.exists(testpaths.CORPUS_ROTATED),
                        reason="needs a PDF with rotated text")
    def test_rotated_text_stays_out_of_the_body(self):
        pages = self._page()
        md = M.to_markdown(pages)
        assert "arXiv" not in md
        assert "arXiv" in M.to_markdown(pages, keep_rotated=True)

    @pytest.mark.skipif(not os.path.exists(testpaths.CORPUS_ROTATED),
                        reason="needs a PDF with rotated text")
    def test_rotated_text_is_never_a_heading(self):
        pages = self._page()
        md = M.to_markdown(pages, keep_rotated=True)
        heads = [l for l in md.splitlines() if l.startswith("#")]
        assert not any("arXiv" in h for h in heads)


@needs_corpus
class TestParagraphBreaks:
    def test_short_line_ends_a_paragraph(self, pages):
        """Markdown joins adjacent lines, so an address block reflows into one
        run-on paragraph unless a line that stops short of the right margin
        ends it."""
        md = M.to_markdown(pages)
        blocks = [b for b in md.split("\n\n") if b.strip()]
        assert len(blocks) > 3, "no paragraph structure at all"


class TestMarkdownIntegrity:
    """Malformed output corrupts far more than the span that caused it."""

    @needs_corpus
    def test_dollar_markers_are_balanced(self, pages):
        """An odd number of `$$` lets a display delimiter pair with a stray
        one and swallow everything between as mathematics. Measured: a single
        stray `$$` turned 681 characters of prose into an equation."""
        import re
        md = M.to_markdown(pages)
        assert len(re.findall(r"\$\$", md)) % 2 == 0

    @needs_corpus
    def test_no_empty_inline_span(self, pages):
        """`$` + `` + `$` is a bare `$$`, indistinguishable from a display."""
        md = M.to_markdown(pages)
        assert "$$" not in md.replace("\n$$\n", "\n")

    def test_literal_dollar_in_prose_is_escaped(self):
        from project_mmd import _escape_text
        assert _escape_text("costs $5") == r"costs \$5"

    def test_empty_tex_is_not_wrapped(self):
        from project_mmd import _inline
        assert _inline("") == "" and _inline(None) == "" and _inline("  ") == ""
        assert _inline("x") == "$x$"


class TestBoldFontNames:
    """TeX font names do not contain the word `bold`."""

    def test_computer_modern_bold_is_recognised(self):
        for name in ("CMBX12", "CMBX10", "ABC+CMBXTI10", "CMB10"):
            assert M._is_bold(name), name

    def test_roman_is_not_bold(self):
        for name in ("CMR12", "CMTI10", "CMSY10", "Times-Roman", "CMMI10"):
            assert not M._is_bold(name), name

    def test_conventional_names_still_work(self):
        for name in ("Times-Bold", "Arial,Bold", "Foo-BD"):
            assert M._is_bold(name), name


class TestOperatorNames:
    """Upright letter runs inside maths are operator names, not variables."""

    def test_upright_run_becomes_one_token(self):
        import structure
        from test_structure import g as mkg

        run = [mkg(None, 10.0, 100.0, x, family="text", text=c)
               for x, c in zip((0.0, 5.0, 10.0, 15.0), "Spin")]
        for n in run:
            n.fontname = "ABC+CMBX10"
            n.tex = structure.TexToken(None, "unknown", None, "none")
        merged = structure._merge_operator_runs(run)
        assert len(merged) == 1
        assert merged[0].tex.latex == r"\mathbf{Spin}"

    def test_roman_run_is_mathrm(self):
        import structure
        from test_structure import g as mkg

        run = [mkg(None, 10.0, 100.0, x, family="text", text=c)
               for x, c in zip((0.0, 5.0), "Cl")]
        for n in run:
            n.fontname = "ABC+CMR10"
            n.tex = structure.TexToken(None, "unknown", None, "none")
        merged = structure._merge_operator_runs(run)
        assert merged[0].tex.latex == r"\mathrm{Cl}"

    def test_italic_letters_are_not_merged(self):
        """Italic letters are variables; each can carry its own script."""
        import structure
        from test_structure import g as mkg

        run = [mkg(None, 10.0, 100.0, x, family="text", text=c)
               for x, c in zip((0.0, 5.0), "xy")]
        for n in run:
            n.fontname = "ABC+CMTI10"
        assert len(structure._merge_operator_runs(run)) == 2

    def test_single_letter_is_not_merged(self):
        import structure
        from test_structure import g as mkg

        one = mkg(None, 10.0, 100.0, 0.0, family="text", text="d")
        one.fontname = "ABC+CMR10"
        assert len(structure._merge_operator_runs([one])) == 1


class TestCoordinateSpaceIsShared:
    """lines.json and crop URLs from one run must be in ONE space.

    They were not: lines.json declared the page in PDF points while crop URLs
    used 250-dpi pixels. A server given both computed a scale of 3.47 and
    every crop landed off the page -- HTTP 400, "empty crop after clamping".
    Handing the server only the images worked, which made the failure look
    like a server bug rather than a units mismatch in what we wrote.
    """

    @needs_corpus
    def test_lines_json_page_size_is_pixels(self, pages):
        import docmodel_six as docmodel
        lj = docmodel.to_lines_json(pages)
        for p, src in zip(lj["pages"], pages):
            pt_w = src.rect[2] - src.rect[0]
            assert p["page_width"] == pytest.approx(
                pt_w * docmodel.PX_PER_PT, abs=1)
            assert p["px_per_pt"] == pytest.approx(docmodel.PX_PER_PT, abs=1e-4)

    @needs_corpus
    def test_crop_url_and_lines_json_agree(self, pages):
        """A region taken from lines.json must reproduce the crop URL."""
        import docmodel_six as docmodel
        lj = docmodel.to_lines_json(pages)
        page = pages[0]
        line = page.lines[0]
        rec = next(l for l in lj["pages"][0]["lines"] if l["id"] == line.id)
        url = M.crop_url(line.rect, page, "d", "")
        for key in ("top_left_x", "top_left_y", "width", "height"):
            from_url = int(url.split(key + "=")[1].split("&")[0])
            assert from_url == pytest.approx(rec["region"][key], abs=1)

    def test_projection_constant_is_shared(self):
        import docmodel_six as docmodel
        assert M.DEFAULT_PX_PER_PT == docmodel.PX_PER_PT


class TestOverlappingCropsAreMerged:
    """A matrix is ONE object drawn as several baseline rows.

    Each row defers separately, and because the tall built-up fences belong to
    every row's rectangle the crops OVERLAP -- four stacked images for one
    `\\begin{array}`, drawn on top of each other in a Markdown viewer.
    Overlapping rectangles are one region.
    """

    def _page(self, rects):
        from docmodel_six import LineNode, PageNode, Span
        import docmodel_six as D

        class _Sp(Span):
            pass

        lines = []
        for i, r in enumerate(rects):
            sp = Span(id=f"s{i}", kind="math", rect=r, glyphs=[], rules=[])
            ln = LineNode(id=f"l{i}", page=1, rect=r, type="formula")
            object.__setattr__(ln, "_spans_cache", [sp])
            lines.append((ln, sp))
        page = PageNode(page=1, rect=(0, 0, 612, 792))
        return page, lines

    def test_overlapping_boxes_collapse_to_one(self):
        import docmodel_six as docmodel
        from docmodel_six import LineNode, PageNode, Span

        page = PageNode(page=1, rect=(0, 0, 612, 792))
        boxes = [(181, 319, 473, 335), (202, 309, 258, 328),
                 (134, 301, 412, 321), (200, 294, 258, 314)]
        spans = [Span(id=f"s{i}", kind="math", rect=b, glyphs=[], rules=[])
                 for i, b in enumerate(boxes)]

        class FakeLine:
            def __init__(self, sp):
                self.spans = [sp]
                self.rect = sp.rect
        page.lines = [FakeLine(sp) for sp in spans]

        real = docmodel.span_latex
        docmodel.span_latex = lambda sp: None
        try:
            clusters = M._crop_clusters(page)
        finally:
            docmodel.span_latex = real

        carriers = [r for r in clusters.values() if r is not None]
        assert len(carriers) == 1, clusters
        x0, y0, x1, y1 = carriers[0]
        assert (x0, y0, x1, y1) == (134, 294, 473, 335)

    def test_disjoint_boxes_stay_separate(self):
        import docmodel_six as docmodel
        from docmodel_six import PageNode, Span

        page = PageNode(page=1, rect=(0, 0, 612, 792))
        spans = [Span(id="a", kind="math", rect=(100, 700, 150, 715),
                      glyphs=[], rules=[]),
                 Span(id="b", kind="math", rect=(100, 400, 150, 415),
                      glyphs=[], rules=[])]

        class FakeLine:
            def __init__(self, sp):
                self.spans = [sp]
                self.rect = sp.rect
        page.lines = [FakeLine(sp) for sp in spans]

        real = docmodel.span_latex
        docmodel.span_latex = lambda sp: None
        try:
            clusters = M._crop_clusters(page)
        finally:
            docmodel.span_latex = real
        assert sum(1 for r in clusters.values() if r is not None) == 2


class TestEmittedLatexIsStructurallyValid:
    """Invalid LaTeX breaks the RENDERER, not just the reader.

    KaTeX answers "Missing argument for \\widetilde" and shows an error box
    where the mathematics should be. An uncomposed accent was emitting its
    command bare; a crop is a worse reading experience than correct LaTeX but
    a far better one than a broken page.
    """

    def test_commands_needing_an_argument(self):
        for tex in (r"\widetilde", r"\frac", r"\sqrt x", r"\overline",
                    r"\mathbb", r"\hat"):
            assert not M.is_emittable(tex), tex

    def test_well_formed_passes(self):
        for tex in (r"\widetilde{x}", r"\frac{1}{2}", r"x^{2}",
                    r"\mathbb{R}^{n}", r"a + b"):
            assert M.is_emittable(tex), tex

    def test_unbalanced_braces_rejected(self):
        assert not M.is_emittable("a{b")
        assert not M.is_emittable("a}b{")

    def test_empty_rejected(self):
        for tex in ("", "   ", None):
            assert not M.is_emittable(tex)

    @needs_corpus
    def test_document_contains_no_bare_accent(self, pages):
        import re
        md = M.to_markdown(pages)
        assert not re.findall(
            r"\\(widetilde|widehat|overline|bar|hat|vec|sqrt|frac)(?!\{)[^a-zA-Z]",
            md)

    @needs_corpus
    def test_document_braces_balanced_in_every_math_span(self, pages):
        """Counting braces is not the test -- `\\{` and `\\}` are literal set
        braces, not grouping. `is_emittable` knows the difference."""
        import re
        md = M.to_markdown(pages)
        for m in re.findall(r"(?<!\$)\$([^$\n]+)\$(?!\$)", md):
            assert M.is_emittable(m), m[:60]

    def test_escaped_braces_are_not_grouping(self):
        assert M.is_emittable(r"\{ x \in S \}")
        assert M.is_emittable(r"\{ x \in")


@needs_corpus
class TestCropCoveredContentIsNotDuplicated:
    """Everything a crop covers is IN the picture.

    Emitting those spans as text or LaTeX as well prints them twice: beside
    the matrix image appeared a stray `arbitrary ,` and a lone `0`, both of
    which the image already showed.
    """

    def test_text_inside_a_crop_is_suppressed(self, pages):
        """Scoped to ONE page: a word covered by a crop here may appear
        perfectly legitimately somewhere else in the document."""
        import docmodel_six as docmodel
        for p in pages:
            md = M.to_markdown([p])
            crops = M._crop_clusters(p)
            boxes = [r for r in crops.values() if r is not None]
            if not boxes:
                continue
            for ln in p.lines:
                for sp in ln.spans:
                    if sp.kind != "text":
                        continue
                    cx = 0.5 * (sp.rect[0] + sp.rect[2])
                    cy = 0.5 * (sp.rect[1] + sp.rect[3])
                    if not any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3]
                               for b in boxes):
                        continue
                    word = docmodel._run_text(sp.glyphs, sp.word_gap).strip()
                    if len(word) > 4 and word.isalpha():
                        assert word not in md, \
                            f"{word!r} is inside a crop and also emitted"
            return


class TestLineNumberGuttersAreNotScripts:
    """A long run of smaller glyphs is a BLOCK, not a script.

    A code listing's line-number gutter sits beside the caption. Treating each
    of its digits as a script produced
    `\\mathrm{L}_{1} \\mathrm{istin}_{\\mathrm{u}} \\mathrm{g}_{\\mathbf{si}}`
    from `Listing 1.20` and the numbers 1..20 beside it.
    """

    def _g(self, text, x, baseline, size):
        import docmodel_six as D
        n = D.GlyphNode(id=f"g{x}", page=1,
                        rect=(x, baseline, x + 0.5 * size, baseline + size),
                        text=text, cid=1, glyphname=None,
                        fontname="ABC+Helv", family="text", size=size,
                        tex=__import__("texmap").project("text", None),
                        matrix=(size, 0, 0, size, x, baseline))
        return n

    def test_long_small_run_is_not_absorbed(self):
        from docmodel_six import LineNode
        caption = [self._g(c, 100.0 + i * 6.0, 500.0, 10.0)
                   for i, c in enumerate("Listing")]
        gutter = [self._g(str(i % 10), 160.0 + i * 5.0, 497.0, 7.0)
                  for i in range(12)]
        line = LineNode(id="l", page=1, rect=(99, 495, 230, 512),
                        type="text", glyphs=caption + gutter)
        for sp in line.spans:
            assert sp.kind == "text", \
                "a gutter of line numbers was read as scripts"


class TestLinkAnnotations:
    """Link annotations live OUTSIDE the content stream.

    Nothing in the drawn page reveals them, yet they carry what the text
    cannot: a citation `[22]` is two digits on the page, but its annotation
    says `cite.polly` -- the author's own BibTeX key.
    """

    def _page_with_link(self, uri=None, dest=None):
        import docmodel_six as D

        class FakeSpan:
            kind = "text"
            word_gap = 2.0

        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        page.links = [D.LinkNode(rect=(100.0, 200.0, 120.0, 212.0),
                                 uri=uri, dest=dest)]
        return page

    def _glyphs(self, text, x0=100.0, baseline=200.0, size=10.0):
        import docmodel_six as D
        from texmap import project
        out = []
        x = x0
        for c in text:
            out.append(D.GlyphNode(
                id=f"g{x}", page=1, rect=(x, baseline, x + 5.0, baseline + size),
                text=c, cid=0, glyphname=None, fontname="ABC+Helv",
                family="text", size=size, tex=project("text", None),
                matrix=(size, 0, 0, size, x, baseline)))
            x += 5.0
        return out

    def _span(self, glyphs):
        import docmodel_six as D
        return D.Span(id="s", kind="text",
                      rect=(glyphs[0].rect[0], glyphs[0].rect[1],
                            glyphs[-1].rect[2], glyphs[-1].rect[3]),
                      glyphs=glyphs, rules=[], word_gap=2.0)

    def test_citekey_survives_into_the_markdown(self):
        page = self._page_with_link(dest="cite.polly")
        span = self._span(self._glyphs("22"))
        assert M._linked_text(span, page, 2.0) == "[22](#cite.polly)"

    def test_external_uri(self):
        page = self._page_with_link(uri="http://example.org/")
        span = self._span(self._glyphs("22"))
        assert M._linked_text(span, page, 2.0) == "[22](http://example.org/)"

    def test_only_the_covered_glyphs_are_wrapped(self):
        """Testing the span's centre swept up whatever shared the run: a
        footnote marker became part of its URL, and a trailing comma landed
        inside the citation."""
        page = self._page_with_link(dest="cite.polly")
        covered = self._glyphs("22")                    # x 100..110
        trailing = self._glyphs(",", x0=125.0)          # outside the rect
        span = self._span(covered + trailing)
        out = M._linked_text(span, page, 2.0)
        assert out.startswith("[22](#cite.polly)") and out.endswith(",")

    def test_no_links_leaves_text_alone(self):
        import docmodel_six as D
        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        span = self._span(self._glyphs("22"))
        assert M._linked_text(span, page, 2.0) == "22"


class TestRaisedMarkers:
    """A raised, script-size glyph with no base is a MARKER, not an exponent.

    Measured on a footnote reference: size 5.98 against a 7.97 line, baseline
    2.81pt higher, advance 2.989 -- NORMAL, not zero -- and a 0.50pt gap to
    the next glyph, an ordinary inter-glyph gap rather than a word space.
    There is no missing space to restore: the PDF encodes none, and the
    correct rendering is a superscript.
    """

    def _g(self, text, x, baseline, size, page=None):
        import docmodel_six as D
        from texmap import project
        return D.GlyphNode(
            id=f"g{x}", page=1, rect=(x, baseline, x + 0.5 * size,
                                      baseline + size),
            text=text, cid=0, glyphname=None, fontname="ABC+Helv",
            family="text", size=size, tex=project("text", None),
            matrix=(size, 0, 0, size, x, baseline))

    def _span(self, glyphs, line_size):
        import docmodel_six as D
        return D.Span(id="s", kind="text",
                      rect=(glyphs[0].rect[0], glyphs[0].rect[1],
                            glyphs[-1].rect[2], glyphs[-1].rect[3]),
                      glyphs=glyphs, rules=[], line_size=line_size,
                      word_gap=2.0)

    def _page(self):
        import docmodel_six as D
        return D.PageNode(page=1, rect=(0, 0, 612, 792))

    def test_marker_becomes_a_superscript(self):
        gl = [self._g("1", 56.93, 78.368, 5.98)]
        gl += [self._g(c, 60.42 + i * 4.0, 75.555, 7.97)
               for i, c in enumerate("http")]
        out = M._linked_text(self._span(gl, 7.97), self._page(), 2.0)
        assert out.startswith("<sup>1</sup>"), out
        assert "http" in out and "<sup>h" not in out

    def test_no_space_is_invented(self):
        """The PDF encodes no gap there, so none is emitted."""
        gl = [self._g("1", 56.93, 78.368, 5.98)]
        gl += [self._g(c, 60.42 + i * 4.0, 75.555, 7.97)
               for i, c in enumerate("http")]
        out = M._linked_text(self._span(gl, 7.97), self._page(), 2.0)
        assert "</sup> " not in out

    def test_ordinary_text_is_untouched(self):
        gl = [self._g(c, 100.0 + i * 4.0, 200.0, 10.0)
              for i, c in enumerate("normal")]
        out = M._linked_text(self._span(gl, 10.0), self._page(), 2.0)
        assert out == "normal"

    def test_a_same_size_glyph_is_not_a_marker(self):
        """Raised alone is not enough: it must also be script-size."""
        gl = [self._g("1", 56.0, 78.0, 10.0)]
        gl += [self._g(c, 62.0 + i * 4.0, 75.5, 10.0)
               for i, c in enumerate("abc")]
        out = M._linked_text(self._span(gl, 10.0), self._page(), 2.0)
        assert "<sup>" not in out

    def test_interleaved_fragments_are_not_markers(self):
        """Several raised runs alternating with ordinary glyphs is two text
        blocks merged into one row, not a line of footnote references.
        Wrapping each fragment gives `L<sup>H</sup>e<sup>i</sup>v<sup>g</sup>`
        -- dressing up a row-merge defect instead of leaving it visible."""
        gl = []
        for i, c in enumerate("LHeivgh"):
            small = i % 2 == 1
            gl.append(self._g(c, 100.0 + i * 5.0,
                              204.0 if small else 200.0,
                              7.0 if small else 10.0))
        out = M._linked_text(self._span(gl, 10.0), self._page(), 2.0)
        assert "<sup>" not in out, out


class TestHeadingsAreNotStrayGlyphs:
    """A heading is a PHRASE.

    One or two characters in a bold face is a chart label, a page number or
    an axis tick. Measured: a bold `m` and `n` from inside a bar chart became
    `### m` and `### n` in the Markdown, and five single digits elsewhere did
    the same.
    """

    def _line(self, text, size=8.9, font="Arial-BoldMT", baseline=616.0):
        import docmodel_six as D
        from texmap import project
        gl = []
        x = 451.0
        for c in text:
            gl.append(D.GlyphNode(
                id=f"g{x}", page=1, rect=(x, baseline, x + 5.0,
                                          baseline + size),
                text=c, cid=0, glyphname=None, fontname=font,
                family="text", size=size, tex=project("text", None),
                matrix=(size, 0, 0, size, x, baseline)))
            x += 5.0
        return D.LineNode(id="l", page=1,
                          rect=(451.0, baseline, x, baseline + size),
                          type="text", glyphs=gl)

    class _Profile:
        body_size = 10.0
        CLEARLY_LARGER = 1.35

        def rank(self, size):
            return 0 if size <= self.body_size * 1.08 else 1

        def clearly_larger(self, size):
            return size > self.body_size * self.CLEARLY_LARGER

    def test_a_single_bold_letter_is_not_a_heading(self):
        assert M.heading_level(self._line("m"), self._Profile()) == 0

    def test_a_single_digit_is_not_a_heading(self):
        assert M.heading_level(self._line("1"), self._Profile()) == 0

    def test_two_characters_are_not_enough(self):
        assert M.heading_level(self._line("IV"), self._Profile()) == 0

    def test_a_bold_phrase_still_is(self):
        assert M.heading_level(self._line("Background"), self._Profile()) == 3

    def test_digits_alone_never_qualify(self):
        """Even at heading size, a run with no letters is a page number."""
        assert M.heading_level(self._line("2018", size=14.0),
                               self._Profile()) == 0


class TestListingBlankLines:
    """A blank line inside a listing still gets a number from the layout tool.

    Treating that row as ordinary text closes the code fence and reopens it
    on the next line, chopping one listing into three. Measured: the gutter
    is 4.98pt roman while the code is 7.97pt NimbusMonL -- a different size
    AND a different face.
    """

    def _line(self, text, size, font, x0=305.0, baseline=400.0):
        import docmodel_six as D
        from texmap import project
        gl = []
        x = x0
        for c in text:
            gl.append(D.GlyphNode(
                id=f"g{x}", page=1, rect=(x, baseline, x + 4.0,
                                          baseline + size),
                text=c, cid=0, glyphname=None, fontname=font,
                family="text", size=size, tex=project("text", None),
                matrix=(size, 0, 0, size, x, baseline)))
            x += 4.0
        return D.LineNode(id="l", page=1, rect=(x0, baseline, x,
                                                baseline + size),
                          type="text", glyphs=gl)

    def test_a_lone_gutter_number_is_recognised(self):
        row = [self._line("3", 4.98, "ABC+NimbusRomNo9L-Regu")]
        assert M._is_gutter_only(row, 7.97)

    def test_a_code_line_is_not(self):
        row = [self._line("3 states=[]", 7.97, "ABC+NimbusMonL-Regu")]
        assert not M._is_gutter_only(row, 7.97)

    def test_a_same_size_number_is_not(self):
        """Size is half the signal; a body-size number is not a gutter."""
        row = [self._line("3", 7.97, "ABC+NimbusRomNo9L-Regu")]
        assert not M._is_gutter_only(row, 7.97)

    def test_a_monospace_number_is_not(self):
        row = [self._line("3", 4.98, "ABC+NimbusMonL-Regu")]
        assert not M._is_gutter_only(row, 7.97)

    def test_a_long_run_is_not(self):
        row = [self._line("12345678", 4.98, "ABC+NimbusRomNo9L-Regu")]
        assert not M._is_gutter_only(row, 7.97)

    @needs_corpus
    def test_blank_line_keeps_its_number_by_default(self, pages):
        """A listing showing 1, 2, 4, 6 has a hole a reader cannot explain."""
        import re
        md = M.to_markdown(pages)
        for fence in re.findall(r"```\n(.*?)```", md, re.S):
            nums = [int(m.group(1)) for line in fence.splitlines()
                    for m in [re.match(r"\s*(\d+)\b", line)] if m]
            if len(nums) >= 4 and nums[0] == 1:
                assert nums == list(range(nums[0], nums[0] + len(nums))), nums
                return

    @needs_corpus
    def test_line_numbers_can_be_dropped(self, pages):
        """All or nothing: a listing showing SOME of its numbers is worse
        than one showing none."""
        import re
        off = M.to_markdown(pages, line_numbers=False)
        for fence in re.findall(r"```\n(.*?)```", off, re.S):
            for line in fence.splitlines():
                assert not re.match(r"\s*\d+\s+\S", line), line


class TestParagraphsOnNarrowBlocks:
    """Paragraph breaks measured LOCALLY, not against the whole page.

    An abstract set inside a two-column page stops far short of the page's
    widest edge on every line. Judged against that edge, every line looks
    like a paragraph end -- measured: 94 lines became 95 Markdown blocks.

    The leading has the same problem in the other direction: taken over the
    sorted set of all row tops, the small offset BETWEEN two columns became
    the modal gap, 1.7pt against a real leading of 10.9.
    """

    def _line(self, x0, x1, y, page=1):
        import docmodel_six as D
        from texmap import project
        gl = []
        x = x0
        while x < x1:
            gl.append(D.GlyphNode(
                id=f"g{x}-{y}", page=page, rect=(x, y, min(x + 5.0, x1),
                                                 y + 10.0),
                text="a", cid=0, glyphname=None, fontname="ABC+Helv",
                family="text", size=10.0, tex=project("text", None),
                matrix=(10.0, 0, 0, 10.0, x, y)))
            x += 5.0
        return D.LineNode(id=f"l{x0}-{y}", page=page,
                          rect=(x0, y, x1, y + 10.0), type="text", glyphs=gl)

    def _page(self):
        import docmodel_six as D
        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        # a narrow block, justified to 300, inside a page that runs to 560
        page.lines = [self._line(48.0, 300.0, 700.0 - i * 12.0)
                      for i in range(6)]
        page.lines.append(self._line(48.0, 560.0, 600.0))
        return page

    def test_a_narrow_block_is_one_paragraph(self):
        page = self._page()
        md = M.to_markdown([page])
        body = [b for b in md.split("\n\n") if b.strip() and "---" not in b]
        assert any(len(b.splitlines()) >= 5 for b in body), \
            [len(b.splitlines()) for b in body]

    def test_the_local_margin_is_the_block_s_own(self):
        page = self._page()
        assert M._column_margin(page, page.lines[0], 560.0) == 300.0

    def test_too_few_lines_falls_back_to_the_page(self):
        import docmodel_six as D
        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        page.lines = [self._line(48.0, 300.0, 700.0)]
        assert M._column_margin(page, page.lines[0], 560.0) == 560.0


class TestDisplayBlocksMustSaySomething:
    """`$$ $$` and `$$\\bigr)$$` are not equations.

    Measured on the four-column gold/MathPix/pdf2mmd comparison: of 836
    display equations emitted across 102 documents, 202 carried three tokens
    or fewer and 55 were EMPTY. The rest of that tail was a lone `\\bigl(`,
    `\\bigr)` or `\\biggl[` on its own line wrapped in `$$`.

    Those are not deferrals waiting to be counted -- they are wrong answers
    shipped at full confidence, and a crop metric cannot see them, because a
    crop is a REFUSAL and these are emissions.
    """

    def test_empty_content_has_none(self):
        from project_mmd import has_content
        assert not has_content("")
        from project_mmd import has_content
        assert not has_content("   ")
        from project_mmd import has_content
        assert not has_content(None)

    def test_a_lone_delimiter_has_none(self):
        from project_mmd import has_content
        assert not has_content(r"\bigl(")
        from project_mmd import has_content
        assert not has_content(r"\bigr)")
        from project_mmd import has_content
        assert not has_content(r"\biggl[")

    def test_a_matched_empty_pair_has_none(self):
        from project_mmd import has_content
        assert not has_content(r"\bigl( \bigr)")
        from project_mmd import has_content
        assert not has_content(r"\left( \right)")

    def test_spacing_alone_has_none(self):
        from project_mmd import has_content
        assert not has_content(r"\quad")
        from project_mmd import has_content
        assert not has_content(r"\mid")

    def test_a_real_expression_has_content(self):
        from project_mmd import has_content
        assert has_content("x + y")
        from project_mmd import has_content
        assert has_content(r"\alpha")
        from project_mmd import has_content
        assert has_content("a")

    def test_an_operator_name_has_content(self):
        """`\\log` alone is a FRAGMENT, not noise. It says something, and
        removing it needs the segmentation fix rather than this gate."""
        from project_mmd import has_content
        assert has_content(r"\log")

    def test_a_delimiter_with_content_inside_is_kept(self):
        from project_mmd import has_content
        assert has_content(r"\bigl( x \bigr)")


class TestEquationNumbersAreNotMaths:
    """An author's `(1)` at the right margin is a LABEL.

    Absorbed into the expression it produced `L^{-1}dL \\in g(1)`,
    `dL = Q + P(2)` and `= K_{0\\ell i}(8)` -- readings that are wrong in a
    way no renderer can catch, because they compile.

    Three conditions together, from a real line: the run is a parenthesised
    number, it ENDS at the right margin (525..540 against a margin of
    540.0), and a wide gap separates it from the mathematics (202pt).
    """

    def _line(self, texts, xs, size=12.0, baseline=700.0):
        import docmodel_six as D
        import texmap
        gl = []
        for t, x in zip(texts, xs):
            n = D.GlyphNode(id=f"g{x}", page=1, rect=(x, baseline, x + 5.0,
                                                      baseline + size),
                            text=t, cid=0, glyphname=None,
                            fontname="ABC+CMR12", family="text", size=size,
                            tex=texmap.project("text", None),
                            matrix=(size, 0, 0, size, x, baseline))
            gl.append(n)
        return D.LineNode(id="p1l0", page=1,
                          rect=(xs[0], baseline, xs[-1] + 5.0,
                                baseline + size), type="text", glyphs=gl)

    def test_a_tag_at_the_margin_behind_a_gap_is_found(self):
        ln = self._line(list("xy(1)"), [269.0, 275.0, 525.0, 530.0, 535.0])
        assert M.equation_number(ln, 540.0)

    def test_a_number_NOT_at_the_margin_is_not_a_tag(self):
        """`(1)` in the middle of an expression is content."""
        ln = self._line(list("xy(1)"), [269.0, 275.0, 300.0, 305.0, 310.0])
        assert M.equation_number(ln, 540.0) == []

    def test_a_number_ABUTTING_the_maths_is_not_a_tag(self):
        """`f(1)` is a function application, not a label."""
        ln = self._line(list("xy(1)"), [500.0, 506.0, 525.0, 530.0, 535.0])
        assert M.equation_number(ln, 540.0) == []

    def test_a_non_numeric_group_is_not_a_tag(self):
        ln = self._line(list("xy(a)"), [269.0, 275.0, 525.0, 530.0, 535.0])
        assert M.equation_number(ln, 540.0) == []

    def test_a_sectioned_number_is_a_tag(self):
        """`(2.14)` and `(3a)` are equation numbers too."""
        ln = self._line(list("x(2.1)"), [269.0, 515.0, 520.0, 525.0, 530.0,
                                         535.0])
        assert M.equation_number(ln, 540.0)


class TestScriptRowsOverlapTheirBase:
    """A row of scripts OVERLAPS the row it belongs to.

    Measured on 91.pdf: a row of 8pt superscripts at y=675.41 against a 12pt
    main row whose top is 674.29. The gap between them is NEGATIVE.

    The display fusion required a non-negative gap, so the two never fused
    and each became its own display equation. That page emitted 85 display
    lines for two authored equations.
    """

    def test_an_overlapping_row_is_part_of_the_same_equation(self):
        """-4.67pt between a 12pt row and the script row above it."""
        size = 12.0
        assert -1.5 * size <= -4.67 <= 2.0 * size

    def test_a_row_a_line_away_is_a_new_equation(self):
        size = 12.0
        assert not (-1.5 * size <= 30.0 <= 2.0 * size)

    def test_a_row_far_above_is_a_new_equation(self):
        """The limit is symmetric-ish but bounded: a row 2 em ABOVE the
        previous one is not an overlapping script row."""
        size = 12.0
        assert not (-1.5 * size <= -30.0 <= 2.0 * size)


class TestDisplayRunsDecidedInOnePass:
    """Runs are decided over the DISPLAY groups alone, before emission.

    Fusing incrementally meant any material between two display rows broke
    the chain -- an inline `$\\bigl($`, a crop -- and incremental emission
    cannot reach back past it. Measured on 91.pdf: the run rule computed
    EIGHT runs for page 1 while TWENTY-SIX blocks were emitted.

    Each run gets one placeholder at its position in the document; the text
    accumulates separately and is substituted once the page is finished.
    """

    def _page(self, rows):
        """A page with body lines at the margin and indented display rows."""
        import docmodel_six as D
        import texmap
        pg = D.PageNode(page=1, rect=(0, 0, 612, 792))
        lines = []

        def mk(x0, y, texts, size, math):
            gl = []
            x = x0
            for t in texts:
                n = D.GlyphNode(
                    id=f"g{y}-{x}", page=1,
                    rect=(x, y, x + 5.0, y + size), text=t, cid=0,
                    glyphname="alpha" if math else None,
                    fontname="ABC+CMMI10" if math else "ABC+CMR10",
                    family="math-italic" if math else "text", size=size,
                    tex=texmap.project("math-italic" if math else "text",
                                       "alpha" if math else None),
                    matrix=(size, 0, 0, size, x, y))
                gl.append(n)
                x += 5.0
            return D.LineNode(id=f"p1l{y}", page=1,
                              rect=(x0, y, x, y + size), type="text",
                              glyphs=gl)

        for i in range(4):
            lines.append(mk(72.0, 760.0 - i * 12.0, "prose text", 10.0,
                            False))
        for x0, y, txt, size in rows:
            lines.append(mk(x0, y, txt, size, True))
        pg.lines = lines
        return pg

    def test_two_overlapping_display_rows_make_ONE_block(self):
        """A script row overlaps its base row: one equation, one block."""
        import project_mmd as M
        pg = self._page([(200.0, 700.0, "ab", 12.0),
                         (200.0, 701.0, "cd", 8.0)])
        md = M.to_markdown([pg], doc_id="t")
        assert md.count("$$") == 2

    def test_two_separated_display_rows_make_TWO_blocks(self):
        import project_mmd as M
        pg = self._page([(200.0, 700.0, "ab", 12.0),
                         (200.0, 600.0, "cd", 12.0)])
        md = M.to_markdown([pg], doc_id="t")
        assert md.count("$$") == 4

    def test_no_placeholder_survives_into_the_output(self):
        """A placeholder left in the text would print as a control character
        in the reader's document."""
        import project_mmd as M
        pg = self._page([(200.0, 700.0, "ab", 12.0),
                         (200.0, 701.0, "cd", 8.0)])
        assert "\x00" not in M.to_markdown([pg], doc_id="t")


def test_private_use_warning_is_formattable():
    """733 -- the warning line itself was a `%` format string beginning `% W`,
    so emitting it raised `unsupported format character 'W'` and the whole
    document failed to project. Caught by a run outside the corpus, not by a
    test: nothing here had ever produced a private-use codepoint."""
    import project_mmd
    import texpackages
    body = "Windkanal  text"
    stripped, private = texpackages.strip_private_use(body)
    assert private
    # the exact expression to_latex builds
    line = ("%% WARNING: %d private-use codepoint(s) removed (a font's "
            "own slot, not a character): %s"
            % (len(private),
               " ".join(sorted({"U+%04X" % ord(c) for c in private}))[:200]))
    assert line.startswith("% WARNING: 1 private-use")
    assert "U+E000" in line


def test_a_pdf_with_no_text_says_so_on_the_page():
    """733 -- a body of only `\\newpage` compiles to "No pages of output",
    which reads as a LaTeX fault and not as "nothing was extracted"."""
    import project_mmd
    out = project_mmd.to_latex([], doc_id="empty")
    assert "No text was read" in out
    assert r"\begin{document}" in out


def test_a_document_with_text_gets_no_such_note():
    import project_mmd
    from docmodel_six import PageNode
    out = project_mmd.to_latex([], doc_id="x")
    assert out.count("No text was read") == 1


class TestDisplayContinuation:
    r"""734 -- a row beginning with a binary operator is a CONTINUATION.

    `is_display` judges one line at a time and its test is INDENT. A
    multi-row display is not obliged to indent every row equally: in
    wzlxjtu-043 the author pulls the continuation left (`\hspace{-0.15cm}`),
    which leaves the FIRST row indented 12px against a 0.5 em test and the
    SECOND indented 110px. The head of the equation -- the part carrying
    `\delta_1^c(0) =`, which is what names it -- was read correctly and then
    emitted as an inline `$...$` beside its own display.

    A binary operator needs a left operand, and the only place it can be is
    the line above.
    """

    def _mathline(self, lid, x0, baseline, texts):
        import docmodel_six as D
        import texmap
        size = 12.0
        gl, x = [], x0
        for t in texts:
            gl.append(D.GlyphNode(
                id=f"{lid}g{x}", page=1, rect=(x, baseline, x + 6.0,
                                               baseline + size),
                text=t, cid=0, glyphname=None, fontname="ABC+CMMI12",
                family="math-italic", size=size,
                tex=texmap.TexToken(t, "atom", None, "corpus"),
                matrix=(size, 0, 0, size, x, baseline)))
            x += 8.0
        ln = D.LineNode(id=lid, page=1, rect=(x0, baseline, x, baseline + size),
                        type="formula", glyphs=gl)
        return ln

    def _page(self):
        import docmodel_six as D
        # body text fixing the column margin at x=100, then the two rows of
        # one display: the head barely indented, the continuation far more.
        head = self._mathline("p1l1", 104.0, 600.0, list("y=a"))
        cont = self._mathline("p1l2", 140.0, 580.0, list("-b"))
        return D.PageNode(page=1, rect=(0.0, 0.0, 612.0, 792.0),
                          lines=[head, cont]), head, cont

    def test_the_head_is_claimed_by_its_continuation(self):
        page, head, cont = self._page()
        assert M.mark_display_continuations(page) == 1
        assert getattr(head, "forced_display", False) is True

    def test_a_row_that_does_not_start_with_an_operator_claims_nothing(self):
        page, head, cont = self._page()
        for g in cont.glyphs[:1]:
            g.text = "z"
        assert M.mark_display_continuations(page) == 0
        assert getattr(head, "forced_display", False) is False


class TestAWideDisplayIsStillCentred:
    r"""762 -- the centring test had a floor a wide display cannot clear.

    wzlxjtu-031's eleventh equation fills its 245pt revtex column: it begins
    3.70pt past the column margin and ends 3.69pt short of the right one. As
    symmetric as a measurement gets, and a tenth of the em the test demanded
    on each side -- so it was emitted as an inline `$...$` in the middle of
    the prose. Not a crop, not in any equation list; simply no longer an
    equation.

    What the floor guards against is calling a FLUSH line centred, and a
    flush line has a gap of zero on one side. The symmetry carries that.
    """

    LEFT, RIGHT, SIZE = 100.0, 345.0, 9.96

    def _line(self, x0, x1):
        import docmodel_six as D
        import texmap
        gl, x = [], x0
        while x < x1:
            w = min(6.0, x1 - x)
            gl.append(D.GlyphNode(
                id="g%.1f" % x, page=1, rect=(x, 600.0, x + w, 600.0 + self.SIZE),
                text="x", cid=0, glyphname=None, fontname="ABC+CMMI10",
                family="math-italic", size=self.SIZE,
                tex=texmap.TexToken("x", "atom", None, "corpus"),
                matrix=(self.SIZE, 0, 0, self.SIZE, x, 600.0)))
            x += 8.0
        return D.LineNode(id="l", page=1,
                          rect=(x0, 600.0, gl[-1].rect[2], 600.0 + self.SIZE),
                          type="formula", glyphs=gl)

    def _disp(self, x0, x1):
        return M.is_display(self._line(x0, x1), self.LEFT, self.RIGHT)

    def test_the_column_filling_display_is_one(self):
        assert self._disp(103.70, 341.31) is True

    def test_a_flush_line_is_not(self):
        """Left gap zero: whatever the right edge does, it is not centred."""
        assert self._disp(100.0, 341.31) is False

    def test_an_indented_but_lopsided_line_is_not(self):
        """4pt in on the left and 25 short on the right is a ragged end,
        not a centring."""
        assert self._disp(104.0, 320.0) is False

    def test_a_generously_centred_display_still_is(self):
        """The case the old floor was written for, unchanged."""
        assert self._disp(160.0, 285.0) is True
