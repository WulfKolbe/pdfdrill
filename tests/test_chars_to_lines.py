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
