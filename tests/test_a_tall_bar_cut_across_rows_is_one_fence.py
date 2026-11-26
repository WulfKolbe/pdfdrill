"""
A tall `|...|` cut across six rows is one fence (B4b, P4).

1805.01788 p3's equation (1) ends `\\left|\\sum_{j=1}^m a_i^j - \\sum_{j=1}^m
r_i^j\\right|`. txfonts draws each bar as six `barex` pieces, and the baseline
grouper gave every piece a row of its own, two of them with the scripts `j`
and `i`. Each piece was an unread glyph (17 refusals), the outer bars were
lost, and `a`, `r` lost their scripts.

The rows are the page's own, frozen as they reach the fold. Judge (pin
ed6eb5d) on the page: 0.0178 -> 0.0092.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken, project

FIX = Path(__file__).parent / "fixtures" / "tall_bar_in_six_rows.groups.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _rows():
    d = json.loads(FIX.read_text())
    rows = []
    for r in d["g"]:
        row = []
        for g in r:
            g = {k: _tup(v) for k, v in g.items()}
            g["tex"] = TexToken(*g["tex"])
            row.append(dm.GlyphNode(**g))
        rows.append(row)
    return rows, d["span_pt"]


def test_barex_is_a_piece_of_a_fence():
    assert project("math-extension", "barex", -1, "ERHUAP+txexs").kind == "fragment"


def test_the_pieces_rows_fold_into_the_display_row():
    rows, span_pt = _rows()
    assert len(rows) == 7
    moved = dm._fold_fence_stacks(rows, span_pt)
    left = [r for r in rows if r]
    assert len(left) == 1, [len(r) for r in left]
    host = left[0]
    assert sum(g.tex.kind == "fragment" for g in host) == 12
    assert len(moved) == 6


def test_the_two_stacks_become_left_and_right_bars():
    rows, span_pt = _rows()
    dm._fold_fence_stacks(rows, span_pt)
    host = next(r for r in rows if r)
    merged, _ = dm.merge_fragments(host)
    # the row's own `|A_i - R_i|` bars are plain `|`; the stacks are fenced
    bars = [g.tex.latex for g in merged if g.tex.kind == "delimiter"
            and g.tex.latex.startswith(("\\left", "\\right"))]
    assert bars == [r"\left|", r"\right|"], bars
