# tests/test_reports_crops.py
from pathlib import Path

import pdfdrill.reports.crops as C
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine, TableRow


def _jpg(d: Path, name: str):
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(b"\xff\xd8" + b"0" * 600)


def _real_jpg(d: Path, name: str, w=400, h=300):
    """A PIL-openable JPEG -- unlike `_jpg` above, this one survives an
    actual re-encode, needed by every 655 budget test below."""
    from PIL import Image
    d.mkdir(exist_ok=True)
    Image.new("RGB", (w, h), color=(90, 140, 200)).save(
        d / name, "JPEG", quality=95)


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


def test_download_crops_fetches_pic_and_dia_not_para(tmp_path, monkeypatch):
    """A PIC/DIA record with an http canonical_uri is fetched; a non-crop
    kind (PARA) with an http uri is left alone."""
    import pdfdrill.net as net

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"\xff\xd8" + b"0" * 600

    monkeypatch.setattr(net, "urlopen", lambda url, timeout=20: _FakeResp())
    dest = tmp_path / "crops"
    ok, cached, failed = C.rt.download_crops(
        [{"title": "D_PIC_0001", "canonical_uri": "https://cdn/p.jpg"},
         {"title": "D_PARA_0001", "canonical_uri": "https://cdn/x.jpg"}],
        dest)
    assert ok == 1 and failed == 0
    assert (dest / "D_PIC_0001.jpg").is_file()
    assert not (dest / "D_PARA_0001.jpg").exists()


# ---------------------------------------------------------------------- #
# 655 — the size budget, applied per KIND inside ensure_crops.
# ---------------------------------------------------------------------- #

def _budget_setup(tmp_path, monkeypatch, *, formula_w=400, formula_h=300):
    """A formula row whose crop is a REAL, sizeable JPEG (so it can be
    genuinely over budget and genuinely re-encoded) and a table row whose
    crop is the tiny placeholder used elsewhere in this file (so it stays
    trivially under budget). Returns (rows, crops_dir, orig_bytes)."""
    def fake_download(records, dest, **kw):
        return 0, 0, 0

    def fake_render(records, dest, pdf, kinds=("_TAB",), **kw):
        for r in records:
            if r["title"] == "D_FO0001":
                _real_jpg(dest, "D_FO0001.jpg", w=formula_w, h=formula_h)
            elif r["title"] == "D_TAB_001":
                _jpg(dest, "D_TAB_001.jpg")
        return len(records), 0, 0

    monkeypatch.setattr(C.rt, "download_crops", fake_download)
    monkeypatch.setattr(C.rt, "render_crops", fake_render)
    h = HostLine(page=3, confidence=0.9, region={"top_left_x": 1, "top_left_y": 2,
                                                 "width": formula_w, "height": formula_h})
    rows = {"equation": [],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P", host_line=h)],
            "table": [TableRow(identifier="D_TAB_001", latex="", page="5",
                               region={"top_left_x": 1, "top_left_y": 1,
                                       "width": 9, "height": 9})],
            "image": []}
    return rows


def test_a_kind_under_budget_selects_full_scale_and_copies_nothing(tmp_path, monkeypatch):
    rows = _budget_setup(tmp_path, monkeypatch)
    out, note = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf", bibkey="D",
                               budget_mb=1000.0)   # comfortably over both
    crops = tmp_path / C.CROPS_DIR
    assert out["formula"][0].crop == crops / "D_FO0001.jpg"
    assert out["formula"][0].px_width == ""        # untouched -> no override
    assert out["table"][0].crop == crops / "D_TAB_001.jpg"
    assert not (tmp_path / C.CROPS_DIR_B).exists()  # nothing to scale, nothing copied
    assert "budget" not in note


def test_a_kind_over_budget_scales_and_the_other_kind_is_untouched(tmp_path, monkeypatch):
    rows = _budget_setup(tmp_path, monkeypatch)
    crops = tmp_path / C.CROPS_DIR
    # Discover the real on-disk size first (655 rule: measure, don't guess),
    # then pick a budget the formula crop alone cannot meet at full size.
    C.rt.download_crops([], crops)
    C.rt.render_crops([{"title": "D_FO0001"}, {"title": "D_TAB_001"}], crops,
                      tmp_path / "D.pdf", kinds=())
    full_size = (crops / "D_FO0001.jpg").stat().st_size
    before_bytes = (crops / "D_FO0001.jpg").read_bytes()
    table_before = (crops / "D_TAB_001.jpg").read_bytes()
    budget_mb = (full_size / 2) / (1024 * 1024)

    out, note = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf", bibkey="D",
                               budget_mb=budget_mb)

    fr = out["formula"][0]
    assert fr.crop.parent == tmp_path / C.CROPS_DIR_B
    assert fr.crop.is_file()
    assert fr.px_width == "400"                    # the ORIGINAL pixel width
    assert "formula scale=" in note

    # the source crop is never touched, at any scale
    assert (crops / "D_FO0001.jpg").read_bytes() == before_bytes

    # the OTHER kind, comfortably under budget on its own, is untouched
    tr = out["table"][0]
    assert tr.crop == crops / "D_TAB_001.jpg"
    assert tr.px_width == ""
    assert (crops / "D_TAB_001.jpg").read_bytes() == table_before


def test_physical_size_on_the_page_is_unchanged_by_scaling(tmp_path, monkeypatch):
    """655 item 5 — assert on the emitted `width=` STRING, not on the image:
    `crop_cell` must set the same physical width whether or not the crop
    behind it was downsampled."""
    rows = _budget_setup(tmp_path, monkeypatch)
    crops = tmp_path / C.CROPS_DIR
    C.rt.render_crops([{"title": "D_FO0001"}], crops, tmp_path / "D.pdf", kinds=())
    full_size = (crops / "D_FO0001.jpg").stat().st_size
    before_cell = C.rt.crop_cell(crops, tmp_path, "D_FO0001", px2mm=0.1,
                                 col_mm=1000.0, bibkey="D")

    out, _ = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf", bibkey="D",
                            budget_mb=(full_size / 2) / (1024 * 1024))
    fr = out["formula"][0]
    assert fr.crop.parent == tmp_path / C.CROPS_DIR_B   # sanity: it WAS scaled
    after_cell = C.rt.crop_cell(fr.crop.parent, tmp_path, fr.crop.stem,
                                px_width=fr.px_width, px2mm=0.1, col_mm=1000.0,
                                bibkey="D")
    import re
    before_w = re.search(r"width=([\d.]+)mm", before_cell).group(1)
    after_w = re.search(r"width=([\d.]+)mm", after_cell).group(1)
    assert before_w == after_w


def test_floor_reached_is_reported_over_budget_in_the_note(tmp_path, monkeypatch):
    rows = _budget_setup(tmp_path, monkeypatch)
    out, note = C.ensure_crops(rows, tmp_path, tmp_path / "D.pdf", bibkey="D",
                               budget_mb=1e-9)     # unreachable by any rung
    fr = out["formula"][0]
    assert fr.crop.parent == tmp_path / C.CROPS_DIR_B
    import pdfdrill.reports.budget as budget_mod
    assert fr.px_width == "400"
    assert "OVER BUDGET" in note
    # never below the floor
    from PIL import Image
    with Image.open(tmp_path / C.CROPS_DIR / "D_FO0001.jpg") as im:
        orig_w = im.size[0]
    with Image.open(fr.crop) as im:
        scaled_w = im.size[0]
    assert scaled_w == round(orig_w * budget_mod.CROP_LADDER[-1][0])
