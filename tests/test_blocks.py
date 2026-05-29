"""
Unit tests for list nesting (pdfdrill.blocks.nest_list_items) — pure, no model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.blocks import (
    nest_list_items, max_depth, count_lists,
    detect_algorithms, algorithm_max_depth,
)


def _items(spec, marker="-"):
    # spec: list of (id, page, line_index, indent)
    return [{"id": i, "page": p, "line_index": li, "indent": ind, "marker": marker}
            for (i, p, li, ind) in spec]


def test_flat_list_one_level():
    roots = nest_list_items(_items([
        ("a", 1, 1, 0.00), ("b", 1, 2, 0.00), ("c", 1, 3, 0.00)]))
    assert count_lists(roots) == 1
    assert max_depth(roots) == 1
    lst = roots[0]["node"]
    assert [c["id"] for c in lst["children"] if c["kind"] == "item"] == ["a", "b", "c"]


def test_nested_sublist_by_indentation():
    # b,c are indented under a; d returns to the outer level
    roots = nest_list_items(_items([
        ("a", 1, 1, 0.00),
        ("b", 1, 2, 0.06),
        ("c", 1, 3, 0.06),
        ("d", 1, 4, 0.00)]))
    assert max_depth(roots) == 2
    outer = roots[0]["node"]
    kinds = [c["kind"] for c in outer["children"]]
    assert kinds == ["item", "list", "item"]            # a, [sublist], d
    sub = [c for c in outer["children"] if c["kind"] == "list"][0]["node"]
    assert [c["id"] for c in sub["children"]] == ["b", "c"]


def test_moderate_gaps_bridge_same_family():
    # Checklist-style: same bullet family, items separated by answer paragraphs
    # (moderate line gaps) stay ONE list; a page change still splits.
    roots = nest_list_items(_items([
        ("a", 1, 1, 0.0), ("b", 1, 12, 0.0), ("c", 1, 25, 0.0),  # one list
        ("d", 2, 1, 0.0)]))                                       # page -> new list
    assert count_lists(roots) == 2
    first = roots[0]["node"]
    assert [c["id"] for c in first["children"] if c["kind"] == "item"] == ["a", "b", "c"]


def test_marker_family_change_splits():
    items = _items([("a", 1, 1, 0.0), ("b", 1, 2, 0.0)], marker="-")
    items += _items([("c", 1, 3, 0.0), ("d", 1, 4, 0.0)], marker="1.")
    roots = nest_list_items(items)
    assert count_lists(roots) == 2          # bullet list, then numbered list


def test_huge_gap_splits():
    roots = nest_list_items(_items([("a", 1, 1, 0.0), ("b", 1, 80, 0.0)]))
    assert count_lists(roots) == 2


def test_missing_indent_defaults_flat():
    roots = nest_list_items([
        {"id": "a", "page": 1, "line_index": 1, "indent": None, "marker": "-"},
        {"id": "b", "page": 1, "line_index": 2, "indent": None, "marker": "-"}])
    assert count_lists(roots) == 1 and max_depth(roots) == 1


def test_detect_algorithms_caption_and_indent_depth():
    # Mirrors the real 2312.11532 shape: caption + Require at base x, body at
    # deeper x, nested if-block deeper still, back out for end if.
    lines = [
        {"id": 0, "page": 3, "line_index": 0, "text": "Algorithm 1: Pseudo-code of TVQ-VAE", "x": 1104},
        {"id": 1, "page": 3, "line_index": 1, "text": "Require: topics beta", "x": 1104},
        {"id": 2, "page": 3, "line_index": 2, "text": "Sample theta_d", "x": 1164},
        {"id": 3, "page": 3, "line_index": 3, "text": "if document analysis then", "x": 1164},
        {"id": 4, "page": 3, "line_index": 4, "text": "Sample z_dn", "x": 1198},
        {"id": 5, "page": 3, "line_index": 5, "text": "end if", "x": 1164},
    ]
    algos = detect_algorithms(lines)
    assert len(algos) == 1
    a = algos[0]
    assert a["number"] == 1
    assert "TVQ-VAE" in a["title"]
    assert a["caption_id"] == 0
    assert len(a["steps"]) == 5                  # caption excluded from steps
    depths = [s["depth"] for s in a["steps"]]
    # Require@1104->0, Sample theta@1164->1, if@1164->1, Sample z_dn@1198->2, end if@1164->1
    assert depths == [0, 1, 1, 2, 1]
    assert algorithm_max_depth(algos) == 2


def test_two_algorithms_split_on_caption():
    lines = [
        {"id": 0, "page": 1, "line_index": 0, "text": "Algorithm 1: A", "x": 100},
        {"id": 1, "page": 1, "line_index": 1, "text": "step", "x": 120},
        {"id": 2, "page": 2, "line_index": 0, "text": "Algorithm 2: B", "x": 100},
        {"id": 3, "page": 2, "line_index": 1, "text": "step", "x": 120},
    ]
    algos = detect_algorithms(lines)
    assert [a["number"] for a in algos] == [1, 2]
    assert all(len(a["steps"]) == 1 for a in algos)


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
