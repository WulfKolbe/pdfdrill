"""440 — an unrecognised transclusion template must be visible, not skipped."""
from pdfdrill.report_tex import ANY_MARKER, KNOWN_TEMPLATES, unknown_markers
from pdfdrill.commands import _unrendered_markers


def test_the_known_set_is_what_the_projector_emits():
    """One list. A consumer that filters by template can only say whether a
    marker it skipped is unsupported or nonexistent if there is a single
    authority on what exists.
    """
    import re
    src = open("src/docops/projectors/tiddlywiki.py").read()
    emitted = set(re.findall(r'\("([A-Z]+)",\s*"', src))
    assert emitted <= KNOWN_TEMPLATES, emitted - KNOWN_TEMPLATES


def test_a_template_nothing_emits_is_reported():
    t = [{"text": "a {{k_FO0001||FO}} b {{k_X||NOPE}} c {{k_Y||NOPE}}"}]
    assert unknown_markers(t) == {"NOPE": 2}


def test_a_legitimate_template_is_not_reported_as_unknown():
    r"""DIA is what 434's type change produces. It must NOT be flagged as
    nonexistent — the point is to separate "this consumer does not handle it"
    from "nothing emits it", which is the distinction that was missing.
    """
    t = [{"text": "{{k_DIA0007||DIA}} {{k_TAB_001||TAB}}"}]
    assert unknown_markers(t) == {}


def test_spoken_reports_what_it_left_verbatim():
    r"""cmd_spoken renders FO/EQ/FREF and leaves the rest as literal braces in
    the output — a listener hears "open brace" and nothing reported it.
    """
    got = _unrendered_markers("{{a||FO}} {{b||DIA}} {{c||TAB}} {{d||NOPE}}")
    assert got == {"DIA": 1, "TAB": 1, "NOPE": 1}
    assert "FO" not in got


def test_the_marker_pattern_does_not_match_a_field_transclusion():
    r"""`{{!!svg_tiddler}}` is a FIELD transclusion, not an object one, and a
    Diagram tiddler's whole body is that. Counting it as a marker would report
    every rendered diagram as a defect.
    """
    assert ANY_MARKER.findall("{{!!svg_tiddler}}") == []
