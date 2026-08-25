r"""143 — --min-conf / --max-conf / --types on reporttex.

A 31 MB, 4,414-row report is not a review artefact. These filters narrow the row
set BEFORE any crop is sized, so a filtered report is smaller on disk as well as
shorter.
"""
import json, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import parse_types, _conf_ok, build_report, TYPE_NAMES


def test_parse_types():
    assert parse_types("equation,formula") == {"equation", "formula"}
    assert parse_types(" Equation , TABLE ") == {"equation", "table"}
    assert parse_types(None) is None and parse_types("") is None


def test_unknown_type_raises_rather_than_selecting_everything():
    """A typo that silently selected all kinds would produce a full-size report
    and read as 'the filter matched nothing to remove'."""
    with pytest.raises(ValueError) as e:
        parse_types("equtaion")
    assert "equtaion" in str(e.value)
    for n in TYPE_NAMES:
        assert n in str(e.value)


def test_conf_bounds():
    assert _conf_ok(0.3, None, 0.5) and not _conf_ok(0.7, None, 0.5)
    assert _conf_ok(0.7, 0.5, None) and not _conf_ok(0.3, 0.5, None)
    assert _conf_ok(0.5, 0.5, 0.5)            # inclusive both ends


def test_missing_confidence_fails_a_bounded_filter():
    """--max-conf 0.5 must not return rows of UNKNOWN confidence beside the
    doubted ones; that is the opposite of what the flag is for."""
    assert not _conf_ok(None, None, 0.5)
    assert not _conf_ok("", 0.1, 0.9)


def test_missing_confidence_passes_when_unbounded():
    assert _conf_ok(None, None, None)


def _tiddlers(tmp: Path):
    key = "doc"
    rows = [
        {"title": f"{key}_EQ0001", "latex": "a=b", "page": "1", "confidence": 0.2},
        {"title": f"{key}_EQ0002", "latex": "c=d", "page": "1", "confidence": 0.9},
        {"title": f"{key}_EQ0003", "latex": "e=f", "page": "2"},          # none
        {"title": f"{key}_FO0001", "latex": r"\alpha", "page": "1"},
        {"title": f"{key}_TAB_001", "latex": "t", "page": "3"},
    ]
    p = tmp / f"{key}.tiddlers.json"
    p.write_text(json.dumps(rows))
    return p


def test_max_conf_keeps_only_doubted_equations(tmp_path):
    r = build_report(_tiddlers(tmp_path), out=tmp_path / "r.tex", max_conf=0.5)
    assert r["equations"] == 1          # 0.2 only; 0.9 too high, one has none
    assert r["formulas"] == 0 and r["tables"] == 0


def test_types_selects_kinds(tmp_path):
    r = build_report(_tiddlers(tmp_path), out=tmp_path / "r.tex",
                     types={"equation"})
    assert r["equations"] == 3 and r["formulas"] == 0 and r["tables"] == 0


def test_no_filter_keeps_everything(tmp_path):
    r = build_report(_tiddlers(tmp_path), out=tmp_path / "r.tex")
    assert (r["equations"], r["formulas"], r["tables"]) == (3, 1, 1)


def test_filtered_output_is_smaller_on_disk(tmp_path):
    full = tmp_path / "full.tex"; nar = tmp_path / "nar.tex"
    build_report(_tiddlers(tmp_path), out=full)
    build_report(_tiddlers(tmp_path), out=nar, max_conf=0.5, types={"equation"})
    assert nar.stat().st_size < full.stat().st_size


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# --------------------------------------------- 180/181 legend + notes ---

def test_legend_always_carries_the_confidence_bands():
    """181: the bands apply whether or not residuals were measured."""
    from pdfdrill import report_tex as rt
    for form in (True, False):
        assert "MathPix confidence" in rt.legend(form)


def test_absent_residual_half_is_NAMED_not_silently_dropped():
    """A key listing only what is present looks complete."""
    from pdfdrill import report_tex as rt
    assert "not shown for this document" in rt.legend(False)
    assert "not shown for this document" not in rt.legend(True)


def test_measured_legend_lists_the_residual_classes():
    from pdfdrill import report_tex as rt
    for cls in ("C component", "W weak", "S stable", "N noise", "K clean"):
        assert cls in rt.legend(True)


def test_unpairable_and_not_run_are_DIFFERENT_sentences():
    """180: the given note asserts a cause. Claiming it for a document nobody
    measured would state a reason that is not the reason."""
    from pdfdrill import report_tex as rt
    a, b = rt.unmeasured_note("unpairable"), rt.unmeasured_note("not_run")
    assert a != b
    assert "could not be read reliably enough" in a
    assert "could not be read reliably enough" not in b
    assert "no residual measurement has been run" in b.lower()


def test_both_notes_say_what_the_reader_HAS():
    from pdfdrill import report_tex as rt
    for k in ("unpairable", "not_run"):
        n = rt.unmeasured_note(k)
        assert "MathPix confidence is shown" in n
        assert "residual column is absent" in n


def test_note_is_empty_when_residuals_are_present():
    from pdfdrill import report_tex as rt
    assert rt.unmeasured_note("") == ""


def test_note_carries_no_internal_vocabulary():
    """Reader-facing: no lattice, no coverage, no inkdrill, no row-pairing."""
    from pdfdrill import report_tex as rt
    for k in ("unpairable", "not_run"):
        low = rt.unmeasured_note(k).lower()
        for jargon in ("lattice", "coverage", "inkdrill", "enclosure", "0.015"):
            assert jargon not in low
