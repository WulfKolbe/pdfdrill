r"""A reading's page is the number the reading states, not its position.

T-0154 (drillgroup, 2026-11-21). `lines.json` carries `pages: [...]` and every
page in it carries its own `"page"` field. Two scans in `src/pdfdrill` read the
list and threw that field away:

    for page, pg in enumerate(j.get("pages") or [], 1):     # inlinectx.load_spans
    for page, pg in enumerate(j.get("pages") or [], 1):     # regionrole.roles_for

Position equals the stated number only while the reading has every page. Where
one is missing -- a reader that skipped a page, an older reading, a reading cut
to a range -- every page after the gap is reported one too low, and nothing
says so: the number flows into `context_of`'s `page`, into an FO row, and into
the crop, so the published picture is of the wrong page of the PDF.
gemma4-f4 saw exactly this on lib:d68e from p246.

The fix is to read the field. The fallback to position stays for a reading that
does not state one at all (several of this suite's own fixtures do not), because
there the position is the only thing there is to go on -- but a STATED number
always wins over it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import inlinectx, regionrole


def _gapped(tmp_path):
    """Pages 1 and 3. Page 2 is not in the reading, and that is the point."""
    p = tmp_path / "gap.lines.json"
    p.write_text(json.dumps({"pages": [
        {"page": 1, "lines": [
            {"type": "text", "text": r"on the first page $a^2$ stands",
             "confidence": 0.9,
             "region": {"top_left_x": 10, "top_left_y": 20,
                        "width": 300, "height": 40}}]},
        {"page": 3, "lines": [
            {"type": "section_header", "text": "References"},
            {"type": "text", "text": r"on the third page $b^2$ stands",
             "confidence": 0.8,
             "region": {"top_left_x": 11, "top_left_y": 21,
                        "width": 301, "height": 41}}]},
    ]}), encoding="utf-8")
    return p


def test_a_span_carries_the_page_the_reading_states(tmp_path):
    """`b^2` is printed on page 3 and the span must say 3, not 2."""
    spans = inlinectx.load_spans(_gapped(tmp_path))
    by_latex = {s["latex"]: s for s in spans}
    assert by_latex["a^2"]["page"] == 1
    assert by_latex["b^2"]["page"] == 3, (
        "the page after the gap was numbered by position: %r"
        % (by_latex["b^2"]["page"],))


def test_the_context_a_crop_is_cut_from_names_that_page(tmp_path):
    """The number does not stay inside this module -- it is the page the
    report crops. A page too low crops a picture of other content."""
    first = inlinectx.first_occurrences(inlinectx.load_spans(_gapped(tmp_path)))
    assert inlinectx.context_of(first["b^2"])["page"] == 3


def test_a_role_is_recorded_against_the_stated_page(tmp_path):
    """`roles_for` returns (page, line_index, type, role); the bibliography
    opened on page 3 must be reported on page 3."""
    rows = regionrole.roles_for(_gapped(tmp_path))
    pages = sorted({r[0] for r in rows})
    assert pages == [1, 3], pages
    biblio = [r for r in rows if r[3] == regionrole.BIBLIOGRAPHY]
    assert biblio and all(r[0] == 3 for r in biblio), biblio


def test_a_reading_that_states_no_page_still_falls_back_to_position(tmp_path):
    """The fallback is not dead code: a hand-made reading (and several
    fixtures in this suite) carries no `page` field at all, and there the
    position is the only number available. It must not become None."""
    p = tmp_path / "nopage.lines.json"
    p.write_text(json.dumps({"pages": [
        {"lines": [{"type": "text", "text": r"first $u$"}]},
        {"lines": [{"type": "text", "text": r"second $v$"}]},
    ]}), encoding="utf-8")
    assert [s["page"] for s in inlinectx.load_spans(p)] == [1, 2]
    assert sorted({r[0] for r in regionrole.roles_for(p)}) == [1, 2]


def test_a_page_field_that_is_not_a_number_is_not_a_page(tmp_path):
    """A stated value only wins when it IS a page number. `null`, a string
    or 0 states nothing, and position is what is left -- the same shape as
    the null `px_per_pt` that raised out of `Pages.__init__` (73188fe9)."""
    p = tmp_path / "junk.lines.json"
    p.write_text(json.dumps({"pages": [
        {"page": None, "lines": [{"type": "text", "text": r"first $u$"}]},
        {"page": "two", "lines": [{"type": "text", "text": r"second $v$"}]},
        {"page": 0, "lines": [{"type": "text", "text": r"third $w$"}]},
    ]}), encoding="utf-8")
    assert [s["page"] for s in inlinectx.load_spans(p)] == [1, 2, 3]
    assert sorted({r[0] for r in regionrole.roles_for(p)}) == [1, 2, 3]
