r"""
B13/J5, lib:c57ac038ae5f p293 frames its four-line algorithm (13.9) in a
ruled box. `listings.frames` finds the rectangle; read as four displays the
box was lost and the judge counted its rules missing. Displays that are the
only lines inside a frame become one `\boxed{\begin{aligned}...\end{aligned}}`,
each row aligned at its first relation. Judge (pin inkdrill 217b03b, which
pairs a drawn frame as its four edges) c57a p293: 0.0025 -> 0.0008.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")


def _rec(text, y, typ="math", x=200, w=300):
    return {"type": typ, "text": text, "text_display": text, "complete": True, "rules": [],
            "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": 40}}


def _page(lines):
    out = {"pages": [{"lines": lines}]}
    pn = SimpleNamespace(rect=(0.0, 0.0, 612.0, 792.0), frames=[(50.0, 600.0, 200.0, 760.0)])
    return out, pn


K = 2.0     # px per pt: the frame is x 100..400, y 64..384 in px


def test_framed_displays_become_one_box():
    lines = [_rec("\\[\np = r ,\n\\]", 80), _rec("\\[\n\\alpha := a/b\n\\]", 160),
             _rec("(13.9)", 200, typ="equation_number", x=500, w=40)]
    out, pn = _page(lines)
    D._box_framed_displays(out, [pn], K)
    got = out["pages"][0]["lines"]
    assert len(got) == 2
    assert got[0]["text"] == "\\[\n\\boxed{\\begin{aligned}p &= r , \\\\ \\alpha &:= a/b\\end{aligned}}\n\\]"
    assert got[1]["text"] == "(13.9)"


def test_a_frame_with_prose_inside_is_left_alone():
    lines = [_rec("\\[\np = r\n\\]", 80), _rec("some prose", 160, typ="text")]
    out, pn = _page(lines)
    D._box_framed_displays(out, [pn], K)
    assert [r["text"] for r in out["pages"][0]["lines"]] == ["\\[\np = r\n\\]", "some prose"]


def test_alignment_skips_braces():
    assert D._align_at_relation(r"f_{a=b} = c") == r"f_{a=b} &= c"
