"""234 — the five-item checklist, before handover.

The pages repo's CI already checks the PUBLISHED state. This checks the state
BEFORE publishing, and the two must not drift: two definitions of "ready" is
how a half-measured document goes up.
"""
import json

import pytest

from pdfdrill.commands import publish_ready, PUBLISH_CHECKS


def _doc(tmp_path, *, glyphs=False, ink=None, quarantine=None,
         bullets=2, legend=True, md=True, inspect=True, pdf=True):
    d = tmp_path / "DOC"
    d.mkdir(exist_ok=True)
    (d / "DOC.pdf").write_bytes(b"%PDF-1.4\n")
    log = "Output written on report.pdf (12 pages, 100 bytes).\n"
    if glyphs:
        log += 'Missing character: There is no g ("67) in font rsfs10!\n'
    (d / "report.log").write_text(log, encoding="utf-8")
    body = "\\ident{DOC_EQ0001}\n" + "\\inkbullet{inkClean}\n" * bullets
    if legend:
        body += r"\textbf{Residual} render vs scan (inkdrill):" + "\n"
    (d / "report.tex").write_text(body, encoding="utf-8")
    if pdf:
        (d / "report.pdf").write_bytes(b"%PDF-1.4\n")
    if md:
        (d / "DOC.md").write_text("x", encoding="utf-8")
    if inspect:
        (d / "DOC.inspect.html").write_text("<html>", encoding="utf-8")
    (d / "DOC.tiddlers.json").write_text(json.dumps(
        [{"title": "DOC_EQ0001", "latex": "x=1"},
         {"title": "DOC_EQ0002", "latex": "y=2"}]), encoding="utf-8")
    if ink is not None:
        (d / "report.ink.json").write_text(
            json.dumps({"rows": ink}), encoding="utf-8")
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
