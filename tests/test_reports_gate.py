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


def test_shown_identifiers_reads_every_ident_form_at_once():
    """fix round 1 — the plain row, the (was)/(now) pair (with its `basis:`
    multicolumn line, which carries no `\\ident` and must contribute
    nothing), and an identifier carrying `\\allowbreak{}` collapse to their
    three bare identifiers, not two (a `(was)`/`(now)` pair is ONE shown
    identifier) and not fewer (the pair must not be dropped)."""
    tex = (
        "\\ident{D_EQ0001} & 1 & x \\\\ \\hline\n"
        "\\ident{D_EQ0002 (was)} & 2 & y \\\\ \\hline\n"
        "\\ident{D_EQ0002 (now)} & 2 & z \\\\ \\hline\n"
        "\\multicolumn{5}{|p{10mm}|}{{\\scriptsize basis: x / y}} \\\\ \\hline\n"
        "\\ident{D\\_\\allowbreak{}EQ0003} & 3 & w \\\\ \\hline\n"
    )
    assert G.shown_identifiers(tex) == {"D_EQ0001", "D_EQ0002", "D_EQ0003"}


def test_coverage_gate_catches_an_unmeasured_corrected_pair(tmp_path):
    """The minimal repro: a residuals.tex with a PLAIN row (which used to
    make `inkconvert.identifiers()` return early on its EQ pattern, per its
    own first-match contract) AND a Corrected `(was)`/`(now)` pair for an
    identifier that is neither measured nor a straddler. The old
    `coverage_gate` (built on `identifiers()`) never saw the pair at all and
    passed; this must fail and name it.
    """
    d = _doc(tmp_path, shown=(), measured=("D_EQ0001",))
    (d / "residuals.tex").write_text(
        "\\ident{D_EQ0001} & 1 & x \\\\ \\hline\n"
        "\\ident{D_EQ0002 (was)} & 2 & y \\\\ \\hline\n"
        "\\ident{D_EQ0002 (now)} & 2 & z \\\\ \\hline\n"
        "\\multicolumn{5}{|p{10mm}|}{{\\scriptsize basis: x / y}} \\\\ \\hline\n"
    )
    ok, detail = G.coverage_gate(d)
    assert not ok and "D_EQ0002" in detail


def test_artefacts_and_glyphs(tmp_path):
    d = _doc(tmp_path)
    assert G.artefacts_gate(d)[0] and G.glyphs_gate(d)[0]
    (d / "evidence-table.pdf").unlink()
    ok, detail = G.artefacts_gate(d)
    assert not ok and "evidence-table.pdf" in detail
    d2 = _doc(tmp_path / "g", glyph_loss=True)
    assert G.glyphs_gate(d2)[0] is False


# ---------------------------------------------------------------- 634

def test_tex_errors_pairs_a_bang_line_with_its_source_line_number():
    r"""A real error: fong-spivak-seven-sketches evidence-formula.log's
    `\boldsymbol{\operatorname{...}}` failure — the `! ` line and its
    `l.736` both present, a few lines apart."""
    real = ("! Missing } inserted.\n"
            "<inserted text> \n"
            "                }\n"
            "l.736 ...oldsymbol{\\operatorname { R e l }}(S)$} &\n")
    assert G.tex_errors(real) == 1


def test_tex_errors_ignores_the_underfull_hbox_wrap():
    r"""Measured false positive: fong-spivak-seven-sketches
    evidence-table.log line 2270. An Underfull \hbox trace wraps a row's own
    text (`yes!`) across the line break, leaving `! \\` at the start of a
    line with no `l.N` anywhere near it — only `[]` and blank lines follow,
    the box-warning's own furniture. A bare `^! ` count would refuse a file
    xelatex built clean; the paired rule must not.
    """
    text = ("Underfull \\hbox (badness 10000) in paragraph at lines "
            "503--518\n"
            "\\TU/DejaVuSansMono(0)/m/n/8 no & yes! \\\\ \\hline 2 & 2 & 2 & "
            "2 & yes & yes & yes\n"
            "! \\\\ \n"
            " []\n"
            "\n")
    assert G.tex_errors(text) == 0


def test_tex_errors_counts_two_real_errors():
    text = ("! Missing } inserted.\n"
            "<inserted text> \n"
            "l.100 foo\n"
            "! Undefined control sequence.\n"
            "l.200 bar\n")
    assert G.tex_errors(text) == 2


def test_compile_gate_refuses_a_log_with_a_remaining_xelatex_error(tmp_path):
    d = _doc(tmp_path)
    log = d / "evidence-formula.log"
    log.write_text(log.read_text() +
                   "! Missing } inserted.\n<inserted text> \nl.736 ...\n")
    ok, detail = G.compile_gate(d)
    assert not ok
    assert "evidence-formula.pdf" in detail and "1 xelatex error" in detail


def test_compile_gate_is_the_new_name_glyphs_gate_stays_an_alias():
    assert G.glyphs_gate is G.compile_gate


def test_publish_ready_uses_the_new_surface_when_residuals_exist(tmp_path, monkeypatch):
    from pdfdrill.commands import publish_ready
    d = _doc(tmp_path)
    (d / "D.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    r = publish_ready(d / "D.pdf")
    assert set(r["checks"]) >= {"artefacts", "glyphs", "ink", "timestamp", "coverage"}
    assert r["ready"], r["checks"]


def test_handover_rows_survives_the_new_surface_and_names_its_checks(tmp_path, monkeypatch):
    """9-fix: `handover_rows` used to index `r["checks"][k] for k in
    PUBLISH_CHECKS` (the legacy 7-key tuple) unconditionally — a document
    carrying residuals.pdf returns the new 5-key surface instead, which
    shares no `model`/`stamp`/`residuals`/`index` key with it, so bulk
    handover raised KeyError on every such document. It must instead iterate
    whatever keys `publish_ready` actually returned.
    """
    from pdfdrill.commands import handover_rows
    # an unmeasured, non-straddling row fails coverage; a model the ink was
    # not measured against fails timestamp — both while artefacts/glyphs/ink
    # stay green, so `blocked_by` names exactly these two checks.
    d = _doc(tmp_path, shown=("D_EQ0001", "D_EQ0002", "D_EQ0003"),
             measured=("D_EQ0001", "D_EQ0002"))
    (d / "D.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "T",
                                                         "model_mtime": 200})
    rows = handover_rows(tmp_path)   # must not raise KeyError
    assert len(rows) == 1
    r = rows[0]
    assert not r["ready"]
    assert set(r["blocked_by"]) >= {"timestamp", "coverage"}
    assert "timestamp" in r["blocked_by"] and "coverage" in r["blocked_by"]
