"""
Unit tests for list nesting (pdfdrill.blocks.nest_list_items) — pure, no model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.blocks import (
    nest_list_items, max_depth, count_lists,
    detect_algorithms, algorithm_max_depth,
    resplit_list_items_by_geometry,
)
from docmodel.core import Document, DocObject, Realization
from docmodel.modules.list_items import _split_bullets


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


def test_merged_bullet_line_splits_on_midline_glyphs():
    # OCR merged several bullets onto one line (no linefeed) -> split each.
    assert _split_bullets("• first • second • third") == [
        ("•", "first"), ("•", "second"), ("•", "third")]
    # a single leading dash bullet stays one item ('-' is not split mid-line)
    assert _split_bullets("- evidence supporting the relation") == [
        ("-", "evidence supporting the relation")]
    assert _split_bullets("1. step one") == [("1.", "step one")]
    assert _split_bullets("just prose, no bullet") == []


def test_geometry_resplit_recovers_merged_bullets():
    # One MathPix line whose region spans three pdftotext bullet lines.
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_height": 1000, "page_width": 800}]
    doc.meta["geometry"] = {"body_left_norm": {"1": 0.10}}
    mp = doc.ensure_stream("mathpix_lines")
    merged = mp.append(text="- alpha - beta - gamma", _page=1, type="text",
                       region={"top_left_x": 80, "top_left_y": 300, "width": 600, "height": 90})
    li = DocObject(type="ListItem", props={"marker": "-", "content": "alpha - beta - gamma",
                                           "page": 1, "line_index": 5})
    li.add_realization(Realization(stream="mathpix_lines", start=merged, end=merged, role="surface"))
    doc.add(li)
    # pdftotext separated them by y: 0.30, 0.33, 0.36 (within the region band)
    pl = doc.ensure_stream("pdf_lines")
    for y, txt in [(0.30, "- alpha"), (0.33, "- beta"), (0.39, "- gamma")]:
        pl.append(page=1, y_norm=y, x0_norm=0.10, text=txt)
    pl.append(page=1, y_norm=0.80, x0_norm=0.10, text="- unrelated far away")

    added = resplit_list_items_by_geometry(doc)
    assert added == 2                              # 1 original + 2 new = 3 items
    items = [o for o in doc.objects.values() if o.type == "ListItem"]
    contents = sorted(o.props["content"] for o in items)
    assert contents == ["alpha", "beta", "gamma"]
    assert sum(1 for o in items if o.props.get("provenance") == "geometry_resplit") == 2


def test_geometry_resplit_noop_on_single_line():
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_height": 1000}]
    mp = doc.ensure_stream("mathpix_lines")
    a = mp.append(text="- single item", _page=1, type="text",
                  region={"top_left_y": 300, "height": 20})
    li = DocObject(type="ListItem", props={"marker": "-", "content": "single item", "page": 1})
    li.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    doc.add(li)
    pl = doc.ensure_stream("pdf_lines")
    pl.append(page=1, y_norm=0.30, x0_norm=0.1, text="- single item")
    assert resplit_list_items_by_geometry(doc) == 0


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
