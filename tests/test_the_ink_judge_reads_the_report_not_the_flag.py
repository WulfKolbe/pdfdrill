"""The ink judge's two measured rules, as tests.

Both were learned on 2026-11-13 while building T-0144 part B, and both are
invisible to a test that only checks the happy path:

 1. `does_not_compile` comes from the REPORT'S TEXT, not from the `unrendered`
    flag. The flag errs in both directions — four unrelated non-compiling
    candidates each came back `flag: weak, distance 10, rendered True` (the ink
    of the italic words "(not rendered)"), and a VALID wrong answer came back
    `flag: unrendered, rendered: False` at the distance it scores alone.

 2. A demoted row reports NO DISTANCE. Its number is the ink of that
    placeholder, constant for every non-compiling candidate, so publishing it
    as a distance would make garbage read as a near miss.
"""
import json

from pdfdrill import inkjudge as J


def _tex(tmp_path, rows):
    """A report.tex with one longtable row per (ident, rendered-cell)."""
    lines = []
    for ident, cell in rows:
        esc = ident.replace("_", "\\_")
        lines.append(
            "\\ident{%s}~\\eqnum{(1)} & 001 & \\confcell{confgreen}{1.000} & "
            "{\\ttfamily x} & \\FitMath{%s} & \\includegraphics{c.jpg} \\\\ \\hline"
            % (esc, cell))
    p = tmp_path / "report.tex"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_a_demoted_row_is_read_from_the_reports_own_text(tmp_path):
    tex = _tex(tmp_path, [("doc_EQ0001", "$\\displaystyle a=b$"),
                          ("doc_EQ0002", "\\emph{(not rendered)}")])
    assert J.unrendered_ids(tex) == {"doc_EQ0002"}


def test_the_identifier_survives_the_projectors_escaping(tmp_path):
    """`\\allowbreak{}` is sprinkled through an ident and `_` is escaped; a
    naive read of the cell returns neither the row id nor an error."""
    ident = "A_Book__Z-Library__EQ0007"
    esc = ident.replace("_", "\\_\\allowbreak{}")
    tex = tmp_path / "report.tex"
    tex.write_text("\\ident{%s}~\\eqnum{(7)} & \\FitMath{\\emph{(not rendered)}} \\\\"
                   % esc, encoding="utf-8")
    assert J.unrendered_ids(tex) == {ident}


def test_the_flag_does_not_decide_that_a_row_compiled():
    """FALSE NEGATIVE: the chain says rendered True, flag `weak`, distance 10.
    The report demoted it, so the verdict is does_not_compile and the 10 is
    not published as a distance."""
    v = {"distance": 10, "comp_delta": 2, "flag": "weak", "rendered": True}
    assert J.verdict(v, demoted=True) == "does_not_compile"
    rec = J.record("r", "d", "arm", v, demoted=True, batch_demoted=True,
                   batch_flagged=False, solo_rerun=True, build_demotions=1)
    assert rec["distance"] is None, "a demoted row must report no distance"
    assert rec["placeholder_distance"] == 10
    assert rec["comp_delta"] is None
    assert rec["exact"] is False


def test_the_flag_does_not_decide_that_a_row_failed():
    """FALSE POSITIVE: flag `unrendered`, rendered False — but the report did
    not demote it and the distance is the one it scores alone. It rendered."""
    v = {"distance": 27, "comp_delta": 6, "flag": "unrendered", "rendered": False}
    assert J.verdict(v, demoted=False) == "differs"
    rec = J.record("r", "d", "arm", v, demoted=False, batch_demoted=False,
                   batch_flagged=True, solo_rerun=True, build_demotions=0)
    assert rec["distance"] == 27, "a row the report kept keeps its distance"
    assert rec["placeholder_distance"] is None


def test_the_flag_still_raises_a_suspicion():
    """It decides nothing, but it is the only other witness, so a row it
    points at is re-asked alone rather than trusted."""
    measured = {"a": {"distance": 0, "flag": "clean", "rendered": True},
                "b": {"distance": 27, "flag": "unrendered", "rendered": False},
                "c": {"distance": 3, "flag": "weak", "rendered": True}}
    assert J.suspects(measured, demoted={"c"}) == {"b", "c"}


def test_distance_zero_is_exact_and_nothing_else_is():
    assert J.verdict({"distance": 0}, demoted=False) == "exact"
    assert J.verdict({"distance": 1}, demoted=False) == "differs"
    assert J.verdict({"distance": None}, demoted=False) == "not_comparable"
    assert J.verdict(None, demoted=False) == "not_measured"


def test_only_rows_the_chain_says_it_rendered_become_verdicts(tmp_path):
    """NAMING A PROVENANCE IS NOT RENDERING IT. A report that rendered one row
    from the provenance measured the OTHER rows' own model LaTeX against their
    own crops, which looks like a result and is not one."""
    ink = tmp_path / "report.ink.json"
    ink.write_text(json.dumps({
        "measured_against": {"rendered_from_provenance": 1,
                             "rendered_ids": ["doc_EQ0001"], "commit": "abc"},
        "rows": [{"id": "doc_EQ0001", "distance": 0, "flag": "clean"},
                 {"id": "doc_EQ0002", "distance": 4, "flag": "weak"}]}),
        encoding="utf-8")
    got, demoted = J.read_pass(ink, _tex(tmp_path, []), alias={})
    assert set(got) == {"doc_EQ0001"}
    assert demoted == set()


def test_the_report_id_is_translated_back_to_the_arms_row_id(tmp_path):
    """A verdict must carry the ARM's id, not ours: the organizer joins on it."""
    ink = tmp_path / "report.ink.json"
    ink.write_text(json.dumps({
        "measured_against": {"rendered_from_provenance": 1,
                             "rendered_ids": ["A_Book__EQ0007"]},
        "rows": [{"id": "A_Book__EQ0007", "distance": 0}]}), encoding="utf-8")
    alias = {"A_Book__EQ0007": "A Book (Z-Library)_EQ0007"}
    got, _ = J.read_pass(ink, tmp_path / "nope.tex", alias)
    assert "A Book (Z-Library)_EQ0007" in got
    assert got["A Book (Z-Library)_EQ0007"]["report_id"] == "A_Book__EQ0007"


# ── the join, which is where this machinery lost 69 % of its work ───────────

def _fake_doc(titles):
    """A stand-in with just the objects `object_for_row` touches."""
    class _O:
        def __init__(self):
            self.realizations = []
            self.props = {}

        def add_realization(self, r):
            self.realizations.append(r)

    class _D:
        def __init__(self):
            self.objects = {oid: _O() for oid in titles}
            self.meta = {}
    return _D()


def _titles_by_id(titles):
    return lambda doc, bibkey: dict(titles)


def _sanitize(t):
    """The projector's rule: spaces and punctuation become underscores."""
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", str(t))


def test_a_raw_row_id_joins_when_the_name_is_an_arxiv_id():
    titles = {"o1": "1911.02782_EQ0001"}
    doc = _fake_doc(titles)
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "1911.02782", "1911.02782_EQ0001") == "o1"


def test_a_punctuated_book_name_joins_only_after_sanitising():
    """THE CASE THAT WAS SILENTLY LOST. The arm builds the id from the RAW
    folder name; our titles are sanitised. Measured 2026-11-03: 199 of 233
    documents joined raw, and the 34 that did not held 15,394 of 22,385 rows —
    reported as "the join matched 0 of N rows"."""
    raw = "Algebraic Number Theory (DISCRETE) (Z-Library)_EQ0001"
    titles = {"o9": _sanitize(raw)}
    doc = _fake_doc(titles)
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "Algebraic Number Theory (DISCRETE) (Z-Library)",
                            raw) == "o9"


def test_a_renamed_stem_joins_on_the_shared_ordinal_when_asked():
    """Defect 516: the model's bibkey is the RESOLVED key, so its titles read
    `<bibkey>_EQnnnn` while the arm built `<folder name>_EQnnnn`. Opt-in."""
    titles = {"o3": "crane2020_EQ0007"}
    doc = _fake_doc(titles)
    assert J.object_for_row(
        _titles_by_id(titles), _sanitize, doc, "crane2020",
        "ConformalGeometryOfSimplicialSurfaces_EQ0007",
        allow_ordinal_fallback=True) == "o3"


def test_the_ordinal_substitution_is_off_by_default():
    """IT MATCHES ACROSS DOCUMENTS, and one candidates file shared over the
    documents an arm covers is the intended use. On by default,
    `someotherdoc_EQ0001` is judged against THIS document's first equation and
    reported as a result — measured on wzlxjtu-004, distance 8."""
    titles = {"o1": "wzlxjtu_004_EQ0001"}
    doc = _fake_doc(titles)
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "wzlxjtu-004", "someotherdoc_EQ0001") is None
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "wzlxjtu-004", "someotherdoc_EQ0001",
                            allow_ordinal_fallback=True) == "o1", (
        "with the fallback on it DOES match across documents — which is why "
        "it is opt-in")


def test_the_ordinal_substitution_never_overrides_a_real_match():
    """It is applied ONLY when both real spellings have failed, so a document
    whose own naming produced a match keeps it."""
    titles = {"own": "MyDoc_EQ0007", "bib": "resolved_EQ0007"}
    doc = _fake_doc(titles)
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "resolved", "MyDoc_EQ0007",
                            allow_ordinal_fallback=True) == "own"


def test_a_row_id_naming_no_object_is_reported_not_invented():
    titles = {"o1": "doc_EQ0001"}
    doc = _fake_doc(titles)
    assert J.object_for_row(_titles_by_id(titles), _sanitize, doc,
                            "doc", "doc_EQ0999") is None


def test_injecting_replaces_this_provenances_previous_candidate():
    """A second pass must measure the candidate it was GIVEN, not the one
    before it — the solo rerun depends on that."""
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.role = kw.get("role")
            self.provenance = kw.get("provenance")

    titles = {"o1": "doc_EQ0001"}
    doc = _fake_doc(titles)
    tb, san = _titles_by_id(titles), _sanitize
    rows = [{"row_id": "doc_EQ0001", "latex": "first"}]
    J.inject(doc, "doc", rows, "arm", titles_by_id=tb, sanitize=san,
             realization_cls=_R)
    rows = [{"row_id": "doc_EQ0001", "latex": "second"}]
    n, missing, alias = J.inject(doc, "doc", rows, "arm", titles_by_id=tb,
                                 sanitize=san, realization_cls=_R)
    rs = doc.objects["o1"].realizations
    assert n == 1 and missing == []
    assert len(rs) == 1, "the earlier candidate of this provenance must be gone"
    assert rs[0].props["latex"] == "second"
    assert alias["doc_EQ0001"] == "doc_EQ0001"


def test_injecting_leaves_another_provenances_candidate_alone():
    """Two arms' verdicts must be tellable apart in one model."""
    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.role = kw.get("role")
            self.provenance = kw.get("provenance")

    titles = {"o1": "doc_EQ0001"}
    doc = _fake_doc(titles)
    tb, san = _titles_by_id(titles), _sanitize
    J.inject(doc, "doc", [{"row_id": "doc_EQ0001", "latex": "G3"}], "g3",
             titles_by_id=tb, sanitize=san, realization_cls=_R)
    J.inject(doc, "doc", [{"row_id": "doc_EQ0001", "latex": "G2"}], "g2",
             titles_by_id=tb, sanitize=san, realization_cls=_R)
    got = {r.provenance: r.props["latex"] for r in doc.objects["o1"].realizations}
    assert got == {"g3": "G3", "g2": "G2"}
