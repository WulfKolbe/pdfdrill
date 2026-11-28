r"""Column detection on arxiv.2209.02970 (user report, 2026-11-28).

Pages where the right column is short (a figure fills it), where one column's
lines start in several 12 pt bins (indented code), or where a row mixes CJK and
run-together Latin (few gaps, so the gutter gap was its own "typical" gap) read
their rows across the gutter. A single-column page must still not be split.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")

PAGE = (0.0, 0.0, 595.0, 842.0)


def _g(text, x0, x1, base, size=10.0):
    return dm.GlyphNode(id=f"g{x0}_{base}", page=1, rect=(x0, base - 2, x1, base + 8),
                        text=text, cid=0, glyphname=None, fontname="T+Times-Roman",
                        family="text", size=size, tex=texmap.UNKNOWN,
                        matrix=(size, 0, 0, size, x0, base))


def _row(x0, x1, base, step=5.0, gap_every=6):
    out, x, n = [], x0, 0
    while x + 4 <= x1:
        out.append(_g("a", x, x + 4, base))
        n += 1
        x += 4 + (step - 4) + (2.5 if n % gap_every == 0 else 0)
    return out


def test_a_short_right_column_is_still_a_column():
    rows = [_row(60, 290, 800 - 12 * i) for i in range(34)]          # left column
    rows += [_row(300, 535, 800 - 12 * i) for i in range(4)]         # 4 right rows
    edge = dm._column_edge(rows, PAGE)
    assert edge is not None and 285 < edge < 300


def test_a_single_column_page_is_not_split():
    rows = [_row(60, 535, 800 - 12 * i) for i in range(30)]          # prose across
    rows += [_row(300, 400, 400 - 12 * i) for i in range(4)]         # 4 indented rows
    assert dm._column_edge(rows, PAGE) is None


def test_a_cjk_row_is_cut_at_its_only_large_gap():
    row = [_g("•", 84, 88, 329)] + [_g("x", 93 + 4 * i, 97 + 4 * i, 329) for i in range(30)]
    row += [_g("练", 306 + 11 * i, 317 + 11 * i, 329.6) for i in range(20)]
    out = dm._split_at_columns([row], 298.3)
    assert len(out) == 2 and out[1][0].text == "练"
