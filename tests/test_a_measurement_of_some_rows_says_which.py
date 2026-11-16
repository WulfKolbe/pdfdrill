"""A measurement may cover some of a report's rows, and it must say which.

WHY THIS EXISTS. T-0144 part C judges candidate LaTeX by ink, through
`measure_doc.py` -> `pdfdrill inkreport`. Measured on the staged corpus, one
book costs 6,606 s (johnston: 446 measure-build pages, 250 of them measured)
and the test set holds six of them, 119-492 pages, times three arms. Only the
candidate rows matter. Library documents are named here by their bibkey or
folder id, never by title: the library's contents are not published (owner's
standing constraint; group house rule, 2026-11-16).

WHERE THE BILL IS, measured on j.nuclphysb.2018.09.006 (28 report pages, 196
rows) through the installed entry point with the model already stamped:

    2 build/measure      6 s
    3 measure          248 s      <- 95% of the run
    4 convert, 5 build/reading, 6 inspect   5 s

So the selection narrows STEP 3 and nothing else. Both builds stay full and
unbounded, which is not a compromise but the point:

  - report.tables.json still names every row the PDF ships, so 593's refusal
    of `--pages N` is untouched — that flag bounds the BUILD, `pagesel` drops
    pages at shipout, and the manifest then names rows the PDF does not carry;
  - every row renders at exactly the geometry a whole-document run gives it,
    so the verdicts are IDENTICAL BY CONSTRUCTION rather than by hope. The
    report PDF of a selected run is the same build.

WHICH SELECTOR, MEASURED rather than assumed. Over the 57 staged T-0144
documents, report pages rendered and compared:

    whole set                        1,163
    the candidate rows' source pages   570   (49%)
    the candidate rows themselves      246   (21%)

A page carries other rows, so `--only-pages` is twice as cheap and
`--only-rows` is five times. Both exist because the judge holds pages and the
coordinator asked for pages; the numbers are the reason judge.py should pass
row ids.

VERIFIED, on j.nuclphysb.2018.09.006 through the installed entry point. Every
measurement field of every row a selected run produced, against the same
identifier's row in the whole-document run — report_page, line, L, R,
distance, comp_delta, signed_delta, flag, rendered, code, crop_sha256:

    whole document                            196 rows, 25 pages, 309 s
    --only-pages 7,8,10,13,19,20,23,32,36      56 rows, 19 pages, 248 s
                                               56 x 11 fields, 0 differences
    --only-rows <the 10 candidate ids>         10 rows,  9 pages, 129 s
                                               10 x 11 fields, 0 differences

`build_sha256` is deliberately NOT among those fields: a PDF carries its own
creation time, so two builds of one document differ there while giving
identical verdicts (measured 2026-11-04 on ser7, 68 of 68).

AND A PARTIAL MEASUREMENT IS NOT ADOPTED. 585 established that the reading
build selects its sections FROM THE INK: a row the ink does not mention is not
flagged, so adopting a selection's ink would publish a report whose findings
describe the selection and whose cover describes the document (539's shape).
The chain stops after step 4 and says so.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import inkconvert as ic
from pdfdrill import inkmeasure as im
from pdfdrill import inkreport as ir
from pdfdrill import report_tex as rt

CAPTION = im.EQUATION_CAPTION


def _tables(tmp: Path, idents, caption=CAPTION):
    (tmp / "report.tables.json").write_text(json.dumps(
        {"bibkey": "doc", "tables": [
            {"caption": caption, "columns": "6", "legend": "True",
             "endhead": "True", "rows": len(idents),
             "identifiers": list(idents), "ordinal": "1"}]}),
        encoding="utf-8")


# ---------------------------------------------------------------- the selector

def test_a_selection_naming_nothing_in_the_table_refuses(tmp_path):
    """An empty result from a non-empty request reads exactly like a clean
    document, which is the one thing it must not do."""
    _tables(tmp_path, ["doc_EQ0001", "doc_EQ0002"])
    with pytest.raises(im.MeasureRefused) as e:
        im.measure(tmp_path / "report.pdf", tmp_path / "w",
                   only={"doc_EQ9999"})
    assert "doc_EQ9999" in str(e.value), \
        "the refusal does not name what was asked for: %s" % e.value
    assert CAPTION in str(e.value)


def test_the_refusal_comes_before_anything_is_rendered(tmp_path):
    """There is no report.pdf and no pdfdrill-rows.json in this folder, so a
    refusal proves the selection is resolved before the expensive part."""
    _tables(tmp_path, ["doc_EQ0001"])
    assert not (tmp_path / "report.pdf").exists()
    with pytest.raises(im.MeasureRefused):
        im.measure(tmp_path / "report.pdf", tmp_path / "w", only={"other"})


def test_no_selection_leaves_the_old_path_exactly_as_it_was(tmp_path):
    """`only=None` must not become `only=set()`. An empty table still returns
    [] and a populated one still reaches the manifest it needs."""
    _tables(tmp_path, [], caption=CAPTION)
    assert im.measure(tmp_path / "report.pdf", tmp_path / "w") == []
    _tables(tmp_path, ["doc_EQ0001"])
    with pytest.raises(im.MeasureRefused) as e:
        im.measure(tmp_path / "report.pdf", tmp_path / "w")
    assert "pdfdrill-rows.json" in str(e.value), \
        "an unselected run no longer reaches the rect manifest: %s" % e.value


# -------------------------------------------------- pages -> report rows

def _tiddlers(tmp: Path, rows):
    """rows: (kind, ordinal, page). The projector's own title scheme."""
    out = [{"title": "doc_%s%04d" % (k, n), "page": p,
            "latex": "x", "width": "100", "height": "10"}
           for k, n, p in rows]
    p = tmp / "doc.tiddlers.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    (tmp / "model.docmodel.json").write_text(
        json.dumps({"meta": {"bibkey": "doc"}}), encoding="utf-8")
    return p


def test_a_page_names_the_rows_printed_from_it(tmp_path):
    tp = _tiddlers(tmp_path, [("EQ", 1, "7"), ("EQ", 2, "7"), ("EQ", 3, "8")])
    got = rt.identifiers_on_pages(tp, ["7"])
    assert got["identifiers"] == {"doc_EQ0001", "doc_EQ0002"}, got
    assert got["empty"] == []


def test_a_leading_zero_is_the_same_page(tmp_path):
    """The library writes `007` and a caller types `7`. A page list that
    silently matched neither would measure nothing and say nothing."""
    tp = _tiddlers(tmp_path, [("EQ", 1, "007"), ("EQ", 2, "12")])
    assert rt.identifiers_on_pages(tp, ["7"])["identifiers"] == {"doc_EQ0001"}
    assert rt.identifiers_on_pages(tp, ["007"])["identifiers"] == {"doc_EQ0001"}


def test_a_page_with_no_row_is_reported_not_dropped(tmp_path):
    """`--only-pages 3,17,42` with one page mistyped would otherwise measure
    two pages and name the third nowhere."""
    tp = _tiddlers(tmp_path, [("EQ", 1, "3"), ("EQ", 2, "17")])
    got = rt.identifiers_on_pages(tp, ["3", "17", "42"])
    assert got["empty"] == ["42"], got
    assert len(got["identifiers"]) == 2


def test_every_kind_of_row_is_reachable_by_its_page(tmp_path):
    """Tables and figures are measured rows too; a page selector that saw only
    equations would drop them from a page that has them."""
    tp = _tiddlers(tmp_path, [("EQ", 1, "5"), ("TAB", 1, "5"),
                              ("DIA", 1, "5"), ("FO", 1, "5")])
    got = rt.identifiers_on_pages(tp, ["5"])
    assert {"doc_EQ0001", "doc_TAB0001", "doc_DIA0001"} <= got["identifiers"], \
        got["identifiers"]


# --------------------------------------------- the selection on the file

#: One row of a report, in the shape the projector prints. The demotion
#: aiming this file does NOT test lives in
#: tests/test_a_demotion_belongs_to_its_own_row.py.
_TEX = r"\ident{doc\_EQ0001}~ & 1 & $x$ & scan & 0 & 0 \\"

_HDR = ("identifier\treport_page\tline\t"
        + "\t".join(ic.FIVE_L) + "\t" + "\t".join(ic.FIVE_R) + "\tA_eq_B")


def _tsv(tmp: Path, idents):
    lines = [_HDR]
    for n, i in enumerate(idents, 1):
        lines.append("\t".join([i, "1", str(n)] + ["1"] * 5 + ["1"] * 5
                               + ["yes"]))
    p = tmp / "report.compare.tsv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_the_selection_is_written_into_the_ink(tmp_path):
    tex = tmp_path / "report.tex"
    tex.write_text(_TEX, encoding="utf-8")
    tsv = _tsv(tmp_path, ["doc_EQ0001"])
    sel = {"by": "rows", "asked": ["doc_EQ0001"],
           "identifiers": ["doc_EQ0001"]}
    payload = ic.convert(tsv, tex, selection=sel)
    assert payload["measured_selection"] == sel
    assert "measured_selection" not in ic.convert(tsv, tex), \
        "an unselected measurement must not claim a selection"


# ------------------------------------------------- the resume, question 7

def _ink_and_stamp(tmp: Path, *, sel=None, sha="abc123"):
    ink = {"rows": [], "measured_against": {"sha256": sha}}
    if sel is not None:
        ink["measured_selection"] = sel
    (tmp / "report.ink.json").write_text(json.dumps(ink), encoding="utf-8")
    (tmp / "report.build.measure.json").write_text(json.dumps(
        {"sha256": sha, "formula_rule": "all", "pages_bound": None,
         "geometry_sha256": rt.geometry_signature()}), encoding="utf-8")
    # the ink must post-date the stamp
    import os
    st = (tmp / "report.build.measure.json").stat()
    os.utime(tmp / "report.ink.json", (st.st_atime + 2, st.st_mtime + 2))


def test_a_full_measurement_does_not_resume_a_selection(tmp_path):
    _ink_and_stamp(tmp_path)
    why: list = []
    assert ir.fresh_ink(tmp_path, formula_rule="all", pages_bound=0,
                        selection={"identifiers": ["doc_EQ0001"]},
                        why=why) is False
    assert "whole report" in why[0] and "1 selected" in why[0], why


def test_a_selection_does_not_resume_the_document(tmp_path):
    _ink_and_stamp(tmp_path, sel={"identifiers": ["doc_EQ0001"]})
    why: list = []
    assert ir.fresh_ink(tmp_path, formula_rule="all", pages_bound=0,
                        selection=None, why=why) is False


def test_two_different_selections_do_not_resume_each_other(tmp_path):
    _ink_and_stamp(tmp_path, sel={"identifiers": ["doc_EQ0001"]})
    assert ir.fresh_ink(tmp_path, formula_rule="all", pages_bound=0,
                        selection={"identifiers": ["doc_EQ0002"]}) is False


def test_the_same_rows_asked_for_differently_do_resume(tmp_path):
    """The question is over the identifier SET, not over the request: a page
    list and the row ids on that page ask for one measurement."""
    _ink_and_stamp(tmp_path, sel={"by": "pages", "asked": ["7"],
                                  "identifiers": ["doc_EQ0001",
                                                  "doc_EQ0002"]})
    assert ir.fresh_ink(tmp_path, formula_rule="all", pages_bound=0,
                        selection={"by": "rows",
                                   "asked": ["doc_EQ0002", "doc_EQ0001"],
                                   "identifiers": ["doc_EQ0002",
                                                   "doc_EQ0001"]}) is True


def test_an_unselected_run_against_an_unselected_ink_still_resumes(tmp_path):
    """The new question must not break the resume that already worked."""
    _ink_and_stamp(tmp_path)
    why: list = []
    assert ir.fresh_ink(tmp_path, formula_rule="all", pages_bound=0,
                        why=why) is True, why
