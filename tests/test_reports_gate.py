import json

from pdfdrill.reports import gate as G


def _doc(tmp_path, *, model_mtime=100, ink_mtime=100, ink_sha="S", model_sha="S",
         built_at="2026-09-05T10:57:49Z", files=G.PUBLISHED_FILES,
         glyph_loss=False, shown=("D_EQ0001", "D_EQ0002"), measured=("D_EQ0001", "D_EQ0002"),
         straddle=()):
    d = tmp_path / "D"
    d.mkdir(parents=True)
    (d / "model.docmodel.json").write_text("{}")
    import os
    os.utime(d / "model.docmodel.json", (model_mtime, model_mtime))
    ma = {"built_at": built_at, "model_mtime": ink_mtime, "model_sha256": ink_sha}
    (d / "report.ink.json").write_text(json.dumps(
        {"rows": [{"id": i, "code": "K|0"} for i in measured],
         "measured_against": ma}))
    for f in files:
        (d / f).write_bytes(b"%PDF-1.4\n")
        log = "Output written on %s (1 page, 10 bytes).\n" % f
        if glyph_loss:
            log += 'Missing character: There is no g ("67) in font rsfs10!\n'
        (d / f).with_suffix(".log").write_text(log)
    (d / "residuals.tex").write_text("".join(
        "\\ident{%s} & 1 & x\n" % i for i in shown))
    (d / "pdfdrill-rows.json").write_text(json.dumps({"rows": [
        {"identifier": i, "rules_on_one_page": i not in straddle}
        for i in set(shown) | set(measured)]}))
    return d


def test_matching_model_passes(tmp_path, monkeypatch):
    d = _doc(tmp_path)
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    ok, detail = G.timestamp_gate(d)
    assert ok and "2026-09-05T10:57:49Z" in detail


def test_newer_model_fails_and_names_the_fix(tmp_path, monkeypatch):
    d = _doc(tmp_path, ink_mtime=100)
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "T",
                                                         "model_mtime": 200})
    ok, detail = G.timestamp_gate(d)
    assert not ok and "residuals --measure" in detail


def test_no_ink_fails(tmp_path):
    d = _doc(tmp_path)
    (d / "report.ink.json").unlink()
    assert G.timestamp_gate(d)[0] is False


def test_pdf_checksum_is_never_compared(tmp_path, monkeypatch):
    d = _doc(tmp_path)
    (d / "residuals.pdf").write_bytes(b"%PDF-1.4 different\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    assert G.timestamp_gate(d)[0]


def test_coverage_excepts_straddlers_and_refuses_unknown_rows(tmp_path):
    d = _doc(tmp_path, shown=("D_EQ0001", "D_EQ0002", "D_EQ0003"),
             measured=("D_EQ0001",), straddle=("D_EQ0002",))
    ok, detail = G.coverage_gate(d)
    assert not ok and "D_EQ0003" in detail
    d2 = _doc(tmp_path / "b", shown=("D_EQ0001", "D_EQ0002"),
              measured=("D_EQ0001",), straddle=("D_EQ0002",))
    assert G.coverage_gate(d2)[0]


def test_artefacts_and_glyphs(tmp_path):
    d = _doc(tmp_path)
    assert G.artefacts_gate(d)[0] and G.glyphs_gate(d)[0]
    (d / "evidence-table.pdf").unlink()
    ok, detail = G.artefacts_gate(d)
    assert not ok and "evidence-table.pdf" in detail
    d2 = _doc(tmp_path / "g", glyph_loss=True)
    assert G.glyphs_gate(d2)[0] is False


def test_publish_ready_uses_the_new_surface_when_residuals_exist(tmp_path, monkeypatch):
    from pdfdrill.commands import publish_ready
    d = _doc(tmp_path)
    (d / "D.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    r = publish_ready(d / "D.pdf")
    assert set(r["checks"]) >= {"artefacts", "glyphs", "ink", "timestamp", "coverage"}
    assert r["ready"], r["checks"]
