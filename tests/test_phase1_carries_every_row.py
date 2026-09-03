"""579 — phase 1 and phase 2 differ by the bullet and the legend, nothing else.

Before this, step 2 hid report.ink.json so the measure build could not adopt
it, because the build stamp derived `phase` from whether the ink had been
adopted. But `flagged` and `doubted` are SELECTED by the ink code in
findings_rows, so a phase-1 build could only ever contain `corrected` and
`unresolved`. Across the 21 published documents phase 1 differed from phase 2
on every one, and on 8 it was empty — so a measurement was taken against a
report nobody reads, or refused outright.

`measured_against` asserts "this ink was measured against THAT report". That
can only be true if the two builds have the same rows.
"""
import json

from pdfdrill import report_tex as rt

_ROWS = {
    "corrected": [],
    "unresolved": [],
    # the delta must clear FLAG_SHOW_DELTA (515 bands the tail into a count),
    # otherwise the row is not SHOWN in either phase and the test would be
    # comparing two absences.
    "flagged": [{"identifier": "X_EQ0001", "page": 3, "conf": 0.95,
                 "latex": "x^2", "code": "C|+45"}],
    "doubted": [{"identifier": "X_EQ0002", "page": 4, "conf": 0.4,
                 "latex": "y^2", "code": "N|+1"}],
}
_W = (78, 78, 78, 78, 78)


def test_the_same_rows_are_emitted_with_and_without_bullets():
    on = rt.findings_tex(_ROWS, _W, bullets=True)
    off = rt.findings_tex(_ROWS, _W, bullets=False)
    for ident in ("X_EQ0001", "X_EQ0002"):
        assert ident.split("_")[1] in on.replace("\\allowbreak{}", "")
        assert ident.split("_")[1] in off.replace("\\allowbreak{}", "")
    assert on.count("\\hline") == off.count("\\hline"), "row counts differ"


def test_only_phase_two_prints_the_bullet():
    on = rt.findings_tex(_ROWS, _W, bullets=True)
    off = rt.findings_tex(_ROWS, _W, bullets=False)
    assert on.count("\\inkbullet") == 2
    assert off.count("\\inkbullet") == 0, "the measure build must print none"


def test_the_captions_and_counts_are_identical():
    on = rt.findings_tex(_ROWS, _W, bullets=True)
    off = rt.findings_tex(_ROWS, _W, bullets=False)
    for cap in ("Flagged, not acted on", "Doubted but correct"):
        assert cap in on and cap in off


def test_phase_is_decided_by_bullets_not_by_adoption(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    # the new case: the ink WAS read, and no bullets were printed -> measure
    st = rt.write_build_stamp(pdf, legend=False, ink_adopted=True,
                              prefer_refined=False, filters={}, bullets=False)
    assert st["phase"] == "measure", "reading the ink must not make it a reading build"
    assert st["ink_adopted"] is True and st["bullets"] is False
    # and the reading build
    st = rt.write_build_stamp(pdf, legend=True, ink_adopted=True,
                              prefer_refined=False, filters={}, bullets=True)
    assert st["phase"] == "reading" and st["bullets"] is True


def test_an_omitted_bullets_argument_keeps_the_old_meaning(tmp_path):
    """Every stamp written before 579, and every caller that does not pass
    `bullets`, must keep the phase it had."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert rt.write_build_stamp(pdf, legend=False, ink_adopted=False,
                                prefer_refined=False,
                                filters={})["phase"] == "measure"
    assert rt.write_build_stamp(pdf, legend=True, ink_adopted=True,
                                prefer_refined=False,
                                filters={})["phase"] == "reading"
