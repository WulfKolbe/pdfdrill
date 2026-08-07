"""A section's page is where its CONTENT is, not where its title is listed.

MathPix reads the printed table of contents as a run of headings, so the Section
objects took their page from the TOC page: 35 of 38 sections in kolbe2018hubbard
claimed page 2 while their content starts on pages 6 through 40.

Visible as page labels marching 5, 2, 6, 2, 7, 2 down the reflow, but the damage
is wider — `booktoc` derives the front-matter offset from
`median(section.pdf_page - toc.printed_page)`, the inspector draws every section
box on the TOC page, and anything that answers "which page is section X on" is
wrong.

A heading CAN legitimately sit at the foot of the previous page, so only a gap
of more than one page counts as wrong.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.heading_cleanup import repair_section_pages


class _Obj:
    def __init__(self, id_, type_, **props):
        self.id = id_
        self.type = type_
        self.props = dict(props)


class _Doc:
    def __init__(self, objs):
        self._objs = objs

    @property
    def objects(self):
        return {o.id: o for o in self._objs}

    def objects_of_type(self, t):
        return [o for o in self._objs if o.type == t]


def _doc(section_page, content_page):
    return _Doc([
        _Obj("s1", "Section", page=section_page, caption="2.3 Spin", flow_index=10),
        _Obj("p1", "Paragraph", page=content_page, parent_section="s1", flow_index=11),
        _Obj("p2", "Paragraph", page=content_page + 1, parent_section="s1", flow_index=12),
    ])


def test_a_section_listed_on_the_contents_page_is_moved_to_its_content():
    d = _doc(section_page=2, content_page=10)
    assert repair_section_pages(d) == 1
    assert d.objects["s1"].props["page"] == 10
    # the original is kept, so the repair is auditable and reversible
    assert d.objects["s1"].props["page_before_repair"] == 2


def test_a_heading_at_the_foot_of_the_previous_page_is_left_alone():
    """Legitimate typesetting: the heading prints on page 9, the body flows onto
    page 10. Moving it would be a fabrication, not a repair."""
    d = _doc(section_page=9, content_page=10)
    assert repair_section_pages(d) == 0
    assert d.objects["s1"].props["page"] == 9


def test_a_correct_section_is_untouched():
    d = _doc(section_page=10, content_page=10)
    assert repair_section_pages(d) == 0
    assert "page_before_repair" not in d.objects["s1"].props


def test_a_section_AFTER_its_content_is_also_wrong():
    """The gap is wrong in either direction — a section cannot start after the
    text it introduces."""
    d = _doc(section_page=30, content_page=10)
    assert repair_section_pages(d) == 1
    assert d.objects["s1"].props["page"] == 10


def test_a_section_with_no_placed_content_is_left_alone():
    d = _Doc([_Obj("s1", "Section", page=2, caption="Empty"),
              _Obj("p1", "Paragraph", parent_section="s1")])      # no page
    assert repair_section_pages(d) == 0
    assert d.objects["s1"].props["page"] == 2


def test_the_repair_is_idempotent():
    d = _doc(section_page=2, content_page=10)
    assert repair_section_pages(d) == 1
    assert repair_section_pages(d) == 0
    assert d.objects["s1"].props["page"] == 10


def test_the_earliest_content_decides_not_whichever_comes_first_in_the_list():
    d = _Doc([
        _Obj("s1", "Section", page=2, flow_index=10),
        _Obj("p2", "Paragraph", page=12, parent_section="s1", flow_index=13),
        _Obj("p1", "Paragraph", page=10, parent_section="s1", flow_index=11),
    ])
    assert repair_section_pages(d) == 1
    assert d.objects["s1"].props["page"] == 10


def test_a_section_with_no_children_uses_the_next_content_in_the_flow():
    """Two sections in the thesis owned no `parent_section` children, so the
    repair skipped them and they stayed on the contents page. The document's
    reading order still says where they begin."""
    d = _Doc([
        _Obj("s1", "Section", page=2, caption="5.1 The Heisenberg Model", flow_index=50),
        _Obj("p1", "Paragraph", page=27, flow_index=51),      # no parent_section
        _Obj("p2", "Paragraph", page=28, flow_index=52),
    ])
    assert repair_section_pages(d) == 1
    assert d.objects["s1"].props["page"] == 27


def test_a_child_is_preferred_over_the_next_flow_element():
    """Ownership beats proximity: a section whose own content is on page 30 is
    not moved to page 27 because some unrelated block follows it."""
    d = _Doc([
        _Obj("s1", "Section", page=2, flow_index=50),
        _Obj("x", "Paragraph", page=27, flow_index=51),
        _Obj("p1", "Paragraph", page=30, parent_section="s1", flow_index=52),
    ])
    assert repair_section_pages(d) == 1
    assert d.objects["s1"].props["page"] == 30


def test_a_trailing_section_with_nothing_after_it_is_left_alone():
    d = _Doc([_Obj("s1", "Section", page=2, flow_index=99)])
    assert repair_section_pages(d) == 0
