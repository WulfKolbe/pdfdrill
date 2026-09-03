"""234 — the five-item checklist, before handover.

The pages repo's CI already checks the PUBLISHED state. This checks the state
BEFORE publishing, and the two must not drift: two definitions of "ready" is
how a half-measured document goes up.
"""
import json

import pytest

from pdfdrill.commands import publish_ready, PUBLISH_CHECKS


def _doc(tmp_path, *, glyphs=False, ink=None, quarantine=None,
         bullets=2, legend=True, md=True, inspect=True, pdf=True,
         measured_against=True):
    d = tmp_path / "DOC"
    d.mkdir(exist_ok=True)
    (d / "DOC.pdf").write_bytes(b"%PDF-1.4\n")
    log = "Output written on report.pdf (12 pages, 100 bytes).\n"
    if glyphs:
        log += 'Missing character: There is no g ("67) in font rsfs10!\n'
    (d / "report.log").write_text(log, encoding="utf-8")
    # The real report.tex is a TABLE: `\ident{..} & <page> & ..`, which is the
    # shape `inkconvert.identifiers()` reads. The fixture used to write a bare
    # `\ident{..}`, which yields NO identifiers — so a coverage check had
    # nothing to compare against and passed silently. Four rows, matching
    # SPREAD, so full coverage is the default and a test that wants a gap
    # creates one deliberately.
    body = "".join("\\ident{DOC_EQ%04d} & %d & x\n" % (i, i) for i in (1, 2, 3, 4))
    body += "\\inkbullet{inkClean}\n" * bullets
    if legend:
        body += r"\textbf{Residual} render vs scan (inkdrill):" + "\n"
    (d / "report.tex").write_text(body, encoding="utf-8")
    if pdf:
        (d / "report.pdf").write_bytes(b"%PDF-1.4\n")
    if md:
        (d / "DOC.md").write_text("x", encoding="utf-8")
    if inspect:
        (d / "DOC.inspect.html").write_text("<html>", encoding="utf-8")
    # 435 — the fixture carries a MODEL and a build stamp naming it. A report
    # with no model beside it cannot be checked against one, and publishready
    # now says so rather than passing quietly. A fixture without a model was
    # asserting readiness for a document shape that cannot occur in the
    # library.
    (d / "model.docmodel.json").write_text(
        json.dumps({"meta": {"bibkey": "DOC"}, "objects": []}),
        encoding="utf-8")
    # Written by the REAL stamp writer, not hand-rolled: a hand-made stamp got
    # the byte count wrong and failed `stamp_matches`, which is a check about
    # the report rather than about the model.
    from pdfdrill import report_tex as _rt
    if (d / "report.pdf").is_file():
        _rt.write_build_stamp(d / "report.pdf", legend=legend, ink_adopted=False,
                              prefer_refined=False, filters={})
    (d / "DOC.tiddlers.json").write_text(json.dumps(
        [{"title": "DOC_EQ0001", "latex": "x=1"},
         {"title": "DOC_EQ0002", "latex": "y=2"}]), encoding="utf-8")
    if ink is not None:
        # 539 — the ink SAYS WHICH REPORT IT MEASURED, because publishready
        # now asks. A fixture whose ink named no build was asserting
        # readiness for a state the gate exists to refuse.
        payload = {"rows": ink}
        if measured_against is not False:
            stamp_p = d / _rt.phase_stamp_name("measure")
            if not stamp_p.is_file() and (d / "report.pdf").is_file():
                _rt.write_build_stamp(d / "report.pdf", legend=False,
                                      ink_adopted=False, prefer_refined=False,
                                      filters={}, findings=False)
                (d / _rt.BUILD_STAMP).replace(stamp_p)
                # and re-stamp the reading build the report actually is
                _rt.write_build_stamp(d / "report.pdf", legend=legend,
                                      ink_adopted=False, prefer_refined=False,
                                      filters={}, findings=False)
            if stamp_p.is_file():
                payload[_rt.MEASURED_AGAINST] = json.loads(
                    stamp_p.read_text(encoding="utf-8"))
        (d / "report.ink.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    if quarantine:
        (d / quarantine).write_text("{}", encoding="utf-8")
    return d / "DOC.pdf"


SPREAD = [{"id": "DOC_EQ0001", "code": "K|0"},
          {"id": "DOC_EQ0002", "code": "C|+4"},
          {"id": "DOC_EQ0003", "code": "N|+1"},
          {"id": "DOC_EQ0004", "code": "S|+9"}]


def test_a_complete_document_is_ready(tmp_path):
    r = publish_ready(_doc(tmp_path, ink=SPREAD))
    assert r["ready"], r["checks"]
    assert set(r["checks"]) == set(PUBLISH_CHECKS)
    assert r["fields"]["pages"] == 12
    assert r["fields"]["equations"] == 2
    assert r["fields"]["residual"] == {"K": 1, "C": 1, "N": 1, "S": 1}


def test_a_dropped_glyph_blocks_it(tmp_path):
    r = publish_ready(_doc(tmp_path, ink=SPREAD, glyphs=True))
    assert not r["ready"]
    assert not r["checks"]["glyphs"][0]
    # the detail is the log's own words — the count and the first casualty,
    # not a paraphrase of them
    assert r["checks"]["glyphs"][1].startswith("1 dropped:")
    assert "There is no g" in r["checks"]["glyphs"][1]


def test_no_measurement_blocks_it(tmp_path):
    r = publish_ready(_doc(tmp_path))
    assert not r["ready"]
    assert "no residual measurement has been run" in r["checks"]["ink"][1]


def test_a_NEWER_quarantine_blocks_it(tmp_path):
    """The last thing that happened was a failure to pair."""
    pdf = _doc(tmp_path, ink=SPREAD)
    q = pdf.parent / "report.ink.json.MISPAIRED"
    q.write_text("{}", encoding="utf-8")
    import os, time
    os.utime(q, (time.time() + 60, time.time() + 60))
    r = publish_ready(pdf)
    assert not r["checks"]["ink"][0]
    assert "NEWER" in r["checks"]["ink"][1]


def test_an_OLDER_quarantine_is_superseded_not_a_veto(tmp_path):
    """0902.0431 carries a MISPAIRED from an earlier attempt beside a later
    measurement that paired. The earlier failure is history, not a verdict."""
    pdf = _doc(tmp_path, ink=SPREAD, quarantine="report.ink.json.MISPAIRED")
    import os, time
    os.utime(pdf.parent / "report.ink.json.MISPAIRED",
             (time.time() - 600, time.time() - 600))
    r = publish_ready(pdf)
    assert r["checks"]["ink"][0]
    assert "superseded" in r["checks"]["ink"][1]


def test_a_flat_distribution_is_a_pairing_failure_not_a_result(tmp_path):
    """0902.0431: 55 of 55 rows class C, cell distances to 1182, one pair
    reading 13 components against 708. The five classes exist to separate
    cases; a probe returning one class for every row separated nothing."""
    flat = [{"id": f"DOC_EQ{i:04d}", "code": "C|+9"} for i in range(1, 8)]
    r = publish_ready(_doc(tmp_path, ink=flat))
    assert not r["ready"]
    assert "no variation" in r["checks"]["residuals"][1]


def test_all_clean_is_the_one_honest_uniform_answer(tmp_path):
    clean = [{"id": f"DOC_EQ{i:04d}", "code": "K|0"} for i in range(1, 8)]
    r = publish_ready(_doc(tmp_path, ink=clean))
    assert r["checks"]["residuals"][0], r["checks"]["residuals"][1]


def test_bullets_without_the_legend_block_it(tmp_path):
    r = publish_ready(_doc(tmp_path, ink=SPREAD, legend=False))
    assert not r["checks"]["residuals"][0]
    assert "ABSENT" in r["checks"]["residuals"][1]


@pytest.mark.parametrize("miss", ["md", "inspect", "pdf"])
def test_a_missing_travelling_artefact_blocks_it(tmp_path, miss):
    r = publish_ready(_doc(tmp_path, ink=SPREAD, **{miss: False}))
    assert not r["checks"]["artefacts"][0]


def test_a_check_that_cannot_see_its_input_FAILS(tmp_path):
    """out/213 had six reports exit 0 with glyphs silently discarded. A gate
    must be harder to satisfy than the thing it guards."""
    d = tmp_path / "EMPTY"
    d.mkdir()
    (d / "EMPTY.pdf").write_bytes(b"%PDF-1.4\n")
    r = publish_ready(d / "EMPTY.pdf")
    assert not r["ready"]
    assert not r["checks"]["glyphs"][0]
    assert "no report.log" in r["checks"]["glyphs"][1]


def test_a_measurement_that_lands_on_NO_rows_is_a_join_failure(tmp_path):
    """237c. residual_colour returns inkUnmeasured for an identifier it cannot
    find, so a measurement whose identifiers do not intersect this report's
    rows renders as a fully measured report in which nothing could be
    measured — indistinguishable, on the page, from a document nobody
    measured.

    The shape is a comparison whose two populations cannot overlap. A peer hit
    it the same week from the other side: 0 of 26 "confirmed" between an
    ink.json holding only EQ identifiers and a text layer yielding only FO
    ones. That test could not have returned a hit under any circumstances,
    including the one where everything is correct."""
    foreign = [{"id": "SOMEONE_ELSE_EQ%04d" % i, "code": "K|0"}
               for i in range(1, 8)]
    r = publish_ready(_doc(tmp_path, ink=foreign))
    assert not r["ready"]
    assert "join failure" in r["checks"]["residuals"][1]


def test_a_measurement_that_lands_is_not_flagged(tmp_path):
    good = [{"id": "DOC_EQ0001", "code": "K|0"},
            {"id": "DOC_EQ0002", "code": "C|+4"},
            {"id": "DOC_EQ0001", "code": "N|+1"},
            {"id": "DOC_EQ0002", "code": "S|+9"}]
    r = publish_ready(_doc(tmp_path, ink=good))
    assert r["checks"]["residuals"][0], r["checks"]["residuals"][1]


# --- 241: credibility, over rendered rows only -----------------------------

def _fives(l, r):
    return {"L": [l, 0, 0, 0, 0], "R": [r, 0, 0, 0, 0]}


def test_an_implausible_measurement_is_refused(tmp_path):
    """0902.0431's shape: most rows disagreeing wildly on component count is a
    pairing failure, not a document that reads badly."""
    from pdfdrill import report_tex as rt
    rows = [dict(id="DOC_EQ%04d" % i, code="C|+9", **_fives(10, 800))
            for i in range(1, 12)]
    r = publish_ready(_doc(tmp_path, ink=rows))
    assert not r["ready"]
    assert "not credible" in r["checks"]["residuals"][1]


def test_a_DEMOTED_row_does_not_make_a_document_implausible(tmp_path):
    """The false positive in the threshold I derived and handed to the pages
    gate. A row demoted to (not rendered) has no rendered mathematics, so its
    render is a tiny constant against a full scan cell and the ratio is
    legitimately enormous. 2010.14265 is 62.5% demoted: p90 8.62 over all rows,
    1.00 over rendered ones — refused as implausible while perfectly paired."""
    from pdfdrill import report_tex as rt
    pdf = _doc(tmp_path, ink=[dict(id="DOC_EQ0001", code="K|0", **_fives(50, 50)),
                              dict(id="DOC_EQ0002", code="C|+9", **_fives(13, 700))])
    # mark the SECOND row's identifier as demoted in the tex
    tex = pdf.parent / "report.tex"
    tex.write_text(
        "\\ident{DOC_EQ0001} & 1 & x\n"
        "\\ident{DOC_EQ0002} & 2 & \\emph{(not rendered)}\n"
        "\\inkbullet{inkClean}\n\\inkbullet{inkClean}\n"
        r"\textbf{Residual} render vs scan (inkdrill):" + "\n",
        encoding="utf-8")
    r = publish_ready(pdf)
    assert r["checks"]["residuals"][0], r["checks"]["residuals"][1]


def test_the_ratio_is_scale_free_and_order_free():
    from pdfdrill import report_tex as rt
    a = [{"L": [10, 0, 0, 0, 0], "R": [80, 0, 0, 0, 0]}] * 10
    b = [{"L": [80, 0, 0, 0, 0], "R": [10, 0, 0, 0, 0]}] * 10
    assert rt.component_ratio_p90(a) == rt.component_ratio_p90(b) == 8.0


def test_demoted_flags_reads_table_order():
    from pdfdrill import report_tex as rt
    body = ("\\ident{X_EQ0001} & 1 & rendered\n"
            "\\ident{X_EQ0002} & 2 & \\emph{(not rendered)}\n"
            "\\ident{X_EQ0003} & 3 & rendered\n")
    assert rt.demoted_flags(body) == [True, False, True]


def test_ink_coverage_is_compared_against_the_report(tmp_path):
    """A measurement can pair perfectly and still cover only part of the report:
    rebuild it with different filters afterwards and every measured row still
    matches while the new rows carry nothing. 1510.06699 reached READY at 219 of
    279 rows, because "bullets on the page" counts rows that DISPLAY a bullet and
    the distribution is read off the measurement, not off the report."""
    pdf = _doc(tmp_path, ink=SPREAD)
    tex = pdf.parent / "report.tex"          # _doc returns the PDF, not the dir
    body = tex.read_text(encoding="utf-8")
    # the table-row shape `identifiers()` actually reads: `\ident{..} & N &`
    body += "\\ident{DOC_EQ0005} & 5 & x\n\\ident{DOC_EQ0006} & 6 & x\n"
    tex.write_text(body, encoding="utf-8")
    r = publish_ready(pdf)
    assert not r["ready"]
    passed, why = r["checks"]["ink"]
    assert not passed
    assert "4 of 6" in why, why
    assert "2 carry no measurement" in why, why


def test_full_coverage_still_passes(tmp_path):
    r = publish_ready(_doc(tmp_path, ink=SPREAD))
    passed, why = r["checks"]["ink"]
    assert passed, why
    assert "MEASURES ONLY" not in why and "UNKNOWN" not in why


def test_coverage_that_cannot_be_computed_fails_rather_than_passing(tmp_path):
    """report.tex not in the table shape identifiers() reads: coverage is
    unknown, and publish_ready's whole rule is that such a check FAILS."""
    pdf = _doc(tmp_path, ink=SPREAD)
    (pdf.parent / "report.tex").write_text(
        "Residual} render vs scan\n\\inkbullet{inkClean}\n", encoding="utf-8")
    r = publish_ready(pdf)
    passed, why = r["checks"]["ink"]
    assert not passed
    assert "coverage UNKNOWN" in why


# ---------------------------------------------------------------- 539

def test_stamp_refuses_an_ink_that_names_no_build(tmp_path):
    """An ink that cannot say what it measured is not evidence about it."""
    r = publish_ready(_doc(tmp_path, ink=SPREAD, measured_against=False))
    assert not r["ready"]
    assert not r["checks"]["stamp"][0]
    assert "does not say which report" in r["checks"]["stamp"][1]


def test_stamp_accepts_a_full_listing_measurement_that_covers_every_row(tmp_path):
    """585 — the two builds are now different BY DESIGN, and this test says
    what replaced the sameness rule.

    516 rebuilt 21 reports into the findings shape while the ink still
    described the full listing that preceded it, and 539 made publishready
    refuse any measurement of a differently-shaped report. 585 reverses the
    direction: the measure build IS the full listing, unbounded, because the
    findings shape selects its rows from the ink and a row the ink never saw
    can never be flagged (Stage C: five of five completed measurements lost
    their flagged set).

    So a shape difference is no longer the question. The question is whether
    every row the published report SHOWS was in the measured set.
    """
    import json as _json
    from pdfdrill import report_tex as _rt
    pdf = _doc(tmp_path, ink=SPREAD)
    d = pdf.parent

    def _remeasure(shown):
        meas = d / _rt.phase_stamp_name("measure")
        st = _json.loads(meas.read_text())
        st["pages"], st["findings"], st["formula_rule"] = 276, False, "all"
        meas.write_text(_json.dumps(st))
        payload = _json.loads((d / "report.ink.json").read_text())
        payload[_rt.MEASURED_AGAINST] = st
        (d / "report.ink.json").write_text(_json.dumps(payload))
        (d / "report.pdf").write_bytes(b"%PDF-1.4\n" + b"findings" * 100)
        _rt.write_build_stamp(d / "report.pdf", legend=True, ink_adopted=True,
                              prefer_refined=False, filters={}, findings=True,
                              bullets=True)
        (d / _rt.BUILD_STAMP).replace(d / _rt.phase_stamp_name("reading"))
        (d / _rt.TABLES_MANIFEST).write_text(_json.dumps(
            {"bibkey": "DOC", "tables": [{"caption": "Flagged, not acted on",
                                          "identifiers": shown}]}))
        return _rt.ink_describes_published(d)

    measured = sorted({r["id"] for r in SPREAD})
    ok, detail = _remeasure(measured)
    assert ok, detail
    assert "covers all" in detail

    # and the guarantee that replaced sameness: a shown row nobody measured
    ok2, detail2 = _remeasure(measured + ["DOC_EQ9999"])
    assert not ok2
    assert "never measured" in detail2 and "DOC_EQ9999" in detail2


def test_a_findings_build_with_no_tables_manifest_is_refused(tmp_path):
    """551 — report.tables.json was empty in 21 of 21 and every reader agreed
    with it. A coverage check with nothing to compare must not pass."""
    import json as _json
    from pdfdrill import report_tex as _rt
    pdf = _doc(tmp_path, ink=SPREAD)
    d = pdf.parent
    meas = d / _rt.phase_stamp_name("measure")
    st = _json.loads(meas.read_text())
    payload = _json.loads((d / "report.ink.json").read_text())
    payload[_rt.MEASURED_AGAINST] = st
    (d / "report.ink.json").write_text(_json.dumps(payload))
    _rt.write_build_stamp(d / "report.pdf", legend=True, ink_adopted=True,
                          prefer_refined=False, filters={}, findings=True,
                          bullets=True)
    (d / _rt.BUILD_STAMP).replace(d / _rt.phase_stamp_name("reading"))
    (d / _rt.TABLES_MANIFEST).write_text(_json.dumps({"tables": []}))
    ok, detail = _rt.ink_describes_published(d)
    assert not ok and "names no rows" in detail, detail

def test_stamp_passes_when_the_ink_measured_this_exact_report(tmp_path):
    """585 — still passes, but no longer by SHORT-CIRCUIT.

    This used to return True the instant the ink's sha matched report.pdf.
    That is also the state where report.pdf IS the measure build — phase-1
    scaffolding published as the artefact, which 557's sweep left on six of
    nine documents — so matching shas is necessary and never sufficient. The
    coverage check now runs on every success path, and the detail says so.
    """
    import json as _json
    from pdfdrill import report_tex as _rt
    pdf = _doc(tmp_path, ink=SPREAD)
    d = pdf.parent
    live = _rt.build_stamp(d / "report.pdf")
    payload = _json.loads((d / "report.ink.json").read_text())
    payload[_rt.MEASURED_AGAINST] = live
    (d / "report.ink.json").write_text(_json.dumps(payload))
    ok, detail = _rt.ink_describes_published(d)
    assert ok, detail
    assert "covers all" in detail, detail
