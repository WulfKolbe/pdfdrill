"""Column-aware reading order for the engine `md` path.

A 2-column PDF read by char-`top` across the FULL width interleaves the columns
(left+right lines at the same y merge into garble). `_split_into_columns` detects
the gutter and returns [left, right] so each column is read top-to-bottom, left
before right. A single-column page is returned unchanged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.nodes.ingest_pdfplumber import _split_into_columns


def _ch(x0, top, w=8.0):
    return {"x0": x0, "x1": x0 + w, "top": top, "width": w, "height": 10}


def _two_column_page():
    chars = []
    for row in range(20):
        top = 100 + row * 12
        for x in range(50, 250, 8):       # LEFT column
            chars.append(_ch(x, top))
        for x in range(320, 520, 8):      # RIGHT column
            chars.append(_ch(x, top))
    return chars


def test_splits_two_columns_left_then_right():
    cols = _split_into_columns(_two_column_page())
    assert len(cols) == 2
    left, right = cols
    assert max(c["x1"] for c in left) < min(c["x0"] for c in right)   # gutter
    # left column comes first in the returned order
    assert max(c["x0"] for c in left) < 300 and min(c["x0"] for c in right) >= 300


def _two_column_with_header():
    chars = []
    for row in range(3):                  # full-width title/author header
        for x in range(50, 520, 8):
            chars.append(_ch(x, 50 + row * 12))
    for row in range(20):                  # 2-column body below
        top = 120 + row * 12
        for x in range(50, 250, 8):
            chars.append(_ch(x, top))
        for x in range(320, 520, 8):
            chars.append(_ch(x, top))
    return chars


def test_splits_two_columns_under_full_width_header():
    # the real-paper case: a full-width header over a 2-column body must STILL
    # split (the gutter is low-density, not empty — header chars cross it).
    cols = _split_into_columns(_two_column_with_header())
    assert len(cols) == 2


def test_single_column_unchanged():
    chars = []
    for row in range(20):
        for x in range(50, 520, 8):       # full-width single column
            chars.append(_ch(x, 100 + row * 12))
    cols = _split_into_columns(chars)
    assert len(cols) == 1 and len(cols[0]) == len(chars)


def test_reading_order_left_column_fully_before_right():
    # concatenating columns then per-column line detection must keep left text
    # (top→bottom) entirely before right text — not interleave by y.
    cols = _split_into_columns(_two_column_page())
    order = [c for col in cols for c in col]
    first_right = next(i for i, c in enumerate(order) if c["x0"] >= 300)
    last_left = max(i for i, c in enumerate(order) if c["x0"] < 300)
    assert last_left < first_right            # all left before any right


if __name__ == "__main__":
    for fn in [test_splits_two_columns_left_then_right,
               test_splits_two_columns_under_full_width_header,
               test_single_column_unchanged,
               test_reading_order_left_column_fully_before_right]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
