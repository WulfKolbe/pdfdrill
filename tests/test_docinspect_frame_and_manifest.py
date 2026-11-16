"""
P9-18 and P9-15 (T-0145, 0001124 p9): the inspect payload states its frame, and
the page can be probed for what it drew.

P9-18 -- THE UNITS WERE MISNAMED. `collect_elements` emitted
`{"page": 9, "pt_w": 3400, "pt_h": 4400}` for a 612 x 792 pt page. Nothing was
wrong with the numbers: every region in a reading is in the reading's own
pixels, and the overlay places boxes as `100*x/w` percent, so a ratio is all it
needs. The NAME was wrong, and it is the name a reader believes -- the
coordinator read it as points and found a page 5.56x too large, the same class
as the task-654 frame defect. The repo already knew better in two places:
`docmodel_six` writes `page_width = round(width_pt * k)` and records
`px_per_pt` beside it, and PROPS.md documents the prop as "page dimensions in
MathPix pixels". The reading states the factor; inspect threw it away.

So the payload now declares its frame the way `pdfdrill.eqlist` does -- px_w,
px_h and the reading's own px_per_pt -- and the inspector shows a region in
pixels, with the points beside it when the factor is known. THE FRAME IS
DECLARED, NEVER INFERRED: px_per_pt comes from the reading (400 dpi = 5.5556
for the glyph reader, 250 dpi = 3.4722 for MathPix and the text layer), never
from a constant and never from the largest observed x.

P9-15 -- THE DOCUMENTED PROBE RETURNED 0. CLAUDE.md's acceptance contract names
`grep -c 'data-id=' x.inspect.html` as the concrete content probe for an
inspect page. The page builds every box client-side from `const DATA = {...}`,
so no `data-id=` is ever written and the documented probe answers 0 on a
perfect 247 KB page. A probe that cannot fail is not a probe. The page now
carries one machine-readable manifest line stating what it holds.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect

PX_PER_PT_400DPI = 400.0 / 72.0


def _model(px_per_pt=PX_PER_PT_400DPI):
    """A page-9 shaped model: 612 x 792 pt read at 400 dpi."""
    page = {"page": 9, "page_width": 3400, "page_height": 4400}
    if px_per_pt is not None:
        page["px_per_pt"] = round(px_per_pt, 6)
    return {
        "meta": {"bibkey": "0001124", "num_pages": 1, "title": "T",
                 "pages": [page]},
        "streams": {"mathpix_lines": {
            "anchors": ["a1"],
            "payload": {"a1": {"region": {"top_left_x": 482, "top_left_y": 1162,
                                          "width": 1962, "height": 60},
                               "text": "prose", "_page": 9}}}},
        "objects": [
            {"id": "pg9", "type": "Page", "props": {"page": 9}, "realizations": []},
            {"id": "p1", "type": "Paragraph",
             "props": {"text": "prose", "page": 9, "flow_index": 1},
             "realizations": [{"stream": "mathpix_lines", "start": "a1",
                               "end": "a1"}]},
        ],
        "alignments": [],
    }


def _pages_meta(model):
    _elements, pages_meta = docinspect.collect_elements(
        model, docinspect.build_stream_index(model))
    return pages_meta


# --------------------------------------------------------------- P9-18 ------

def test_the_payload_names_its_units_pixels_not_points():
    pm = _pages_meta(_model())[0]
    assert "pt_w" not in pm and "pt_h" not in pm, \
        f"reader pixels are still labelled points: {pm}"
    assert pm["px_w"] == 3400 and pm["px_h"] == 4400, pm


def test_the_frame_factor_is_taken_from_the_reading():
    pm = _pages_meta(_model())[0]
    assert pm["px_per_pt"] == round(PX_PER_PT_400DPI, 6), pm
    # and it is the reading's, not a constant: a 250 dpi reading says so
    pm250 = _pages_meta(_model(250.0 / 72.0))[0]
    assert pm250["px_per_pt"] == round(250.0 / 72.0, 6), pm250


def test_a_reading_that_states_no_factor_gets_none_not_a_guess():
    pm = _pages_meta(_model(px_per_pt=None))[0]
    assert pm["px_per_pt"] is None, \
        f"the frame was inferred instead of declared: {pm}"
    assert pm["px_w"] == 3400


def test_the_page_in_points_is_the_pixels_divided_by_the_factor():
    """The arithmetic a reader of the payload performs: 3400 px / 5.5556 =
    612 pt, the real page width of 0001124."""
    pm = _pages_meta(_model())[0]
    assert round(pm["px_w"] / pm["px_per_pt"]) == 612
    assert round(pm["px_h"] / pm["px_per_pt"]) == 792


def test_the_built_page_shows_a_region_in_pixels():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "m.docmodel.json"
        mp.write_text(json.dumps(_model()))
        out = Path(d) / "x.inspect.html"
        docinspect.build_from_paths(str(mp), out=str(out))
        html = out.read_text()
    assert "region pt<" not in html, "the inspector still calls pixels points"
    assert "region px" in html


# --------------------------------------------------------------- P9-15 ------

MANIFEST = re.compile(
    r"<!-- pdfdrill-inspect/1 bibkey=(\S+) elements=(\d+) pages=(\d+) "
    r"blobs=(\d+) px_per_pt=(\S+) -->")


def test_the_page_carries_a_manifest_that_can_be_grepped():
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "m.docmodel.json"
        mp.write_text(json.dumps(_model()))
        out = Path(d) / "x.inspect.html"
        docinspect.build_from_paths(str(mp), out=str(out))
        html = out.read_text()
    m = MANIFEST.search(html)
    assert m, "no machine-readable manifest line in the built page"
    bibkey, elements, pages, _blobs, px_per_pt = m.groups()
    assert bibkey == "0001124"
    assert int(pages) == 1
    assert int(elements) >= 1, "a page that drew nothing must say 0, not nothing"
    assert px_per_pt.startswith("5.5555")


def test_the_manifest_counts_match_what_the_cli_prints():
    """The point of the probe: the number in the manifest is the number of
    records the page will draw, so a short page is visible from the shell --
    and it is the SAME number `build_from_paths` prints beside the file, by the
    same rule (Page containers are the tree's furniture, not elements in it).
    Two different counts for one page is the defect that rule was written
    against."""
    model = _model()
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "m.docmodel.json"
        mp.write_text(json.dumps(model))
        out = Path(d) / "x.inspect.html"
        docinspect.build_from_paths(str(mp), out=str(out))
        html = out.read_text()
        _html, _np, n_el, _mode, _ni = docinspect.build_from_paths(str(mp))
    m = MANIFEST.search(html)
    assert int(m.group(2)) == n_el, \
        f"manifest says {m.group(2)} elements, the CLI prints {n_el}"
    elements, _pm = docinspect.collect_elements(
        model, docinspect.build_stream_index(model))
    assert n_el == sum(1 for e in elements if e.get("type") != "Page")
