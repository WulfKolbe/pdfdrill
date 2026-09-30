"""Tests for the two render tiers and the topology measurement behind them.

The separation being tested: 250 dpi images exist to be looked at; anything
topological must come from a 400 dpi (or finer) raster, because glyph
component and hole counts are not stable at 250 dpi.
"""

import json
import pathlib
import os
import shutil
import threading
from http.server import ThreadingHTTPServer
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pytest

import inspectserver
import testpaths

MIELKE = testpaths.CORPUS_PDF
LINES = testpaths.CORPUS_LINES
PAGES_DIR = testpaths.PAGES_DIR
HAVE_GS = shutil.which("gs") is not None


class TestTopologyPrimitive:
    """`dpitopo.topology` must count what inkdrill counts."""

    def test_solid_block(self):
        from dpitopo import topology
        m = np.zeros((20, 20), bool)
        m[5:15, 5:15] = True
        assert topology(m) == (1, 0)

    def test_ring_has_one_hole(self):
        from dpitopo import topology
        m = np.zeros((20, 20), bool)
        m[5:15, 5:15] = True
        m[8:12, 8:12] = False
        assert topology(m) == (1, 1)

    def test_two_rings(self):
        from dpitopo import topology
        m = np.zeros((20, 40), bool)
        for dx in (0, 20):
            m[5:15, 5 + dx:15 + dx] = True
            m[8:12, 8 + dx:12 + dx] = False
        assert topology(m) == (2, 2)

    def test_empty(self):
        from dpitopo import topology
        assert topology(np.zeros((10, 10), bool)) == (0, 0)

    def test_diagonal_touch_is_one_component(self):
        """8-connected foreground, as inkdrill uses (nest: fg conn=8)."""
        from dpitopo import topology
        m = np.zeros((10, 10), bool)
        m[2, 2] = m[3, 3] = True
        assert topology(m)[0] == 1


class TestMathpixIsExactly250dpi:
    @pytest.mark.skipif(not os.path.exists(LINES), reason="needs lines.json")
    def test_every_page_is_250dpi(self):
        """Not a coincidence of one page: constant across the book."""
        from pdfminer.pdfdocument import PDFDocument
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfparser import PDFParser

        with open(LINES, encoding="utf-8") as fh:
            by_page = {p["page"]: p for p in json.load(fh)["pages"]}
        with open(MIELKE, "rb") as fh:
            doc = PDFDocument(PDFParser(fh))
            checked = 0
            for i, pg in enumerate(PDFPage.create_pages(doc), start=1):
                mp = by_page.get(i)
                if not mp:
                    continue
                x0, y0, x1, y1 = pg.mediabox
                dpi_x = mp["page_width"] / abs(x1 - x0) * 72.0
                dpi_y = mp["page_height"] / abs(y1 - y0) * 72.0
                assert 249.5 < dpi_x < 250.5, (i, dpi_x)
                assert 249.5 < dpi_y < 250.5, (i, dpi_y)
                checked += 1
                if checked >= 40:
                    break
        assert checked >= 40


@pytest.mark.skipif(
    not (os.path.isdir(PAGES_DIR) and os.path.exists(MIELKE)
         and os.path.exists(LINES)),
    reason="needs a pages folder, a corpus PDF and its lines.json")
class TestRectRescaling:
    @pytest.fixture(scope="class")
    def pages(self):
        return inspectserver.Pages(PAGES_DIR, [LINES], None, MIELKE, "gs")

    def test_250_space_rect_scales_to_400dpi(self, pages):
        q = {"top_left_x": ["592"], "top_left_y": ["204"],
             "width": ["748"], "height": ["885"]}
        left, top, w, h = pages.rect_at_dpi(25, q, 400)
        assert w == pytest.approx(748 * 1.6, abs=2)
        assert h == pytest.approx(885 * 1.6, abs=2)
        assert left == pytest.approx(592 * 1.6, abs=2)
        assert top == pytest.approx(204 * 1.6, abs=2)

    def test_identity_at_the_source_resolution(self, pages):
        q = {"top_left_x": ["100"], "top_left_y": ["200"],
             "width": ["300"], "height": ["400"]}
        left, top, w, h = pages.rect_at_dpi(25, q, 250)
        assert (left, top, w, h) == pytest.approx((100, 200, 300, 400), abs=2)

    def test_missing_rect_raises(self, pages):
        with pytest.raises(ValueError):
            pages.rect_at_dpi(25, {"width": ["10"]}, 400)


@pytest.mark.skipif(
    not (HAVE_GS and os.path.isdir(PAGES_DIR) and os.path.exists(MIELKE)),
    reason="needs ghostscript, a pages folder and a corpus PDF")
class TestRenderRoute:
    @pytest.fixture(scope="class")
    def server(self):
        inspectserver.Handler.pages = inspectserver.Pages(
            PAGES_DIR, [LINES], None, MIELKE, "gs")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), inspectserver.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()

    def _img(self, url):
        from PIL import Image
        return Image.open(BytesIO(urlopen(url).read()))

    def test_full_page_at_400dpi(self, server):
        im = self._img(server + "/render/p209.png?dpi=400")
        # 439.4 x 666.1 pt at 400 dpi
        assert im.size[0] == pytest.approx(439.4 * 400 / 72, abs=3)
        assert im.size[1] == pytest.approx(666.1 * 400 / 72, abs=3)

    def test_dpi_changes_the_raster(self, server):
        lo = self._img(server + "/render/p209.png?dpi=250")
        hi = self._img(server + "/render/p209.png?dpi=400")
        assert hi.size[0] / lo.size[0] == pytest.approx(1.6, abs=0.01)

    def test_render_crop_uses_the_same_rect_space_as_cropped(self, server):
        """A rect written for /cropped must land on the same content at 400."""
        q = "height=885&width=748&top_left_y=204&top_left_x=592"
        view = self._img(server + f"/cropped/xg-25.jpg?{q}")
        topo = self._img(server + f"/render/p25.png?dpi=400&{q}")
        assert topo.size[0] / view.size[0] == pytest.approx(1.6, abs=0.01)
        assert topo.size[1] / view.size[1] == pytest.approx(1.6, abs=0.01)

    def test_render_without_pdf_is_a_clear_error(self):
        pages = inspectserver.Pages(PAGES_DIR, [LINES], None, None, "gs")
        with pytest.raises(ValueError, match="--pdf"):
            pages.render(1, 400)

    def test_bad_route_is_404(self, server):
        with pytest.raises(HTTPError) as e:
            urlopen(server + "/render/nope.png")
        assert e.value.code == 404


@pytest.mark.skipif(not os.path.isdir(PAGES_DIR), reason="needs a pages folder")
class TestCoordinateSpaceDiagnostics:
    """A units mismatch must name itself, not surface as a bare 400."""

    def _pages(self, dims, px_per_pt=None):
        p = inspectserver.Pages(PAGES_DIR, [], None, None, "gs")
        page = sorted(p.by_page)[0]
        p.dims[page] = dims
        if px_per_pt:
            p.px_per_pt[page] = px_per_pt
        return p, page

    def test_points_sized_lines_json_is_flagged_at_startup(self):
        """612x792 declared against a 2125x2750 image is points vs pixels."""
        p, _ = self._pages((612.0, 792.0))
        notes = p.check_consistency()
        assert notes and "POINTS" in notes[0]

    def test_pixel_sized_lines_json_is_silent(self):
        from PIL import Image
        p = inspectserver.Pages(PAGES_DIR, [], None, None, "gs")
        page = sorted(p.by_page)[0]
        with Image.open(p.by_page[page]) as im:
            p.dims[page] = (im.width, im.height)
        p.px_per_pt[page] = 250 / 72
        assert p.check_consistency() == []

    def test_diagnose_reports_the_scale_and_the_mapping(self):
        p, page = self._pages((612.0, 792.0))
        info = p.diagnose(page, {"top_left_x": ["929"], "top_left_y": ["496"],
                                 "width": ["58"], "height": ["44"]},
                          2125, 2750)
        assert info["scale_applied"][0] == pytest.approx(3.47, abs=0.01)
        assert info["mapped_to_px"][0] > 2125, "must show it lands off-page"
        assert "POINTS" in info["hint"]
        assert info["space_source"] == "lines.json"

    def test_assume_pixels_overrides_the_declared_space(self):
        p = inspectserver.Pages(PAGES_DIR, [], None, None, "gs",
                                assume_pixels=True)
        page = sorted(p.by_page)[0]
        p.dims[page] = (612.0, 792.0)
        assert p.scale(page, 2125, 2750) == (1.0, 1.0)


class TestPageImagesBelongToTheDocument:
    """Page images used to share ONE folder across documents.

    Converting a second document into the same output directory silently
    reused the first one's renders: a crop captioned "An XML Document as a
    Tree" showed a type hierarchy from an entirely different book. The
    renderer now namespaces by document and writes a manifest.
    """

    def _dir(self, tmp_path, document="Alpha"):
        import json
        d = tmp_path / "pages"
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"document": document, "dpi": 250, "pages": 2}))
        return str(d)

    def test_mismatch_is_reported(self, tmp_path):
        p = inspectserver.Pages(self._dir(tmp_path), [], None, None, "gs")
        notes = p.check_identity([], "/somewhere/Beta.pdf")
        assert notes and "Beta" in notes[0] and "Alpha" in notes[0]

    def test_match_is_silent(self, tmp_path):
        p = inspectserver.Pages(self._dir(tmp_path), [], None, None, "gs")
        assert p.check_identity([], "/somewhere/Alpha.pdf") == []

    def test_lines_json_name_is_checked_too(self, tmp_path):
        p = inspectserver.Pages(self._dir(tmp_path), [], None, None, "gs")
        assert p.check_identity(["/x/Beta.lines.json"], None)

    def test_missing_manifest_is_reported(self, tmp_path):
        d = tmp_path / "bare"
        d.mkdir()
        p = inspectserver.Pages(str(d), [], None, None, "gs")
        notes = p.check_identity([], "/x/Alpha.pdf")
        assert notes and "manifest" in notes[0]

    def test_no_document_given_is_silent(self, tmp_path):
        """Serving images alone, with nothing to check against, is fine."""
        p = inspectserver.Pages(self._dir(tmp_path), [], None, None, "gs")
        assert p.check_identity([], None) == []


class TestACoordinateRatioIsNotAMismatch:
    """819d — the normal pdfdrill+MathPix pairing IS a 1.6x ratio, and the
    warning called it a failure.

    MathPix works at 250 dpi (2125x2750 on Letter) and pdf2mmd matches that
    space deliberately; `pdfdrill inspect` renders its pages at 400 dpi
    (3400x4400). Both are PIXELS, `scale()` divides one by the other, and crops
    land exactly right — measured, aspect ratio preserved to the pixel
    (834/571 = 1334/914). Telling the user "every crop will land off the page"
    there is false, and it is the first thing they read.
    """

    def _pages(self, tmp_path, decl_w, decl_h, img_w, img_h):
        from PIL import Image
        d = tmp_path / "pages"
        d.mkdir()
        Image.new("RGB", (img_w, img_h)).save(d / "p1.png")
        lines = tmp_path / "x.lines.json"
        lines.write_text(json.dumps({"pages": [
            {"page": 1, "image_id": "x-01", "lines": [],
             "page_width": decl_w, "page_height": decl_h}]}))
        return inspectserver.Pages(str(d), [str(lines)], None, None, "gs")

    def test_a_dpi_difference_explains_itself(self, tmp_path):
        notes = self._pages(tmp_path, 2125, 2750, 3400, 4400).check_consistency()
        assert notes and "both pixels" in notes[0]
        assert "land off the page" not in notes[0]
        assert "--coord-width 2125" in notes[0]

    def test_points_are_still_reported_as_the_failure_they_are(self, tmp_path):
        notes = self._pages(tmp_path, 612, 792, 3400, 4400).check_consistency()
        assert notes and "PDF POINTS" in notes[0]
        assert "land off the page" in notes[0]

    def test_the_same_space_says_nothing(self, tmp_path):
        assert self._pages(tmp_path, 3400, 4400, 3400, 4400).check_consistency() == []


def test_the_banner_advertises_the_mask_the_server_actually_uses():
    """The `g` in `<id>g-<page>.jpg` was a stray character from the docstring
    example, and it advertised a filename mask the server does not use: the path
    is the image_id verbatim. Two masks for one thing is one too many."""
    src = pathlib.Path(inspectserver.__file__).read_text()
    assert "/cropped/<image_id>.jpg" in src
    assert "<id>g-<page>" not in src


class TestTheLibraryServesEveryDocument:
    """820 — one process for the whole library, and no URL changes.

    The server was built to test ONE document and served one: a second document
    meant a second process on a second port. Measured over 400 corpus documents:
    12,742 distinct image_ids and ZERO collisions, because a MathPix id is a
    per-conversion UUID plus a page number — so an id already identifies
    (document, page) library-wide.
    """

    def _lib(self, tmp_path, docs):
        """docs = {name: {image_id: page}} -> a library root with manifests."""
        from PIL import Image
        for name, ids in docs.items():
            d = tmp_path / name / "inspect" / "pages"
            d.mkdir(parents=True)
            for page in sorted(set(ids.values())):
                Image.new("RGB", (3400, 4400)).save(d / f"p{page}.png")
            man = {"document": name, "dpi": 400,
                   "pages": len(set(ids.values())),
                   "coord": [2125, 2750]}
            if ids:
                man["image_ids"] = ids
            (d / "manifest.json").write_text(json.dumps(man))
        return inspectserver.Library(str(tmp_path))

    def test_an_image_id_finds_its_own_document(self, tmp_path):
        lib = self._lib(tmp_path, {
            "docA": {"aaaa-01": 1, "aaaa-02": 2},
            "docB": {"bbbb-01": 1},
        })
        assert lib.documents == 2
        assert len(lib.dir_of_id) == 3
        a = lib.pages_for_id("aaaa-02")
        b = lib.pages_for_id("bbbb-01")
        assert a is not None and b is not None
        assert a is not b
        assert "docA" in a.root and "docB" in b.root

    def test_the_page_comes_from_the_manifest_not_a_lines_json(self, tmp_path):
        """The whole point of indexing manifests: no 10 MB lines.json is opened
        at request time."""
        lib = self._lib(tmp_path, {"docA": {"aaaa-07": 7}})
        pg = lib.pages_for_id("aaaa-07")
        assert pg.id_page["aaaa-07"] == 7
        assert pg.dims == {}          # nothing was loaded from a lines.json

    def test_the_coordinate_space_comes_from_the_manifest_too(self, tmp_path):
        lib = self._lib(tmp_path, {"docA": {"aaaa-01": 1}})
        pg = lib.pages_for_id("aaaa-01")
        assert pg.coord == (2125, 2750)
        # and it scales: 400 dpi image against a 250 dpi coordinate space
        assert pg.scale(1, 3400, 4400) == (1.6, 1.6)

    def test_a_document_is_built_once_and_cached(self, tmp_path):
        lib = self._lib(tmp_path, {"docA": {"aaaa-01": 1, "aaaa-02": 2}})
        assert lib.pages_for_id("aaaa-01") is lib.pages_for_id("aaaa-02")

    def test_a_document_can_be_addressed_by_name(self, tmp_path):
        lib = self._lib(tmp_path, {"docA": {"aaaa-01": 1}})
        assert lib.pages_for_doc("docA") is not None
        assert lib.pages_for_doc("nope") is None

    def test_an_unknown_id_is_not_served_from_the_wrong_document(self, tmp_path):
        """The hazard the manifest guard exists for: a crop showing a figure from
        an entirely different book under the right caption."""
        lib = self._lib(tmp_path, {"docA": {"aaaa-01": 1}})
        assert lib.pages_for_id("bbbb-01") is None

    def test_a_manifest_with_no_index_is_reported_not_silently_dropped(self, tmp_path):
        lib = self._lib(tmp_path, {"docA": {"aaaa-01": 1}, "docB": {}})
        assert lib.documents == 1
        assert "docB" in lib.skipped

    def test_pages_with_no_manifest_at_all_are_counted(self, tmp_path):
        """A folder with no manifest is invisible to the glob, so reporting only
        `skipped` said "0 without an index" while 746 of 747 documents were
        unreachable."""
        from PIL import Image
        lib_root = tmp_path
        self._lib(lib_root, {"docA": {"aaaa-01": 1}})
        bare = lib_root / "docC" / "inspect" / "pages"
        bare.mkdir(parents=True)
        Image.new("RGB", (100, 100)).save(bare / "p1.png")
        lib = inspectserver.Library(str(lib_root))
        assert lib.unindexed == ["docC"]
