r"""
836/838 — seams 2 and 3 of the pdf2mmd integration: crop images, and one
crop id.

The two halves neither program had right:

  * pdf2mmd derived its preamble from the document's content (seam 1, fixed in
    836) but emitted every crop as an `http://localhost:8000/cropped/...` URL,
    so its `.tex` compiled in nonstopmode with 324 of 324 images MISSING and
    looked like it had worked.
  * Its crop id was `{doc_id}g-{page}` while pdfdrill's manifest has always
    written `<bibkey>-<page:02d>`, so the Markdown it produced could not
    resolve against the server `inspect` feeds: 404, with a helpful message
    pointing at the wrong fix.

Measured on arXiv 1102.1889 through `pdfdrill glyphlines`:

    before   324 \includegraphics, 324 URLs,   324 images missing
    after    324 \includegraphics,   0 URLs,     0 images missing
             (xelatex: 111 pages, 0 errors)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest                                                  # noqa: E402

pytest.importorskip("pdfminer")

from pdfreader import project_mmd as mmd                       # noqa: E402


class _Page:
    """The two things `crop_box`/`crop_ref` read off a page."""
    def __init__(self, page, rect):
        self.page = page
        self.rect = rect


def test_there_is_one_crop_id_and_it_is_the_manifest_s():
    """`<bibkey>-<page:02d>`. The `g` and the unpadded page were the two
    halves of the 404."""
    assert mmd.crop_id("olog", 2) == "olog-02"
    assert mmd.crop_id("olog", 12) == "olog-12"
    assert mmd.crop_id("arxiv.1102.1889", 7) == "arxiv.1102.1889-07"


def test_the_retired_id_shape_is_gone():
    for page in (1, 7, 52):
        assert "g-" not in mmd.crop_id("doc", page)


def test_both_id_shapes_still_resolve_to_a_page_at_the_server():
    """This is a rename, not a protocol change: `inspectserver.page_of` falls
    back to the trailing integer, so an old URL in an already-written .md
    keeps working."""
    from pdfreader.inspectserver import TRAILING_INT
    for ident, page in (("arxiv.1102.1889g-7", "7"),
                        ("arxiv.1102.1889-07", "07"),
                        ("olog-12", "12")):
        m = TRAILING_INT.search(ident)
        assert m and m.group(1) == page, ident


def test_crop_box_is_y_down_pixels_from_y_up_points():
    p = _Page(1, (0, 0, 100, 200))
    left, top, w, h = mmd.crop_box((10, 150, 40, 190), p, px_per_pt=2.0)
    assert (left, w, h) == (20, 60, 80)
    # y is measured from the TOP of the page: (200 - 190) * 2
    assert top == 20


def test_the_url_is_built_from_the_same_box():
    p = _Page(3, (0, 0, 100, 200))
    url = mmd.crop_url((10, 150, 40, 190), p, "doc", "http://h:1", 2.0)
    assert "/cropped/doc-03.jpg" in url
    assert "top_left_x=20" in url and "top_left_y=20" in url
    assert "width=60" in url and "height=80" in url


def test_a_crop_ref_that_has_no_file_drops_the_figure():
    r"""A reference to a crop that was not written is the defect this seam
    exists to remove; emitting one for a rectangle the renderer skipped would
    only move it."""
    import inspect
    src = inspect.getsource(mmd.to_latex)
    assert "if not ref:" in src
    assert "% uncropped:" in src, (
        "a dropped crop must leave a comment saying so, not silence")


def test_the_latex_projector_takes_a_reference_maker():
    import inspect
    assert "crop_ref" in inspect.signature(mmd.to_latex).parameters
    # and the markdown does NOT: a reader with a server is the point there
    assert "crop_ref" not in inspect.signature(mmd.to_markdown).parameters


# ---------------------------------------------------------------- 862

def test_the_cli_tex_export_cannot_emit_a_link_latex_cannot_fetch():
    r"""862 — 838 gave `to_latex` a `crop_ref` and wired a file-writing one into
    `pdfdrill glyphlines`, so `.glyphs.tex` holds real paths. `pdf2mmd.py main()`
    was left passing none and kept emitting
    `\includegraphics{http://localhost:8000/cropped/...}` — and it is still the
    entry point inkdrill invokes: 2,783 dead links across 20 sigma26 `.tex`
    files, 698 in sigma26-086 alone, each wrapped in `\begin{figure}[H]` where an
    inline formula belongs.

    LaTeX cannot fetch a URL. The document does not typeset there on any machine
    without that server running, so the default is the comment alone: a missing
    figure is better than a broken one.
    """
    import inspect
    from pdfreader import pdf2mmd
    src = inspect.getsource(pdf2mmd.main)
    assert "crop_ref" in src, "the tex export must pass a crop_ref"
    assert "--crop-urls" in src, "URLs must be opt-in, not the default"
    # the default branch yields the empty reference, which to_latex turns into
    # `% uncropped: …` rather than a figure
    assert 'lambda rect, page: ""' in src


# NOT ADDED: a second assertion that `to_latex`'s no-crop branch emits a comment
# rather than a figure. 838's `test_a_crop_ref_that_has_no_file_drops_the_figure`
# already holds that contract, and my first attempt here sliced the function's
# SOURCE TEXT between two string indices — which is the third time today I have
# written a check that could not be contradicted by the code being wrong. One
# assertion of a contract, in the place that owns it.


# ---------------------------------------------------------------- 863

def test_exports_only_stops_before_the_reading_is_rewritten():
    r"""863 — A READING IS HASHED BY ITS CONSUMERS.

    inkdrill's every mark set carries
    `measured_against: {"<stem>.lines.json": "<sha256>"}`, so rewriting the
    reading invalidates the set even when the new reading means the same thing —
    and after 846 it is not even byte-identical, because the top-level `source`
    key is new. So regenerating the two exports to drop 862's dead crop URLs
    must not touch the reading, or fixing a broken link costs a re-measurement
    of nineteen documents.

    Verified on sigma26-092: 26 dead URLs became 0 with 22 `% uncropped:`
    comments, and the lines.json sha256 did not move.
    """
    import inspect
    from pdfreader import pdf2mmd
    src = inspect.getsource(pdf2mmd.main)
    assert "--exports-only" in src
    guard = src.index("if args.exports_only")
    # the guard must come BEFORE every write that touches the reading or model
    for later in ('.lines.json", "w"', "model.docmodel.json",
                  '.equations.json", "w"', '.fonts.md", "w"'):
        assert guard < src.index(later), f"{later} is written before the guard"


def test_every_argparse_help_escapes_its_percent_signs():
    r"""862 left `% uncropped:` in a help string, and argparse treats `%` as a
    format specifier: the whole CLI died with "badly formed help string" before
    writing anything. It failed SAFELY — the reading's hash was untouched — but
    a flag nobody can pass is a flag that does not exist."""
    import argparse
    import contextlib
    import io
    from pdfreader import pdf2mmd
    # building the parser and rendering help is what raises
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            pdf2mmd.main(["--help"])
        except SystemExit:
            pass                       # --help exits 0; that is success here
        except ValueError as e:         # pragma: no cover
            raise AssertionError(f"argparse rejected a help string: {e}")
