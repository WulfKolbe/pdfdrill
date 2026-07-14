"""
chars_to_lines (src/pdfdrill/chars_to_lines.py): convert a pdfplumber CHARACTER
dump (a born-digital PDF's text layer) into a MathPix-shape lines.json, so the
PDF is drillable offline with no MathPix. Coords flip from PDF bottom-left to
the MathPix top-left origin; chars group into lines + words.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import chars_to_lines as c2l


def _chars(*specs):
    return [{"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": t}
            for (x0, y0, x1, y1, t) in specs]


def test_single_line_word_split_and_coord_flip():
    # page height 100; "Hi" then a big x-gap then "you", PDF bottom-origin y≈90
    page = {"page_number": 1, "width": 200, "height": 100, "chars": _chars(
        (10, 90, 16, 98, "H"), (16, 90, 22, 98, "i"),
        (60, 90, 66, 98, "y"), (66, 90, 72, 98, "o"), (72, 90, 78, 98, "u"))}
    out = c2l.chars_to_lines_json({"pages": [page]})
    assert out["source"] == "pdfplumber-chars"
    ln = out["pages"][0]["lines"][0]
    assert ln["type"] == "text" and "Hi" in ln["text"] and "you" in ln["text"]
    # top-left origin: a char near the PDF top (y≈90 of 100) maps to a small top_left_y
    assert ln["region"]["top_left_y"] < 20
    assert out["pages"][0]["page_height"] == 100


def test_two_lines_separated_by_baseline():
    page = {"page_number": 1, "width": 200, "height": 100, "chars": _chars(
        (10, 90, 16, 98, "A"), (16, 90, 22, 98, "a"),       # top line  (y≈90)
        (10, 60, 16, 68, "B"), (16, 60, 22, 68, "b"))}      # lower line (y≈60)
    lines = c2l.chars_to_lines_json({"pages": [page]})["pages"][0]["lines"]
    assert len(lines) == 2
    texts = [l["text"] for l in lines]
    assert "Aa" in texts and "Bb" in texts
    # reading order: the upper line (smaller top_left_y) comes first
    assert lines[0]["region"]["top_left_y"] < lines[1]["region"]["top_left_y"]


def test_empty_and_blank_pages():
    out = c2l.chars_to_lines_json({"pages": [
        {"page_number": 1, "width": 100, "height": 100, "chars": []},
        {"page_number": 2, "width": 100, "height": 100}]})
    assert [p["page"] for p in out["pages"]] == [1, 2]
    assert all(p["lines"] == [] for p in out["pages"])


def _two_column_page(width=600.0, height=800.0, rows=8):
    """A dense two-column page: left column x∈[50,~130], right x∈[360,~450], an
    empty gutter in the middle — the layout that used to interleave."""
    chars = []
    for r in range(rows):
        y1 = 700 - r * 20; y0 = y1 - 10          # bottom-left, descending rows
        lx = 50
        for ch in f"LeftLine{r:02d}":            # a left-column word
            chars.append((lx, y0, lx + 8, y1, ch)); lx += 8
        rx = 360
        for ch in f"RightLine{r:02d}":           # a right-column word
            chars.append((rx, y0, rx + 8, y1, ch)); rx += 8
    return {"page_number": 1, "width": width, "height": height,
            "chars": _chars(*chars)}


def test_two_column_reading_order_is_not_interleaved():
    lines = c2l.chars_to_lines_json({"pages": [_two_column_page(rows=8)]})["pages"][0]["lines"]
    texts = [l["text"] for l in lines]
    # THE bug this fixes: no line may contain BOTH a left- and a right-column word
    assert not any("Left" in t and "Right" in t for t in texts), texts
    # reading order: the whole LEFT column (top→bottom) before the RIGHT column
    left = [t for t in texts if "Left" in t]
    right = [t for t in texts if "Right" in t]
    assert texts == left + right, texts               # left column fully, then right
    assert left == [f"LeftLine{r:02d}" for r in range(8)]
    assert right == [f"RightLine{r:02d}" for r in range(8)]


def test_column_split_detected_only_for_two_columns():
    page = _two_column_page(rows=8)
    ph = page["height"]
    items = [{"x0": c["x0"], "x1": c["x1"], "top": ph - c["y1"], "bottom": ph - c["y0"]}
             for c in page["chars"]]
    assert c2l._column_split(items, page["width"]) is not None      # 2-col → a gutter
    # a sparse / single-column page → no split (unchanged behavior)
    assert c2l._column_split(items[:10], page["width"]) is None


def test_line_columns_splits_two_columns_keeps_spanning_whole():
    def it(x0, x1): return {"x0": x0, "x1": x1}
    # a genuine two-column line: big gap at the gutter → split
    line = [it(50, 100), it(360, 410)]
    cols = c2l._line_columns(line, split_x=250, gutter_min=9)
    assert [c for c, _ in cols] == [0, 1]
    # a full-width line that flows across the gutter (adjacent chars) → kept whole
    spanning = [it(50, 248), it(250, 450)]
    cols2 = c2l._line_columns(spanning, split_x=250, gutter_min=9)
    assert len(cols2) == 1 and cols2[0][0] == 0


def test_single_column_page_unchanged():
    # a one-column page: several lines, all chars on the left — must stay in y order
    chars = []
    for r in range(6):
        y1 = 700 - r * 20; y0 = y1 - 10; x = 50
        for ch in f"Body{r}":
            chars.append((x, y0, x + 8, y1, ch)); x += 8
    page = {"page_number": 1, "width": 600, "height": 800, "chars": _chars(*chars)}
    lines = c2l.chars_to_lines_json({"pages": [page]})["pages"][0]["lines"]
    assert [l["text"] for l in lines] == [f"Body{r}" for r in range(6)]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
