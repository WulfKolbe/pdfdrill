"""
Unit test for FormulaReportProjector — inline Formula section + display
Equation section with CDN image.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.formula_report import FormulaReportProjector


def _html():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    doc.meta["source_path"] = "/tmp/x.lines.json"
    doc.add(DocObject(type="Formula", props={"latex": "x^2", "flow_index": 0}))
    doc.add(DocObject(type="Formula", props={"latex": "A", "flow_index": 1}))
    doc.add(DocObject(type="Equation", props={
        "latex": "E=mc^2", "equation_number": "(1)", "page": 3,
        "cdn_url": "https://cdn.mathpix.com/cropped/x.jpg", "flow_index": 2}))
    doc.add(DocObject(type="Equation", props={
        "latex": "y=1", "page": 4, "cdn_url": "", "flow_index": 3}))  # no crop
    proj = FormulaReportProjector(
        OperatorConfig(op="projector", classname="FormulaReportProjector"))
    return proj, proj.project(doc)


def test_header_counts_and_sections():
    proj, h = _html()
    assert "<strong>MathExpressions:</strong> 2" in h
    assert "<strong>Equations:</strong> 2" in h
    assert "Inline Math — MathExpression tiddlers (2)" in h
    assert "Display Equations (2)" in h
    assert proj.counters["inline_rows"] == 2
    assert proj.counters["equation_rows"] == 2


def test_inline_rows_have_latex_and_render_span():
    _, h = _html()
    assert "<code>x^2</code>" in h
    assert 'data-latex="x^2" data-display="false"' in h
    assert 'id="DOC_FO0001"' in h


def test_equation_rows_have_cdn_and_eqnum_and_display_render():
    _, h = _html()
    assert 'data-latex="E=mc^2" data-display="true"' in h
    assert "cdn.mathpix.com/cropped/x.jpg" in h
    assert '<span class="eq-num">(1)</span>' in h
    assert 'class="cdn-missing"' in h            # the crop-less equation
    assert "katex.render" in h


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
