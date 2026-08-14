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


def _ink_tree(n_children=900):
    """One fat region plus two thin ones, and every residual class populated."""
    kids = [[float(i), 10.0, float(i) + 5, 20.0] for i in range(n_children)]
    return {"1": {
        "components": n_children + 3,
        "regions": 3,
        "region_list": [["diagram#0", "diagram", n_children, [0, 0, 950, 500]],
                        ["text#1", "text", 2, [0, 600, 950, 640]],
                        ["text#2", "text", 0, [0, 700, 950, 740]]],
        "kids": {"diagram#0": kids,
                 "text#1": [[1.0, 601.0, 5.0, 610.0], [7.0, 601.0, 11.0, 610.0]],
                 "text#2": []},
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


def test_expanding_a_region_renders_its_children_and_only_its_children():
    out = _boot("""
      const panel = document.getElementById('inkPanel');
      panel.querySelectorAll('.inkregion')[1].dispatch('click');
      OUT.kids = panel.querySelectorAll('.inkkid').length;
      panel.querySelectorAll('.inkregion')[1].dispatch('click');
      OUT.after_collapse = panel.querySelectorAll('.inkkid').length;
    """, ink_tree=_ink_tree())
    assert out["kids"] == 2
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


def test_the_ink_panel_is_absent_entirely_when_no_ink_was_merged():
    """A document with no inkdrill run must not grow an empty panel that
    reads as "no ink found" when the truth is "inkdrill never ran"."""
    out = _boot("""
      const p = document.getElementById('inkPanel');
      OUT.present = !!p;
    """, ink_tree=None)
    assert out["present"] is False
