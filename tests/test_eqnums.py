"""
Unit tests for equation-number fusion (pdfdrill.eqnums).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill.eqnums import fuse_equation_numbers


def _doc():
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_height": 1000, "page_width": 800}]
    mp = doc.ensure_stream("mathpix_lines")
    # eq A: MathPix already gave refnum "3"
    a = mp.append(text="x=1", _page=1,
                  region={"top_left_x": 100, "top_left_y": 200, "width": 300, "height": 40})
    eqA = DocObject(type="Equation", props={"latex": "x=1", "refnum": "3", "page": 1,
                                            "region": {"top_left_y": 200, "height": 40},
                                            "cdn_url": "u"})
    eqA.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    doc.add(eqA)
    # eq B: no refnum; a right-margin "(5)" sits at its vertical center (y~0.52)
    b = mp.append(text="y=2", _page=1,
                  region={"top_left_x": 100, "top_left_y": 500, "width": 300, "height": 40})
    eqB = DocObject(type="Equation", props={"latex": "y=2", "page": 1,
                                            "region": {"top_left_y": 500, "height": 40},
                                            "cdn_url": "u"})
    eqB.add_realization(Realization(stream="mathpix_lines", start=b, end=b, role="surface"))
    doc.add(eqB)
    # pdf_lines: a right-margin number token "(5)" near y_norm 0.52
    pl = doc.ensure_stream("pdf_lines")
    pl.append(text="(5)", page=1, x0_norm=0.92, x1_norm=0.96, y_norm=0.52)
    pl.append(text="some body text", page=1, x0_norm=0.12, y_norm=0.30)
    return doc, eqA, eqB


def test_mathpix_number_normalized_to_parens():
    doc, eqA, eqB = _doc()
    stats = fuse_equation_numbers(doc)
    assert eqA.props["equation_number"] == "(3)"
    assert stats["from_mathpix"] == 1


def test_missing_number_recovered_from_margin_geometry():
    doc, eqA, eqB = _doc()
    stats = fuse_equation_numbers(doc)
    assert eqB.props.get("refnum") == "5"
    assert eqB.props.get("equation_number") == "(5)"
    assert stats["recovered"] == 1
    assert any(a.kind == "equation_number" for a in doc.alignments)


def test_far_number_not_matched():
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_height": 1000, "page_width": 800}]
    mp = doc.ensure_stream("mathpix_lines")
    a = mp.append(text="z=3", _page=1, region={"top_left_y": 100, "height": 20})
    eq = DocObject(type="Equation", props={"latex": "z=3", "page": 1,
                                           "region": {"top_left_y": 100, "height": 20}, "cdn_url": "u"})
    eq.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    doc.add(eq)
    pl = doc.ensure_stream("pdf_lines")
    pl.append(text="(9)", page=1, x0_norm=0.92, y_norm=0.90)   # far away
    stats = fuse_equation_numbers(doc)
    assert stats["recovered"] == 0
    assert "equation_number" not in eq.props


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
