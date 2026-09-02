"""506 — the section-path gate."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import sectionpath as sp


TABLE = {"usable": True, "pages": 100, "density": 0.5,
         "entries": [(10, "1", "Vectors"), (30, "1.2", "Bases"),
                     (60, "2", "Matrices")]}


def test_the_path_is_the_deepest_entry_at_or_before_the_page():
    assert sp.path_for(TABLE, 31)["number"] == "1.2"
    assert sp.path_for(TABLE, 30)["number"] == "1.2"
    assert sp.path_for(TABLE, 29)["number"] == "1"
    assert sp.path_for(TABLE, 60)["number"] == "2"


def test_a_page_before_the_first_entry_gets_no_path():
    assert sp.path_for(TABLE, 9) is None


def test_granularity_is_PER_OBJECT_not_per_book():
    """505: a book is not uniformly coarse, it is coarse where its TOC is
    thin. johnston's median gap is 9 pages and its p90 is 113."""
    assert sp.path_for(TABLE, 31)["granularity"] == "section"      # gap 1
    assert sp.path_for(TABLE, 50)["granularity"] == "chapter"      # gap 20
    assert sp.path_for(TABLE, 95)["granularity"] == "distant"      # gap 35


def test_the_path_carries_its_own_evidence():
    p = sp.path_for(TABLE, 45)
    assert p["starts_on_pdf_page"] == 30 and p["pages_since_heading"] == 15


def test_a_refused_table_yields_nothing_at_any_page():
    for reason in ({"usable": False, "reason": "no /PageLabels"},
                   {"usable": False, "reason": "no TOC entry parses"}):
        assert sp.path_for(reason, 50) is None


def test_a_missing_page_yields_nothing():
    assert sp.path_for(TABLE, None) is None


def test_the_toc_line_parser():
    m = sp.TOC_ENTRY.match("  3.4 Distances in Chordal Graphs ..... 59 ")
    assert m and m.group(1) == "3.4" and m.group(3) == "59"
    assert m.group(2) == "Distances in Chordal Graphs"
    # cardona's shape: no number, roman page — must NOT parse
    assert sp.TOC_ENTRY.match("Introduction  ..... v") is None


def test_the_gate_constants_are_the_measured_ones():
    assert (sp.GAP_SECTION, sp.GAP_CHAPTER) == (5, 30)
