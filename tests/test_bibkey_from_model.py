"""463 — the bibkey comes from the model, and an empty report is refused."""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import report_tex as rt


def _doc(tmp_path, *, file_key, model_key, titles_key):
    (tmp_path / rt.MODEL_NAME).write_text(json.dumps(
        {"meta": {"bibkey": model_key}, "objects": []}))
    tp = tmp_path / f"{file_key}.tiddlers.json"
    tp.write_text(json.dumps([
        {"title": f"{titles_key}_EQ0001", "latex": "a=b", "page": 1,
         "confidence": 0.9},
        {"title": f"{titles_key}_FO0001", "latex": "x^2", "page": 1},
    ]))
    return tp


def test_the_bibkey_comes_from_the_model_not_the_filename(tmp_path):
    tp = _doc(tmp_path, file_key="Some Long Z-Library Title (2019)",
              model_key="voloshin-hypergraph", titles_key="voloshin-hypergraph")
    assert rt.resolve_bibkey(tp) == "voloshin-hypergraph"


def test_the_filename_is_the_fallback_with_no_model(tmp_path):
    tp = tmp_path / "plainkey.tiddlers.json"
    tp.write_text("[]")
    assert rt.resolve_bibkey(tp) == "plainkey"


def test_a_model_without_a_bibkey_falls_back(tmp_path):
    (tmp_path / rt.MODEL_NAME).write_text(json.dumps({"meta": {}}))
    tp = tmp_path / "plainkey.tiddlers.json"
    tp.write_text("[]")
    assert rt.resolve_bibkey(tp) == "plainkey"


def test_an_unreadable_model_falls_back_rather_than_raising(tmp_path):
    (tmp_path / rt.MODEL_NAME).write_text("{not json")
    tp = tmp_path / "plainkey.tiddlers.json"
    tp.write_text("[]")
    assert rt.resolve_bibkey(tp) == "plainkey"


def test_the_renamed_document_builds_its_rows_again(tmp_path):
    """The 462 shape end to end: long filename, short bibkey, short titles."""
    tp = _doc(tmp_path, file_key="Some Long Z-Library Title (2019)",
              model_key="voloshin-hypergraph", titles_key="voloshin-hypergraph")
    r = rt.build_report(tp, out=tmp_path / "report.tex")
    assert (r["equations"], r["formulas_total"]) == (1, 1)


def test_an_empty_report_from_a_typed_projection_is_REFUSED(tmp_path):
    """What silently happened to nine documents: a bibkey that matches no
    title builds a one-page report with no rows, compiles it, stamps it, and
    reports success."""
    tp = _doc(tmp_path, file_key="doc", model_key="wrong-key",
              titles_key="voloshin-hypergraph")
    with pytest.raises(rt.ReportRefused) as e:
        rt.build_report(tp, out=tmp_path / "report.tex")
    msg = str(e.value)
    assert "wrong-key" in msg and "voloshin-hypergraph_EQ0001" in msg
    assert not (tmp_path / "report.tex").exists()


def test_a_document_with_no_typed_tiddlers_is_still_allowed_to_be_empty(tmp_path):
    """A document with no mathematics is a fact, not a defect."""
    (tmp_path / rt.MODEL_NAME).write_text(json.dumps(
        {"meta": {"bibkey": "d"}, "objects": []}))
    tp = tmp_path / "d.tiddlers.json"
    tp.write_text(json.dumps([{"title": "d/intro", "text": "prose"}]))
    r = rt.build_report(tp, out=tmp_path / "report.tex")
    assert r["equations"] == 0
    assert (tmp_path / "report.tex").exists()
