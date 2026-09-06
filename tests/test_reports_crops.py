# tests/test_reports_crops.py
from pathlib import Path

import pdfdrill.reports.crops as C
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine, TableRow


def _jpg(d: Path, name: str):
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(b"\xff\xd8" + b"0" * 600)


def test_records_are_built_from_rows():
    h = HostLine(page=3, confidence=0.9, region={"top_left_x": 1, "top_left_y": 2,
                                                 "width": 30, "height": 4})
    rows = {"equation": [EquationRow(identifier="D_EQ0001", latex="x", page="2",
                                     cdn_url="https://cdn/x.jpg",
                                     region={"top_left_x": 5, "top_left_y": 6,
                                             "width": 7, "height": 8})],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P", host_line=h),
                        FormulaRow(identifier="D_FO0002", latex="\\square")],
            "table": [TableRow(identifier="D_TAB_001", latex="", page="5",
                               region={"top_left_x": 1, "top_left_y": 1,
                                       "width": 9, "height": 9})],
            "image": []}
    recs = C.records(rows)
    assert {"title": "D_EQ0001", "canonical_uri": "https://cdn/x.jpg", "page": "2",
            "top_left_x": 5, "top_left_y": 6, "width": 7, "height": 8} in recs
    assert {"title": "D_FO0001", "canonical_uri": "", "page": "3",
            "top_left_x": 1, "top_left_y": 2, "width": 30, "height": 4} in recs
    assert all(r["title"] != "D_FO0002" for r in recs)     # no host line, no record
    assert any(r["title"] == "D_TAB_001" and r["canonical_uri"] == "" for r in recs)


def test_ensure_crops_calls_download_then_render_and_fills_crop(tmp_path, monkeypatch):
    seen = {}

    def fake_download(records, dest, **kw):
        seen["download"] = [r["title"] for r in records]
        _jpg(dest, "D_EQ0001.jpg")
        return 1, 0, 0

    def fake_render(records, dest, pdf, kinds=("_TAB",), **kw):
        seen["render"] = ([r["title"] for r in records], kinds)
        for r in records:
            if not r["canonical_uri"]:
                _jpg(dest, r["title"] + ".jpg")
        return 2, 0, 0

    monkeypatch.setattr(C.rt, "download_crops", fake_download)
    monkeypatch.setattr(C.rt, "render_crops", fake_render)
    h = HostLine(page=3, confidence=0.9, region={"top_left_x": 1, "top_left_y": 2,
                                                 "width": 30, "height": 4})
    rows = {"equation": [EquationRow(identifier="D_EQ0001", latex="x", page="2",
                                     cdn_url="https://cdn/x.jpg")],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P", host_line=h),
                        FormulaRow(identifier="D_FO0002", latex="\\square")],
            "table": [TableRow(identifier="D_TAB_001", latex="", page="5",
                               region={"top_left_x": 1, "top_left_y": 1,
                                       "width": 9, "height": 9})],
            "image": []}
    out, note = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf", bibkey="D")
    assert seen["render"][1] == ("_EQ", "_FO", "_TAB", "_DIA", "_PIC")
    assert out["equation"][0].crop == tmp_path / "report-crops" / "D_EQ0001.jpg"
    assert out["formula"][0].crop == tmp_path / "report-crops" / "D_FO0001.jpg"
    assert out["formula"][1].crop is None
    assert out["table"][0].crop == tmp_path / "report-crops" / "D_TAB_001.jpg"
    assert "1 fetched" in note and "2 rendered" in note


def test_images_off_leaves_every_crop_none(tmp_path):
    rows = {"equation": [EquationRow(identifier="D_EQ0001", latex="x")],
            "formula": [], "table": [], "image": []}
    out, note = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf",
                               bibkey="D", images=False)
    assert out["equation"][0].crop is None and note == "images: off"
