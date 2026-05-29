"""
Unit tests for list nesting (pdfdrill.blocks.nest_list_items) — pure, no model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.blocks import nest_list_items, max_depth, count_lists


def _items(spec):
    # spec: list of (id, page, line_index, indent)
    return [{"id": i, "page": p, "line_index": li, "indent": ind, "marker": "-"}
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


def test_separate_runs_split_by_page_or_gap():
    roots = nest_list_items(_items([
        ("a", 1, 1, 0.0), ("b", 1, 2, 0.0),    # run 1
        ("c", 1, 20, 0.0),                       # line gap -> run 2
        ("d", 2, 1, 0.0)]))                      # page change -> run 3
    assert count_lists(roots) == 3
    assert max_depth(roots) == 1


def test_missing_indent_defaults_flat():
    roots = nest_list_items([
        {"id": "a", "page": 1, "line_index": 1, "indent": None, "marker": "-"},
        {"id": "b", "page": 1, "line_index": 2, "indent": None, "marker": "-"}])
    assert count_lists(roots) == 1 and max_depth(roots) == 1


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
