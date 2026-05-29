"""
Unit tests for the docmodel core extension: Region + provenance/score/region
on Realization, including JSON round-trip.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization, Region


def test_region_from_mathpix():
    r = Region.from_mathpix(
        {"top_left_x": 237, "top_left_y": 2140, "width": 746, "height": 513}, page=2)
    assert (r.page, r.top_left_x, r.top_left_y, r.width, r.height) == (2, 237, 2140, 746, 513)
    assert r.space == "mathpix_image_px"
    assert Region.from_mathpix(None) is None


def test_region_from_cnt_bbox():
    r = Region.from_cnt([[49, 332], [49, 0], [774, 0], [774, 332]], page=6)
    assert (r.top_left_x, r.top_left_y, r.width, r.height) == (49, 0, 725, 332)
    assert r.space == "snip_px"


def test_realization_to_dict_omits_unset_fields():
    d = Realization(stream="mathpix_lines").to_dict()
    assert "provenance" not in d and "score" not in d and "region" not in d


def test_candidate_realization_round_trips():
    doc = Document()
    eq = DocObject(type="Equation", props={"latex": "a+b", "cdn_url": "x"})
    eq.add_realization(Realization(
        stream="snip", role="latex_candidate", provenance="snip", score=0.95,
        props={"latex": "a + b"},
        region=Region.from_cnt([[0, 0], [10, 0], [10, 5], [0, 5]], page=1),
    ))
    doc.add(eq)

    doc2 = Document.from_dict(doc.to_dict())
    e2 = next(iter(doc2.objects.values()))
    cand = [r for r in e2.realizations if r.role == "latex_candidate"][0]
    assert cand.provenance == "snip"
    assert cand.score == 0.95
    assert cand.props["latex"] == "a + b"
    assert cand.region is not None
    assert (cand.region.width, cand.region.height, cand.region.page) == (10, 5, 1)


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
