"""174 — the refined report: conf | ink before | ink after | verdict."""
import json

from pdfdrill import report_tex as rt


def _changes(**over):
    d = {"bibkey": "demo", "proposals": [
        {"id": "obj_a", "page": 85, "confidence": 0.002, "status": "accepted",
         "ink_before": 91, "ink_after": 40},
        {"id": "obj_b", "page": 85, "confidence": 0.004, "status": "rejected",
         "reason": "no improvement", "ink_before": 54, "ink_after": 104},
        {"id": "obj_c", "page": 12, "confidence": 0.11, "status": "rejected",
         "reason": "width uniformity"},
        {"id": "obj_d", "page": 3, "confidence": 0.30, "status": "selected"},
    ]}
    d.update(over)
    return d


def _write(tmp_path, d):
    p = tmp_path / "changes.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_selected_but_never_proposed_row_is_excluded():
    """A row with no proposal has no before/after; a row of dashes would read
    as a measurement that came out empty."""
    ids = [p["id"] for p in rt.refined_rows(_changes())]
    assert "obj_d" not in ids and len(ids) == 3


def test_rows_are_worst_confidence_first():
    assert [p["id"] for p in rt.refined_rows(_changes())] == \
        ["obj_a", "obj_b", "obj_c"]


def test_verdicts_read_from_status_and_reason():
    a, b, c = rt.refined_rows(_changes())
    assert rt._verdict_of(a) == ("accepted", "ink fell")
    assert rt._verdict_of(b) == ("rejected", "no improvement")
    assert rt._verdict_of(c) == ("rejected", "width uniformity")


def test_report_carries_the_four_columns(tmp_path):
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    txt = r["out"].read_text()
    for head in ("Conf.", "Ink before", "Ink after", "Verdict"):
        assert head in txt


def test_signed_delta_is_shown(tmp_path):
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    txt = r["out"].read_text()
    assert "(-51)" in txt          # 91 -> 40, improved
    assert "(+50)" in txt          # 54 -> 104, worse


def test_unmeasured_row_shows_dashes_not_zero(tmp_path):
    """0 is a real ink distance and means 'identical'. An absent measurement
    must not be rendered as one."""
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    line = [l for l in r["out"].read_text().splitlines() if "obj\\_c" in l][0]
    assert "---" in line and " 0 " not in line


def test_ink_colours_are_defined_in_the_preamble(tmp_path):
    """The bullets use FORM_PREAMBLE's palette; without it every one is an
    'Undefined color' error — the exact defect task 158 hit."""
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    txt = r["out"].read_text()
    assert "\\newcommand{\\inkbullet}" in txt
    assert "\\definecolor{inkComponent}" in txt


def test_document_is_closed(tmp_path):
    """Without \\end{document} xelatex ends in Emergency stop and no pages."""
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    assert r["out"].read_text().rstrip().endswith("\\end{document}")


def test_counts_are_reported(tmp_path):
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    assert r["counts"] == {"accepted": 1, "rejected": 2}
    assert r["rows"] == 3


def test_empty_changes_still_produces_a_valid_document(tmp_path):
    r = rt.build_refined_report(_write(tmp_path, {"bibkey": "x", "proposals": []}))
    txt = r["out"].read_text()
    assert r["rows"] == 0
    assert "no refined rows" in txt
    assert txt.rstrip().endswith("\\end{document}")


def test_output_name_shares_no_prefix_with_the_published_report(tmp_path):
    """`report.*` in a document folder sweeps twelve files, including
    report.ink.json.MISPAIRED — a quarantined file whose whole purpose is that
    it must never be republished. Quarantine by rename survives being picked by
    NAME and does not survive a glob, so the refined report must not sit in
    that namespace at all."""
    r = rt.build_refined_report(_write(tmp_path, _changes()))
    assert r["out"].name == rt.REFINED_NAME
    assert not r["out"].name.startswith("report.")
    # and the xelatex byproducts inherit the safe stem
    assert r["out"].with_suffix(".pdf").name == "refine.report.pdf"


def test_row_is_labelled_by_identifier_not_object_id(tmp_path):
    """The auditor searches for 0902.0431_EQ0515, not obj_dedd3734e03a. A
    report keyed on object ids is unsearchable against every other artefact."""
    d = _changes()
    d["proposals"][0]["identifier"] = "0902.0431_EQ0515"
    txt = rt.build_refined_report(_write(tmp_path, d))["out"].read_text()
    assert "EQ0515" in txt


def test_row_without_an_identifier_falls_back_to_the_object_id(tmp_path):
    """Never a blank cell: an unmapped row must still be locatable."""
    txt = rt.build_refined_report(_write(tmp_path, _changes()))["out"].read_text()
    assert "obj\\_a" in txt
