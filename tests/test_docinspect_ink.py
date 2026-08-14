"""B4 — a 3,390-component page must OPEN showing tens of objects.

The tree gives the collapse levels for free: 101 regions by default, expand one
to see its 20-900 children. The canvas layer is not a prerequisite for that and
is deliberately not used here.

Asserted by booting the SHIPPED script against the DOM shim and counting the
rows a reader actually gets, not by grepping the emitted HTML. The emitted HTML
carries the child data either way — that is the whole point of lazy expansion —
so a string search would pass on a page that renders 3,668 rows and locks the
browser.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

_SHIM = Path(__file__).resolve().parent / "dom_shim.js"


def _model():
    return {
        "meta": {"bibkey": "demo", "num_pages": 1,
                 "pages": [{"page": 1, "page_width": 1000, "page_height": 1400}]},
        "streams": {"mathpix_lines": {"anchors": ["a1"], "payload": {
            "a1": {"text": "hello", "_page": 1,
                   "region": {"top_left_x": 10, "top_left_y": 10,
                              "width": 900, "height": 40}}}}},
        "objects": [
            {"id": "p1", "type": "Paragraph", "flow_index": 1,
             "props": {"page": 1, "flow_index": 1, "text": "hello"},
             "realizations": [{"stream": "mathpix_lines", "start": "a1", "end": "a1"}]},
        ],
        "alignments": [],
    }


def _sum(n, w=4, h=7, holes=2):
    return {"n": n, "median_w": w, "median_h": h, "max_w": w * 3,
            "max_h": h * 2, "holes": holes, "area": n * 20}


def _ink_tree(n_children=900):
    """One fat region plus two thin ones, and every residual class populated."""
    return {"1": {
        "components": n_children + 3,
        "regions": 3,
        "region_list": [["diagram#0", "diagram", n_children, _sum(n_children)],
                        ["text#1", "text", 2, _sum(2)],
                        ["text#2", "text", 0, None]],
        "region_rects": {"diagram#0": [0, 0, 950, 500],
                         "text#1": [0, 600, 950, 640],
                         "text#2": [0, 700, 950, 740]},
        "residuals": {"orphan": [[500.0, 900.0, 520.0, 906.0]],
                      "straddler": [[940.0, 600.0, 980.0, 610.0]],
                      "tie": [[3.0, 602.0, 4.0, 603.0]]},
        "residual_counts": {"orphan": 1, "straddler": 1, "tie": 1},
    }}


def _boot(body: str, ink_tree=None):
    html = docinspect.build_inspector_html(_model(), pages={}, title="t",
                                           ink_tree=ink_tree)
    i = html.index("const DATA = ")
    script = html[i:html.index("</script>", i)]
    start = html.index("<body>") + len("<body>")
    markup = html[start:html.index("<script", start)]
    prog = "\n".join(["globalThis.__SHIM_BODY = " + json.dumps(markup) + ";",
                      _SHIM.read_text(encoding="utf-8"), script,
                      "const OUT = {};", body,
                      'console.log("@@" + JSON.stringify(OUT));'])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(prog)
        path = fh.name
    try:
        p = subprocess.run(["node", path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert p.returncode == 0, p.stderr[-3000:]
    return json.loads([l for l in p.stdout.splitlines()
                       if l.startswith("@@")][-1][2:])


def test_a_900_child_region_opens_collapsed_as_one_row():
    out = _boot("""
      const panel = document.getElementById('inkPanel');
      OUT.rows = panel.querySelectorAll('.inkregion').length;
      OUT.kids = panel.querySelectorAll('.inkkid').length;
      OUT.text = panel.allText();
    """, ink_tree=_ink_tree())
    assert out["rows"] == 3, "one row per region, not per blob"
    assert out["kids"] == 0, "children must not be in the DOM until expanded"
    assert "900" in out["text"], "the child count is what makes a region worth opening"


def test_expanding_a_region_shows_a_summary_block_not_a_list_of_extents():
    """Superseded design, deliberately: the panel used to expand into one row
    per blob. `2x4 pt, 4x7 pt, 4x7 pt` tells a reader nothing, and on the
    extreme page it is 11,551 rows. One summary block replaces the list."""
    panel_js = """
      const panel = document.getElementById('inkPanel');
      panel.querySelectorAll('.inkregion')[0].dispatch('click');
      OUT.blocks = panel.querySelectorAll('.inksummary').length;
      OUT.kids = panel.querySelectorAll('.inkkid').length;
      OUT.text = panel.querySelectorAll('.inksummary').length
                   ? panel.querySelectorAll('.inksummary')[0].textContent : '';
      panel.querySelectorAll('.inkregion')[0].dispatch('click');
      OUT.after_collapse = panel.querySelectorAll('.inksummary').length;
    """
    out = _boot(panel_js, ink_tree=_ink_tree())
    assert out["blocks"] == 1 and out["kids"] == 0
    assert "median" in out["text"] and "holes" in out["text"]
    assert out["after_collapse"] == 0


def test_the_three_residual_classes_are_visible_without_expanding_anything():
    """The tree is the product; the residuals are the AUDIT. A straddler that
    only appears behind a click is a straddler nobody looks at."""
    out = _boot("""
      const panel = document.getElementById('inkPanel');
      OUT.text = panel.allText();
    """, ink_tree=_ink_tree())
    for cls in ("orphan", "straddler", "tie"):
        assert cls in out["text"].lower(), cls


def test_a_residual_count_survives_a_tree_that_carries_no_rectangles():
    """A tree stored before rects were recorded has the ids and no rectangles.

    Counting the rect array then reported "straddler 0" for a page that has
    one — a zero meaning "unknown", which is the exact failure this audit
    exists to catch. The count comes from `residual_counts`.
    """
    tree = _ink_tree(2)
    tree["1"]["residuals"] = {"orphan": [], "straddler": [], "tie": []}
    out = _boot("""
      OUT.text = document.getElementById('inkPanel').allText();
    """, ink_tree=tree)
    assert "straddler  1" in out["text"]


def _two_page_tree():
    """Page 8 is ordinary; page 11 is the extreme case — a document about
    document extraction, containing pictures of documents. Nothing else in the
    corpus puts 11,551 blobs under one region, which is exactly why it is the
    standing test for the collapse behaviour."""
    tree = _ink_tree(4)
    tree["11"] = {
        "components": 11708, "regions": 5,
        "region_list": [["diagram#0", "diagram", 11551, _sum(11551)],
                        ["text#1", "text", 100, _sum(100)],
                        ["text#2", "text", 55, _sum(55)],
                        ["page_info#3", "page_info", 2, _sum(2)],
                        ["text#4", "text", 0, None]],
        "residuals": {"orphan": [], "straddler": [], "tie": []},
        "residual_counts": {"orphan": 0, "straddler": 0, "tie": 0},
    }
    return tree


def test_the_panel_opens_on_the_page_being_viewed_not_the_first_page_with_ink():
    """It opened on the first page carrying ink regardless of where the reader
    was, so a reader on page 11 was shown page 8's 101 regions and had to touch
    the selector to see the 5 that belong to the page in front of them."""
    out = _boot("""
      gotoPage(11);
      const p = document.getElementById('inkPanel');
      OUT.rows = p.querySelectorAll('.inkregion').length;
      OUT.head = p.allText().split('\\n')[0];
    """, ink_tree=_two_page_tree())
    assert out["rows"] == 5
    assert "11708" in out["head"]


def test_a_collapsed_row_carries_a_blob_summary_so_it_is_worth_reading():
    """A row that says only "diagram" tells a reader nothing about whether it
    is worth opening. The count and the size of what is inside are what make
    the collapsed level usable on its own."""
    out = _boot("""
      gotoPage(11);
      const rows = document.getElementById('inkPanel').querySelectorAll('.inkregion');
      OUT.first = rows[0].textContent;
      OUT.empty_row = rows[4].textContent;
    """, ink_tree=_two_page_tree())
    assert "11551 blobs" in out["first"]
    assert "median" in out["first"], "count alone does not separate 11,551 tick marks from 12 paragraphs"
    # a region with nothing in it says so, and offers no twisty to open
    assert "0 blobs" in out["empty_row"] and "▸" not in out["empty_row"]


def test_a_table_region_renders_its_grid_not_a_flat_list_of_children():
    """`inktables` already knows 13x4 with column widths; showing 52 anonymous
    child rectangles throws that away and makes the reader rebuild it by eye."""
    tree = _ink_tree(4)
    tree["1"]["tables"] = [{
        "region_id": "table#9", "n_rows": 13, "n_cols": 4,
        "holes": 52,
        "col_widths": [45.0, 42.7, 99.5, 278.3],
        "row_heights": [37.8, 23.8],
    }]
    tree["1"]["region_list"].append(["table#9", "table", 52, _sum(52)])
    out = _boot("""
      const p = document.getElementById('inkPanel');
      const rows = p.querySelectorAll('.inkregion');
      let t = null;
      rows.forEach(r => { if (r.dataset.rid === 'table#9') t = r; });
      t.dispatch('click');
      OUT.grid = p.querySelectorAll('.inkgrid').length;
      OUT.kids = p.querySelectorAll('.inkkid').length;
      OUT.text = p.allText();
    """, ink_tree=tree)
    assert out["grid"] == 1, "a table expands to a grid, not to child rectangles"
    assert out["kids"] == 0
    assert "13" in out["text"] and "4" in out["text"]
    assert "278.3" in out["text"], "the column widths are the part worth having"


def test_the_ink_panel_is_absent_entirely_when_no_ink_was_merged():
    """A document with no inkdrill run must not grow an empty panel that
    reads as "no ink found" when the truth is "inkdrill never ran"."""
    out = _boot("""
      const p = document.getElementById('inkPanel');
      OUT.present = !!p;
    """, ink_tree=None)
    assert out["present"] is False
