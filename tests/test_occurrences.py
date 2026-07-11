"""
occurrences — a clean per-element region list (page + bbox + title) for the
optional external image-enrichment tools (locate an element on the page image by
its region, no content matching). Scoped to REGION-BEARING types (Equation default;
Table/Picture/Diagram opt-in). Deduped inline Formula has no per-object region and
is intentionally excluded.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.occurrences import occurrence_records


def _o(id, t, **props):
    return types.SimpleNamespace(id=id, type=t, props=props)


def _objs():
    return [
        _o("e1", "Equation", flow_index=2, page=21, refnum="(3)", latex="a=b",
           region={"top_left_x": 281, "top_left_y": 818, "width": 717, "height": 62}),
        _o("e2", "Equation", flow_index=4, page=22,
           region={"top_left_x": 100, "top_left_y": 200, "width": 300, "height": 40}),
        _o("f1", "Formula", flow_index=3, latex="\\frac{1}{2}"),   # deduped, no region
        _o("t1", "Table", flow_index=5, page=23,
           region={"top_left_x": 10, "top_left_y": 20, "width": 100, "height": 50}),
    ]


def test_equation_records_carry_title_page_bbox():
    recs = occurrence_records(_objs(), "D")               # default: Equation only
    assert len(recs) == 2                                  # e1, e2 — not f1 (no region)
    r = next(x for x in recs if x["title"] == "D_EQ0001")
    assert r["page"] == 21 and r["type"] == "Equation"
    assert (r["top_left_x"], r["top_left_y"], r["width"], r["height"]) == (281, 818, 717, 62)
    assert r["refnum"] == "(3)" and r["latex"] == "a=b"
    # flow order → EQ0001, EQ0002
    assert {x["title"] for x in recs} == {"D_EQ0001", "D_EQ0002"}


def test_inline_formula_excluded():
    recs = occurrence_records(_objs(), "D", types=("Equation", "Formula"))
    assert all(x["type"] != "Formula" for x in recs)       # no region → excluded


def test_table_opt_in():
    recs = occurrence_records(_objs(), "D", types=("Equation", "Table"))
    tabs = [x for x in recs if x["type"] == "Table"]
    assert len(tabs) == 1 and tabs[0]["title"] == "D_TAB_001"
    assert tabs[0]["width"] == 100


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
