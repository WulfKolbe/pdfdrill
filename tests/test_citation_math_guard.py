"""
Regression: a bracketed/parenthetical group INSIDE a math span is math (an
interval/set/index), not a citation. Bug — `\\([A x, B x]\\)` (MathPix's render
of the interval `[A_x, B_x]`) produced two bogus `A x`/`B x` Citations, which
then leaked into a synthetic FOX formula's LaTeX as `{{...||CIT}}` transclusions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.citation import CitationProcessor
from docmodel.base_module import ModuleConfig
from pdfdrill import bibliography as B


def _mod(cls, bibkey="T"):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), bibkey)


def _doc(line_text):
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "l1", "type": "text", "text": line_text, "text_display": line_text}]}]})
    return doc


def test_bracket_in_math_is_not_a_citation():
    doc = _doc(r"truth value, which we can denote by \([A x, B x]\). See [Smith2020] too.")
    _mod(CitationProcessor).process_document(doc)
    keys = {o.props.get("citekey") for o in doc.objects_of_type("Citation")}
    assert "A x" not in keys and "B x" not in keys     # inside \(...\) -> math
    assert "Smith2020" in keys                          # outside math -> real cite


def test_citation_outside_math_still_detected():
    doc = _doc(r"As shown in [Awo10] and [BB17], the result holds.")
    _mod(CitationProcessor).process_document(doc)
    keys = {o.props.get("citekey") for o in doc.objects_of_type("Citation")}
    assert {"Awo10", "BB17"} <= keys


def test_numeric_cite_inside_math_skipped():
    # `[1,2]` inside \(...\) is an index/range, not a numeric citation.
    doc = _doc(r"the entry \(M[1,2]\) and reference [3] of the list.")
    added = B.detect_numeric_citations(doc, max_num=10)
    nums = sorted(o.props.get("number") for o in doc.objects_of_type("Citation"))
    assert 3 in nums and 1 not in nums and 2 not in nums


if __name__ == "__main__":
    for fn in [test_bracket_in_math_is_not_a_citation,
               test_citation_outside_math_still_detected,
               test_numeric_cite_inside_math_skipped]:
        fn(); print(f"PASS {fn.__name__}")
    print("\nAll tests passed.")
