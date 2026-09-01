"""460 — the formulas section is a report of problems, not a catalogue."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import report_tex as rt


ROWS = [
    ("D_FO_001", r"x^2 + y^2", 3, ""),          # renders
    ("D_FO_002", r"\alpha\beta", 4, ""),        # renders
    ("D_FO_003", "a & b", 5, ""),                # a bare & -- refused
    ("D_FO_004", "", 6, ""),                    # no LaTeX at all
]


def test_unresolved_keeps_only_the_rows_that_did_not_render():
    keep = rt.unresolved_formulas(ROWS)
    ids = [r[0] for r in keep]
    # the two that render are gone, and so is the one with no LaTeX: an
    # absent formula is not an unresolved one, it shows as a dash.
    assert "D_FO_001" not in ids and "D_FO_002" not in ids
    assert "D_FO_004" not in ids
    # and the predicate is the SAME one the Rendered cell uses
    for r in ROWS:
        assert (r in keep) == bool(r[1] and not rt.renderable(r[1]))


def test_a_row_with_no_latex_is_absent_not_unresolved():
    assert rt.unresolved_formulas([("D_FO_009", "", 1, "")]) == []


def test_the_rule_names_are_the_only_ones_accepted():
    assert rt.FORMULA_RULES == ("all", "unresolved", "none")


def test_build_report_refuses_a_rule_it_does_not_know(tmp_path):
    t = tmp_path / "doc.tiddlers.json"
    t.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        rt.build_report(t, out=tmp_path / "report.tex", formulas="some")
    assert "all, unresolved, none" in str(e.value)


def _doc(tmp_path):
    import json
    tids = [
        {"title": "doc_FO_001", "latex": "x^2", "page": 1},
        {"title": "doc_FO_002", "latex": "a & b", "page": 2},
        {"title": "doc_EQ_001", "latex": "a=b", "page": 1, "confidence": 0.9},
    ]
    t = tmp_path / "doc.tiddlers.json"
    t.write_text(json.dumps(tids), encoding="utf-8")
    return t


def test_default_shows_only_the_unresolved_formula(tmp_path):
    r = rt.build_report(_doc(tmp_path), out=tmp_path / "report.tex")
    assert r["formulas"] == 1 and r["formulas_total"] == 2
    assert r["formula_rule"] == "unresolved"
    tex = (tmp_path / "report.tex").read_text()
    # the caption states the rule, so a one-row table is not read as a
    # one-formula document
    assert "Inline formulas that did not render (1 of 2)" in tex
    plain = tex.replace("\\allowbreak{}", "").replace("\\_", "_")
    assert "doc_FO_002" in plain and "doc_FO_001" not in plain


def test_none_omits_the_section_and_its_manifest_record(tmp_path):
    import json
    r = rt.build_report(_doc(tmp_path), out=tmp_path / "report.tex",
                        formulas="none")
    assert r["formulas"] == 0 and r["formulas_total"] == 2
    tex = (tmp_path / "report.tex").read_text()
    assert "Inline formulas" not in tex
    man = json.loads((tmp_path / "report.tables.json").read_text())
    caps = [t["caption"] for t in man["tables"]]
    assert not any("Inline formulas" in c for c in caps)
    # the equations table is still there and still FIRST, which is the one
    # inkmeasure joins on
    assert caps and caps[0] == "Display equations"


def test_all_is_the_former_behaviour(tmp_path):
    r = rt.build_report(_doc(tmp_path), out=tmp_path / "report.tex",
                        formulas="all")
    assert r["formulas"] == 2 == r["formulas_total"]
    tex = (tmp_path / "report.tex").read_text()
    assert "Inline formulas (first occurrence)" in tex
