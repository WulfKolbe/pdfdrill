"""
Unified out-of-column geometry — source-independent (works on MathPix AND OCR
line regions, both shaped {top_left_x, top_left_y, width, height}).

Commercial/scientific documents print continuity numbers, control keys and page
numbers OUTSIDE the body column (left/right margin). MathPix tags these
type='column' (→ generic Sidenote); the OCR path dropped the signal entirely.
This computes the body column from the line regions themselves, flags the
out-of-column lines, and types each margin item — so a "footnote that is really a
key" becomes a first-class, queryable confirmation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.geometry_columns import (MarginRole, body_column, out_of_column,
                                       classify_margin_item, tag_out_of_column)


def _reg(x, w, y=100, h=20):
    return {"top_left_x": x, "top_left_y": y, "width": w, "height": h}


def test_body_column_from_wide_body_lines():
    # five wide body lines (x 80..520) + two narrow margin items
    regions = [_reg(80, 440, y=100 + 20 * i) for i in range(5)]
    regions += [_reg(20, 30), _reg(560, 40)]      # left + right margin
    left, right = body_column(regions)
    assert 70 <= left <= 90 and 510 <= right <= 530


def test_out_of_column_detects_left_right_and_body():
    body = (80.0, 520.0)
    assert out_of_column(_reg(560, 40), body) == "right"
    assert out_of_column(_reg(20, 30), body) == "left"
    assert out_of_column(_reg(120, 300), body) is None       # inside the column


def test_classify_margin_item():
    assert classify_margin_item("Seite 2 von 6") == MarginRole.CONTINUITY
    assert classify_margin_item("Fortsetzung Seite 3") == MarginRole.CONTINUITY
    assert classify_margin_item("Seite 3") == MarginRole.PAGE_NUMBER
    assert classify_margin_item("12") == MarginRole.PAGE_NUMBER
    assert classify_margin_item("Kassenzeichen 725.356.194.433") == MarginRole.CONTROL_NUMBER
    assert classify_margin_item("725.356.194.433") == MarginRole.CONTROL_NUMBER
    assert classify_margin_item("Kundennummer 000888035") == MarginRole.CONTROL_NUMBER
    assert classify_margin_item("Anlage") == MarginRole.LABEL


def test_tag_out_of_column_marks_margin_lines_with_role():
    lines = [{"text": "gerne informieren wir Sie über Ihre Versicherung für 2026",
              "region": _reg(80, 440, y=200)},
             {"text": "weitere Angaben zu Ihrer Police und den Bedingungen hier",
              "region": _reg(80, 440, y=220)},
             {"text": "Seite 2 von 6", "region": _reg(560, 60, y=30)},
             {"text": "725.356.194.433", "region": _reg(15, 50, y=400)}]
    tagged = tag_out_of_column(lines)
    by_text = {l["text"]: l for l in tagged}
    assert by_text["Seite 2 von 6"]["out_of_column"] == "right"
    assert by_text["Seite 2 von 6"]["margin_role"] == MarginRole.CONTINUITY.value
    assert by_text["725.356.194.433"]["out_of_column"] == "left"
    assert by_text["725.356.194.433"]["margin_role"] == MarginRole.CONTROL_NUMBER.value
    # body lines are not flagged
    assert by_text["gerne informieren wir Sie über Ihre Versicherung für 2026"].get("out_of_column") is None


def test_ocr_lines_json_tags_out_of_column_margin():
    """OCR↔MathPix parity: the tesseract lines.json assembler now flags
    out-of-column margin lines (the signal it used to drop)."""
    from pdfdrill.ocr_lines import lines_json_from_words
    words = []
    for ln, y in [(1, 100), (2, 130)]:
        for i, x in enumerate(range(80, 520, 60)):
            words.append({"page": 1, "block": 1, "line": ln, "x0": x, "y0": y,
                          "x1": x + 55, "y1": y + 18, "text": f"word{ln}{i}"})
    for t, x in [("Seite", 600), ("2", 660), ("von", 700), ("6", 760)]:
        words.append({"page": 1, "block": 2, "line": 1, "x0": x, "y0": 40,
                      "x1": x + 40, "y1": 58, "text": t})
    lj = lines_json_from_words(words, {1: (850, 1000)})
    lines = lj["pages"][0]["lines"]
    margin = [l for l in lines if l.get("out_of_column")]
    assert margin and any(l.get("margin_role") == "continuity" for l in margin)
    assert all(not l.get("out_of_column") for l in lines if l["text"].startswith("word"))


if __name__ == "__main__":
    test_body_column_from_wide_body_lines(); print("PASS body_column")
    test_ocr_lines_json_tags_out_of_column_margin(); print("PASS ocr-parity")
    test_out_of_column_detects_left_right_and_body(); print("PASS out_of_column")
    test_classify_margin_item(); print("PASS classify")
    test_tag_out_of_column_marks_margin_lines_with_role(); print("PASS tag")
    print("\nAll tests passed.")
