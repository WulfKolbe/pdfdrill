"""
Regression: equation numbers matched by page + y-position, not stream order.

MathPix often emits all of a page's `math` lines first, then all its
`equation_number` lines — so a +-N stream-index window only catches the first
equation per page. This left 12/13 equations of arXiv 2312.11532 unnumbered
(incl. eq 9) when running `pdfdrill model` alone. EquationProcessor must pair
each equation with the same-page equation_number whose region y-center is
closest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.equation import EquationProcessor
from docmodel.base_module import ModuleConfig


def _cfg(name):
    return ModuleConfig(title=name, type="application/python", classname=name)


def _build(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, lines)
    PageProcessor(_cfg("PageProcessor"), "T").process_document(doc)
    EquationProcessor(_cfg("EquationProcessor"), "T").process_document(doc)
    return sorted((o for o in doc.objects.values() if o.type == "Equation"),
                  key=lambda o: o.props["region"]["top_left_y"])


def test_numbers_matched_when_grouped_after_math():
    # 3 math lines first, then 3 equation_number lines (MathPix's grouping):
    # a +-3 stream window only reaches the first; y-matching gets all three.
    lines = {"pages": [{
        "page": 1, "image_id": "img", "page_height": 1000, "page_width": 800,
        "lines": [
            {"text": "a=1", "type": "math",
             "region": {"top_left_x": 100, "top_left_y": 100, "width": 200, "height": 20}},
            {"text": "b=2", "type": "math",
             "region": {"top_left_x": 100, "top_left_y": 200, "width": 200, "height": 20}},
            {"text": "c=3", "type": "math",
             "region": {"top_left_x": 100, "top_left_y": 300, "width": 200, "height": 20}},
            {"text": "(1)", "type": "equation_number",
             "region": {"top_left_x": 700, "top_left_y": 102, "width": 30, "height": 18}},
            {"text": "(2)", "type": "equation_number",
             "region": {"top_left_x": 700, "top_left_y": 202, "width": 30, "height": 18}},
            {"text": "(3)", "type": "equation_number",
             "region": {"top_left_x": 700, "top_left_y": 302, "width": 30, "height": 18}},
        ],
    }]}
    assert [e.props.get("refnum") for e in _build(lines)] == ["1", "2", "3"]


def test_each_number_used_once():
    lines = {"pages": [{
        "page": 1, "image_id": "img", "page_height": 1000, "page_width": 800,
        "lines": [
            {"text": "x", "type": "math",
             "region": {"top_left_x": 100, "top_left_y": 100, "width": 50, "height": 20}},
            {"text": "y", "type": "math",
             "region": {"top_left_x": 100, "top_left_y": 130, "width": 50, "height": 20}},
            {"text": "(7)", "type": "equation_number",
             "region": {"top_left_x": 700, "top_left_y": 101, "width": 30, "height": 18}},
            {"text": "(8)", "type": "equation_number",
             "region": {"top_left_x": 700, "top_left_y": 131, "width": 30, "height": 18}},
        ],
    }]}
    assert [e.props.get("refnum") for e in _build(lines)] == ["7", "8"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
