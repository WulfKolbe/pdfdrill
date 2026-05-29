"""
Unit tests for ComparisonHtmlProjector (docops.projectors.comparison_html).

Builds a tiny synthetic Document with one Equation that carries a CDN image
and one that does not, then checks the emitted HTML.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors.comparison_html import ComparisonHtmlProjector


def _doc_with_equations():
    doc = Document()
    doc.meta["bibkey"] = "TESTDOC"
    doc.meta["source_path"] = "/tmp/test.lines.json"
    lines = doc.ensure_stream("mathpix_lines")

    a1 = lines.append(_page=1, _line_index=0, type="equation", text="$$E=mc^2$$")
    eq1 = DocObject(type="Equation", props={
        "latex": "E = mc^2",
        "refnum": "1",
        "page": 1,
        "cdn_url": "https://cdn.mathpix.com/cropped/abc.jpg?height=1&width=2&top_left_y=3&top_left_x=4",
    })
    eq1.add_realization(Realization(stream="mathpix_lines", start=a1, end=a1, role="surface"))
    doc.add(eq1)

    # Equation with no CDN crop — must be skipped from the comparison.
    a2 = lines.append(_page=1, _line_index=1, type="equation", text="$$x+y$$")
    eq2 = DocObject(type="Equation", props={"latex": "x + y", "page": 1, "cdn_url": ""})
    eq2.add_realization(Realization(stream="mathpix_lines", start=a2, end=a2, role="surface"))
    doc.add(eq2)
    return doc


def _project():
    proj = ComparisonHtmlProjector(
        OperatorConfig(op="projector", classname="ComparisonHtmlProjector")
    )
    return proj, proj.project(_doc_with_equations())


def test_only_equations_with_cdn_become_rows():
    proj, _ = _project()
    assert proj.counters.get("rows") == 1


def test_html_contains_latex_katex_and_image():
    _, html_out = _project()
    assert "E = mc^2" in html_out                      # LaTeX source cell
    assert 'data-tex="E = mc^2"' in html_out           # KaTeX render cell
    assert "cdn.mathpix.com/cropped/abc.jpg" in html_out  # MathPix image
    assert "katex.render" in html_out                  # client-side render
    assert "katex.min.css" in html_out
    assert "x + y" not in html_out                     # the cdn-less eq is gone


def test_is_valid_standalone_html():
    _, html_out = _project()
    assert html_out.startswith("<!DOCTYPE html>")
    assert html_out.count("<tr>") == 2  # header row + 1 data row


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
