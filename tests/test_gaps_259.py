"""259 — the four gaps the audits named, closed and measured.

Two of the four were not gaps. `molecule` was already claimed by
PictureProcessor's inline path, and `code` was 97.5% recovered as a Diagram's
`code` prop. The type contract said both were dropped entirely; 259 corrects it
and closes what is actually missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.mathpix import crop_region, quad, quad_bbox, is_axis_aligned
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.header import HeaderProcessor, levels_by_font_size
from docmodel.modules.code_listing import CodeProcessor
from docmodel.modules.picture import PictureProcessor
from docmodel.modules.table import _CELL_TYPES


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _doc(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "im-01", "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    return doc


# ---- gap 1: code -> CodeListing --------------------------------------------

def test_a_code_run_becomes_one_listing_with_mathpix_text_verbatim():
    doc = _doc([
        {"type": "code", "text": "\n```julia\nfunction f(x)"},
        {"type": "code", "text": "\n    return x + 1"},
        {"type": "code", "text": "\nend\n```\n"},
    ])
    m = _mod(CodeProcessor)
    m.process_document(doc)
    obj = doc.objects_of_type("CodeListing")[0]
    assert obj.props["code"] == "function f(x)\n    return x + 1\nend"
    assert obj.props["language"] == "julia"
    assert obj.props["line_count"] == 3


def test_indentation_is_content_and_survives():
    doc = _doc([{"type": "code", "text": "\n        deeply_indented()"}])
    _mod(CodeProcessor).process_document(doc)
    assert doc.objects_of_type("CodeListing")[0].props["code"] == "        deeply_indented()"


def test_a_blank_interior_line_is_content_and_survives():
    doc = _doc([
        {"type": "code", "text": "\nfirst()"},
        {"type": "code", "text": "\n"},
        {"type": "code", "text": "\nsecond()"},
    ])
    _mod(CodeProcessor).process_document(doc)
    assert doc.objects_of_type("CodeListing")[0].props["code"] == "first()\n\nsecond()"


def test_two_runs_separated_by_prose_are_two_listings():
    doc = _doc([
        {"type": "code", "text": "\nfirst()"},
        {"type": "text", "text": "and then"},
        {"type": "code", "text": "\nsecond()"},
    ])
    _mod(CodeProcessor).process_document(doc)
    assert [o.props["code"] for o in doc.objects_of_type("CodeListing")] == ["first()", "second()"]


def test_the_parent_is_recorded_because_43933_lines_sit_under_a_diagram():
    doc = _doc([
        {"id": "d", "type": "diagram", "text": "", "children_ids": ["c"]},
        {"id": "c", "type": "code", "text": "\nx = 1", "parent_id": "d"},
    ])
    _mod(CodeProcessor).process_document(doc)
    obj = doc.objects_of_type("CodeListing")[0]
    assert obj.props["parent_id"] == "d"
    assert obj.props["parent_type"] == "diagram"


def test_a_run_of_nothing_but_fences_creates_no_object():
    doc = _doc([{"type": "code", "text": "\n```\n```\n"}])
    _mod(CodeProcessor).process_document(doc)
    assert doc.objects_of_type("CodeListing") == []


def test_code_breaks_a_paragraph():
    from docmodel.modules.paragraph import _BREAK_TYPES
    assert "code" in _BREAK_TYPES


# ---- gap 2: cnt, the true quadrilateral ------------------------------------

_UPRIGHT = [[10, 20], [110, 20], [110, 50], [10, 50]]
_SKEW = [[1214, 504], [1324, 703], [1306, 719], [1189, 522]]


def test_an_upright_quad_leaves_the_crop_alone():
    region = {"top_left_x": 9, "top_left_y": 19, "width": 102, "height": 32}
    assert crop_region({"cnt": _UPRIGHT, "region": region}) == region


def test_a_line_with_no_cnt_falls_back_to_region_unchanged():
    region = {"top_left_x": 1, "top_left_y": 2, "width": 3, "height": 4}
    assert crop_region({"region": region}) == region
    assert crop_region({}) == {}


def test_a_skewed_quad_tightens_the_crop():
    # The rectangle MathPix gives is wider than the rotated text inside it.
    region = {"top_left_x": 1100, "top_left_y": 450, "width": 300, "height": 320}
    out = crop_region({"cnt": _SKEW, "region": region})
    assert out == quad_bbox(_SKEW)
    assert out["width"] * out["height"] < region["width"] * region["height"]


def test_a_skewed_quad_does_not_widen_a_crop_that_is_already_tighter():
    tight = {"top_left_x": 1200, "top_left_y": 505, "width": 10, "height": 10}
    assert crop_region({"cnt": _SKEW, "region": tight}) == tight


@pytest.mark.parametrize("bad", [None, [], [[1, 2]], [[1, 2], [3, 4], [5, 6]], "x"])
def test_a_malformed_cnt_is_ignored_not_crashed_on(bad):
    region = {"top_left_x": 0, "top_left_y": 0, "width": 5, "height": 5}
    assert quad({"cnt": bad}) == []
    assert crop_region({"cnt": bad, "region": region}) == region


def test_the_quad_is_carried_only_when_it_says_something_a_box_cannot():
    from docmodel.modules.diagram import DiagramProcessor
    up = _doc([{"type": "diagram", "text": "![](http://cdn/x.jpg)", "cnt": _UPRIGHT,
                "region": {"top_left_x": 10, "top_left_y": 20, "width": 100, "height": 30}}])
    assert _mod(DiagramProcessor).find_items(up)[0]["quad"] == []
    sk = _doc([{"type": "diagram", "text": "![](http://cdn/x.jpg)", "cnt": _SKEW,
                "region": {"top_left_x": 1100, "top_left_y": 450, "width": 300, "height": 320}}])
    assert _mod(DiagramProcessor).find_items(sk)[0]["quad"] == _SKEW


def test_is_axis_aligned_reads_the_corners_not_the_order():
    assert is_axis_aligned(_UPRIGHT)
    assert is_axis_aligned([])
    assert not is_axis_aligned(_SKEW)


# ---- gap 3: font_size -> header level --------------------------------------

def test_levels_rank_within_the_document_largest_first():
    assert levels_by_font_size([31, 39, 29, 39]) == {39: 1, 31: 2, 29: 3}


def test_more_than_five_sizes_collapse_into_the_deepest_level():
    # 7% of documents; the cap matches _LEVEL's own range.
    got = levels_by_font_size([70, 60, 50, 40, 30, 20, 10])
    assert got[70] == 1 and got[30] == 5 and got[10] == 5


def test_sizes_that_are_absent_or_junk_are_ignored():
    assert levels_by_font_size([None, 0, -3, "big", 40]) == {40: 1}


def _header(display, size):
    return _doc([
        {"id": "h", "type": "section_header", "children_ids": ["hc"], "font_size": size},
        {"id": "hc", "type": "text", "text": "The Caption", "text_display": display},
    ])


def test_the_latex_command_still_wins_over_font_size():
    # The author's own statement of depth beats an inference from pixel height.
    item = _mod(HeaderProcessor).find_items(_header(r"\subsubsection*{The Caption}", 60))[0]
    assert item["level"] == 3
    assert item["level_basis"] == "latex_command"


def test_font_size_sets_the_level_when_no_command_is_present():
    doc = _doc([
        {"id": "h1", "type": "section_header", "children_ids": ["c1"], "font_size": 40},
        {"id": "c1", "type": "text", "text": "Big", "text_display": "Big"},
        {"id": "h2", "type": "section_header", "children_ids": ["c2"], "font_size": 20},
        {"id": "c2", "type": "text", "text": "Small", "text_display": "Small"},
    ])
    items = _mod(HeaderProcessor).find_items(doc)
    assert [(i["level"], i["level_basis"]) for i in items] == \
           [(1, "font_size"), (2, "font_size")]


def test_no_command_and_no_font_size_keeps_the_old_level_1():
    item = _mod(HeaderProcessor).find_items(_header("The Caption", None))[0]
    assert item["level"] == 1
    assert item["level_basis"] == "default"


# ---- gap 4: table_split_cell, and molecule which was never a gap -----------

def test_table_split_cell_is_a_cell_type():
    assert "table_split_cell" in _CELL_TYPES


def test_a_backslashbox_corner_cell_is_collected():
    from docmodel.modules.table import TableProcessor
    # All 10 corpus split cells are DIRECT children of the table and are listed
    # in its children_ids — checked, because _collect_children does not recurse.
    doc = _doc([
        {"id": "t", "type": "table", "children_ids": ["r", "c1", "c2"]},
        {"id": "r", "type": "table_row", "parent_id": "t"},
        {"id": "c1", "type": "table_split_cell", "parent_id": "t",
         "text": r"\backslashbox{Publication Type}{Language}"},
        {"id": "c2", "type": "simple_cell", "parent_id": "t", "text": "German"},
    ])
    items = _mod(TableProcessor).find_items(doc)
    texts = [ch["text"] for it in items for ch in (it.get("children") or [])]
    assert any("backslashbox" in t for t in texts), \
        "the corner cell of a cross-tabulation must not be dropped"


def test_molecule_was_already_claimed_by_the_inline_picture_path():
    # All 10 corpus lines carry a plain Markdown CDN link, which _from_inline
    # has always matched. The contract's GAP entry was wrong.
    doc = _doc([{"type": "molecule",
                 "text": "\n![](https://cdn.mathpix.com/cropped/a-414.jpg"
                         "?height=146&width=291&top_left_y=1&top_left_x=2)"}])
    items = _mod(PictureProcessor).find_items(doc)
    assert len(items) == 1
    assert items[0]["from_line_type"] == "molecule"


def test_each_listing_keeps_its_own_anchors():
    """The run list is reused across runs; handing it over by reference gave
    every listing but the last the NEXT one's anchors, and emptied the last."""
    doc = _doc([
        {"id": "a", "type": "code", "text": "\nfirst()"},
        {"id": "b", "type": "text", "text": "prose"},
        {"id": "c", "type": "code", "text": "\nsecond()"},
        {"id": "d", "type": "text", "text": "more prose"},
        {"id": "e", "type": "code", "text": "\nthird()"},
    ])
    m = _mod(CodeProcessor)
    items = m.find_items(doc)
    assert [len(i["anchors"]) for i in items] == [1, 1, 1]
    assert len({id(i["anchors"]) for i in items}) == 3, "the same list was reused"
    m.process_document(doc)
    objs = doc.objects_of_type("CodeListing")
    assert len(objs) == 3
    stream = doc.stream("mathpix_lines")
    for obj, expected in zip(objs, ["first()", "second()", "third()"]):
        r = obj.realizations[0]
        assert stream.payload[r.start]["text"].strip() == expected


# ---- 262: a Toc is derived, and each projection chooses ---------------------

def test_a_toc_object_is_marked_derived():
    from docmodel.modules.toc import TocProcessor
    from docops.projectors.common import is_derived
    doc = _doc([
        {"id": "c", "type": "table_of_contents_container", "children_ids": ["r"]},
        {"id": "r", "type": "table_of_contents_row", "parent_id": "c",
         "text": "Chapter 1 ..... 7"},
    ])
    m = _mod(TocProcessor)
    m.process_document(doc)
    toc = doc.objects_of_type("Toc")[0]
    assert toc.props["derived"] is True
    assert toc.props["derived_from"] == "section_header"
    assert is_derived(toc)


def test_is_derived_is_false_for_everything_else():
    from docops.projectors.common import is_derived
    from docmodel.core import DocObject
    assert not is_derived(DocObject(type="Paragraph", props={"text": "x"}))
    assert not is_derived(DocObject(type="Abstract", props={"text": "x"}))


# ---- 263: the dot leader is not part of the title --------------------------

@pytest.mark.parametrize("raw,title,loc", [
    (r"1.1. Cayley algebra \(\mathfrak{C}\)  ..... 1",
     r"1.1. Cayley algebra \(\mathfrak{C}\)", "1"),
    ("..... 1", "", "1"),                       # a table_of_contents_number line
    ("Preface ....... xiv", "Preface", "xiv"),  # roman page number
    ("Terminology ..... 3.1.2.1", "Terminology", "3.1.2.1"),  # section locator
    ("Results .... 12a", "Results", "12a"),
    ("Appendix ..... 200-204", "Appendix", "200-204"),
    ("A Title With No Leader", "A Title With No Leader", ""),
    ("", "", ""),
])
def test_split_leader(raw, title, loc):
    from docmodel.modules.toc import split_leader
    assert split_leader(raw) == (title, loc)


def test_a_multiline_row_keeps_its_authors_and_lifts_the_page_number():
    # 948 corpus rows read "Title ..... 57 \n Authors". Stripping the leader
    # without lifting the number welds it into the title.
    from docmodel.modules.toc import split_leader
    title, loc = split_leader(
        "Discrete Complex Analysis on Planar Quad-Graphs  ..... 57 \n"
        "Alexander I. Bobenko and Felix Günther")
    assert loc == "57"
    assert title == ("Discrete Complex Analysis on Planar Quad-Graphs\n"
                     "Alexander I. Bobenko and Felix Günther")
    assert ".." not in title


def test_no_leader_survives_into_any_title():
    from docmodel.modules.toc import split_leader
    for raw in ("X ..... 1", "..... 9", "Y .. z", "A ... B ... 4"):
        assert ".." not in split_leader(raw)[0]


def test_the_model_carries_title_locator_and_raw():
    from docmodel.modules.toc import TocProcessor
    doc = _doc([
        {"id": "r", "type": "table_of_contents_row", "text": "Chapter 1 ..... 7"},
        {"id": "n", "type": "table_of_contents_number", "text": "..... 7"},
    ])
    m = _mod(TocProcessor)
    m.process_document(doc)
    toc = doc.objects_of_type("Toc")[0]
    assert toc.props["entries"] == ["Chapter 1"]        # the number line drops out
    assert toc.props["rows"] == [
        {"title": "Chapter 1", "locator": "7", "raw": "Chapter 1 ..... 7",
         "line_type": "table_of_contents_row"},
        {"title": "", "locator": "7", "raw": "..... 7",
         "line_type": "table_of_contents_number"},
    ]


# ---- 264: a bibkey rename is recorded, so crops can still be found ---------

def test_crop_file_finds_the_crop_under_an_earlier_bibkey(tmp_path):
    from pdfdrill.report_tex import crop_file
    crops = tmp_path / "report-crops"
    crops.mkdir()
    (crops / "oldkey_EQ0001.jpg").write_bytes(b"x" * 800)
    # Renamed model: title now carries the new key, the file still the old one.
    assert crop_file(crops, "newkey_EQ0001", "newkey", ["oldkey"]) == \
        crops / "oldkey_EQ0001.jpg"


def test_crop_file_prefers_the_current_name(tmp_path):
    from pdfdrill.report_tex import crop_file
    crops = tmp_path / "c"; crops.mkdir()
    (crops / "oldkey_EQ0001.jpg").write_bytes(b"x" * 800)
    (crops / "newkey_EQ0001.jpg").write_bytes(b"y" * 800)
    assert crop_file(crops, "newkey_EQ0001", "newkey", ["oldkey"]) == \
        crops / "newkey_EQ0001.jpg"


def test_crop_file_follows_a_sanitised_earlier_key(tmp_path):
    # The prior key had a space; the file on disk carries the sanitised form.
    from pdfdrill.report_tex import crop_file
    crops = tmp_path / "c"; crops.mkdir()
    (crops / "0111016__1__EQ0002.jpg").write_bytes(b"x" * 800)
    assert crop_file(crops, "k_EQ0002", "k", ["0111016 (1)"]) == \
        crops / "0111016__1__EQ0002.jpg"


def test_crop_file_without_history_behaves_exactly_as_before(tmp_path):
    from pdfdrill.report_tex import crop_file
    crops = tmp_path / "c"; crops.mkdir()
    (crops / "oldkey_EQ0001.jpg").write_bytes(b"x" * 800)
    assert crop_file(crops, "newkey_EQ0001", "newkey", None) is None
    assert crop_file(crops, "newkey_EQ0001", "newkey", []) is None
    assert crop_file(None, "x", "k", ["o"]) is None


def test_a_truncated_crop_is_not_accepted(tmp_path):
    from pdfdrill.report_tex import crop_file
    crops = tmp_path / "c"; crops.mkdir()
    (crops / "k_EQ0001.jpg").write_bytes(b"x" * 100)   # < 500 bytes
    assert crop_file(crops, "k_EQ0001", "k", []) is None


# ---- 265: a header without children is still a header ----------------------

def test_a_childless_header_becomes_a_section():
    """34,126 of the corpus's 43,160 section_header lines have no children and
    were dropped outright — 79% of every heading, in 629 documents that ended
    up with no Section object at all."""
    from docmodel.modules.header import HeaderProcessor
    doc = _doc([{"id": "h", "type": "section_header", "font_size": 46,
                 "text": "REFERENCES",
                 "text_display": "\n\n\\section*{REFERENCES}"}])
    items = _mod(HeaderProcessor).find_items(doc)
    assert len(items) == 1
    assert items[0]["caption"] == "REFERENCES"
    assert items[0]["cmd"] == "section"
    assert items[0]["level"] == 1
    assert items[0]["level_basis"] == "latex_command"


def test_a_childless_subsection_keeps_its_depth():
    from docmodel.modules.header import HeaderProcessor
    doc = _doc([{"id": "h", "type": "section_header",
                 "text": "2.1 Method",
                 "text_display": "\\subsection*{2.1 Method}"}])
    assert _mod(HeaderProcessor).find_items(doc)[0]["level"] == 2


def test_the_child_still_wins_when_there_is_one():
    from docmodel.modules.header import HeaderProcessor
    doc = _doc([
        {"id": "h", "type": "section_header", "children_ids": ["c"],
         "text": "ignored", "text_display": "\\section*{ignored}"},
        {"id": "c", "type": "text", "text": "Real Caption",
         "text_display": "\\subsection*{Real Caption}"},
    ])
    item = _mod(HeaderProcessor).find_items(doc)[0]
    assert item["caption"] == "Real Caption"
    assert item["level"] == 2


def test_a_header_with_no_text_at_all_is_still_skipped():
    from docmodel.modules.header import HeaderProcessor
    doc = _doc([{"id": "h", "type": "section_header", "text": "  ",
                 "text_display": ""}])
    assert _mod(HeaderProcessor).find_items(doc) == []
