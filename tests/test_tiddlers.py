"""
Unit test: equation tiddlers carry the fields a TiddlyWiki <$latex>/<$image>
table macro needs (latex, displayMode, canonical_uri, width, height, refnum)
plus competing readings as latex_<provenance> fields.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector


def _tiddlers():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    e = DocObject(type="Equation", props={
        "latex": "E = mc^2", "refnum": "1", "equation_number": "(1)", "page": 3,
        "cdn_url": "https://cdn.mathpix.com/cropped/abc.jpg?height=80&width=200&top_left_y=10&top_left_x=20",
        "region": {"height": 80, "width": 200, "top_left_x": 20, "top_left_y": 10},
    })
    e.add_realization(Realization(stream="snip", role="latex_candidate",
                                  provenance="snip", score=0.97,
                                  props={"latex": "E=mc^{2}"}))
    doc.add(e)
    proj = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    return json.loads(proj.project(doc))


def test_equation_tiddler_has_macro_fields():
    tids = _tiddlers()
    eq = [t for t in tids if "equation" in t.get("tags", "")]
    assert len(eq) == 1
    t = eq[0]
    assert t["latex"] == "E = mc^2"
    assert t["displayMode"] == "true"
    assert t["refnum"] == "1"
    assert t["canonical_uri"].startswith("https://cdn.mathpix.com/cropped/")
    assert t["width"] == "200" and t["height"] == "80"
    assert t["equation_number"] == "(1)"          # for ||FREF transclusion


def test_fref_template_present():
    tids = _tiddlers()
    fref = [t for t in tids if t.get("title") == "FREF"]
    assert len(fref) == 1
    assert "equation_number" in fref[0]["text"]


def test_competing_readings_become_parallel_fields():
    t = [t for t in _tiddlers() if "equation" in t.get("tags", "")][0]
    assert t["latex_snip"] == "E=mc^{2}"
    assert t["score_snip"] == "0.97"


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
