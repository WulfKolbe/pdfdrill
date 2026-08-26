"""195 — reporttex adopts the document's own report.ink.json.

The residual measurement is a two-phase loop by construction: the ink pass
needs a report to measure, so the report is built BEFORE the residuals and
rebuilt AFTER them. Before this fix the rebuild ignored the file unless
someone typed --ink with its path, so every drill produced a report without
residuals and a human re-ran it by hand.
"""
import json
import pytest

from pdfdrill import report_tex as rt


def _ink(tmp_path, rows):
    p = tmp_path / "report.ink.json"
    p.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return p


def test_load_ink_reads_the_measured_classes(tmp_path):
    p = _ink(tmp_path, [{"id": "X_EQ0001", "flag": "component", "code": "C|+4"},
                        {"id": "X_EQ0002", "flag": "clean", "code": "K|0"}])
    m = rt.load_ink(p)
    assert m["X_EQ0001"]["flag"] == "component"
    assert m["X_EQ0002"]["code"] == "K|0"


def test_absent_ink_file_RAISES_rather_than_loading_empty(tmp_path):
    """Strict on purpose. An explicit --ink to a missing file must not become
    a report that says no measurement was run — cmd_reporttex checks the path
    and refuses by name instead."""
    with pytest.raises(OSError):
        rt.load_ink(tmp_path / "nope.json")


def test_residual_column_appears_only_when_asked():
    """`form` gates the column; ink data must imply it or the file is read,
    the bullets computed, and nothing drawn."""
    assert "not shown for this document" in rt.legend(False)
    assert "C component" in rt.legend(True)


def test_unmeasured_note_states_not_run_only_when_nothing_was_measured():
    a = rt.unmeasured_note("not_run")
    assert "no residual measurement has been run" in a.lower()


def test_measured_report_carries_no_unmeasured_note():
    """A report with residuals must not tell the reader there are none."""
    assert rt.unmeasured_note("") == ""
