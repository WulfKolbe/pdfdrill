"""509 — the three findings states, selected once and shared with corrections.html."""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import corrections as C, report_tex as rt


def _doc(tmp_path, objects, tiddlers, bibkey="d"):
    (tmp_path / "model.docmodel.json").write_text(json.dumps(
        {"meta": {"bibkey": bibkey}, "objects": objects}))
    tp = tmp_path / f"{bibkey}.tiddlers.json"
    tp.write_text(json.dumps(tiddlers))
    return tp


def _pair_obj(before, after, region, page="001", verified="ink"):
    return {"id": "obj_1", "type": "Equation",
            "props": {"latex": before, "latex_refined": after, "page": page,
                      "region": region},
            "realizations": [{"provenance": "change",
                              "props": {"latex_refined": after,
                                        "verified_by": verified,
                                        "basis": "measured"}}]}


REGION = {"top_left_x": 10, "top_left_y": 20, "width": 30, "height": 40}


def test_the_selection_is_the_one_corrections_html_uses(tmp_path):
    """422's lesson as a test: one implementation, two renderers."""
    _doc(tmp_path, [_pair_obj("A", "B", REGION)],
         [{"title": "d_EQ0001", "latex": "A", "page": "001",
           "top_left_x": 10, "top_left_y": 20, "width": 30, "height": 40}])
    pairs = C.pairs_in(tmp_path)
    assert len(pairs) == 1 and pairs[0]["before"] == "A" and pairs[0]["after"] == "B"
    assert rt.corrected_pairs(tmp_path)[0]["identifier"] == "d_EQ0001"


def test_an_unverified_change_is_not_a_correction(tmp_path):
    o = _pair_obj("A", "B", REGION, verified=None)
    o["realizations"][0]["props"].pop("verified_by")
    _doc(tmp_path, [o], [])
    assert C.pairs_in(tmp_path) == []


def test_a_corrected_row_is_not_ALSO_reported_unresolved(tmp_path):
    r"""502's pair is exactly this: `\mathscr{g}` renders nothing at all,
    so without the exclusion it would appear in both sections."""
    tp = _doc(tmp_path, [_pair_obj(r"\mathscr{g}", r"\mathscr{J}", REGION)],
              [{"title": "d_EQ0001", "latex": r"a & b", "page": "001",
                "top_left_x": 10, "top_left_y": 20, "width": 30,
                "height": 40}])
    tids = json.loads(tp.read_text())
    f = rt.findings_rows(tids, "d", tmp_path)
    assert len(f["corrected"]) == 1
    assert [u["identifier"] for u in f["unresolved"]] == []


def test_an_unrendered_row_with_no_correction_is_unresolved(tmp_path):
    tp = _doc(tmp_path, [], [{"title": "d_EQ0002", "latex": "a & b",
                              "page": "002"}])
    f = rt.findings_rows(json.loads(tp.read_text()), "d", tmp_path)
    assert [u["identifier"] for u in f["unresolved"]] == ["d_EQ0002"]


def test_doubted_needs_BOTH_low_confidence_and_ink_agreement(tmp_path):
    tp = _doc(tmp_path, [], [
        {"title": "d_EQ0003", "latex": "x^2", "page": "003", "confidence": 0.01},
        {"title": "d_EQ0004", "latex": "y^2", "page": "004", "confidence": 0.01},
        {"title": "d_EQ0005", "latex": "z^2", "page": "005", "confidence": 0.9}])
    tids = json.loads(tp.read_text())
    ink = {"d_EQ0003": {"code": "K|+0"},      # low conf, ink agrees
           "d_EQ0004": {"code": "C|+40"},     # low conf, ink DISAGREES
           "d_EQ0005": {"code": "K|+0"}}      # ink agrees, confident
    f = rt.findings_rows(tids, "d", tmp_path, ink=ink)
    assert [d["identifier"] for d in f["doubted"]] == ["d_EQ0003"]


def test_a_clean_document_yields_nothing_in_all_three(tmp_path):
    """The right answer for a clean document, with no special case."""
    tp = _doc(tmp_path, [], [{"title": "d_EQ0006", "latex": "x^2",
                              "page": "006", "confidence": 0.99}])
    f = rt.findings_rows(json.loads(tp.read_text()), "d", tmp_path,
                         ink={"d_EQ0006": {"code": "K|+0"}})
    assert (f["corrected"], f["unresolved"], f["doubted"]) == ([], [], [])


def test_the_ink_classes_that_count_as_agreement():
    assert rt.INK_AGREES == {"K", "N", "S"}
    assert "C" not in rt.INK_AGREES and "W" not in rt.INK_AGREES


def test_an_all_none_region_does_not_match_a_page_tiddler(tmp_path):
    """It did: 0707.4470_FO0175's identifier came back as _PAGE_029."""
    _doc(tmp_path, [], [{"title": "d_PAGE_001", "latex": None}])
    assert C.identifier_for({"doc": tmp_path.name, "page": "001",
                             "region": {}, "before": "zzz"},
                            tmp_path.parent) is None


def test_a_unique_latex_identifies_a_row_the_region_cannot_reach(tmp_path):
    """An FO tiddler carries no region at all (488), so the region join is
    structurally impossible for inline formulas."""
    _doc(tmp_path, [], [{"title": "d_FO0175", "latex": r"\mathscr{g}"}])
    C._TID_CACHE.pop(tmp_path.name, None)
    assert C.identifier_for({"doc": tmp_path.name, "page": "029",
                             "region": {}, "before": r"\mathscr{g}"},
                            tmp_path.parent) == "d_FO0175"


def test_a_REPEATED_latex_is_dropped_rather_than_guessed(tmp_path):
    _doc(tmp_path, [], [{"title": "d_FO0001", "latex": "x"},
                        {"title": "d_FO0002", "latex": "x"}])
    C._TID_CACHE.pop(tmp_path.name, None)
    assert C.identifier_for({"doc": tmp_path.name, "page": "1",
                             "region": {}, "before": "x"},
                            tmp_path.parent) is None


# ---- 513: the fourth state, and the emission -------------------------------

def test_flagged_is_the_fourth_state(tmp_path):
    """"The ink disagrees and nobody acted on it" was invisible under the
    first rule, and 1510.06699 has 68 such rows."""
    tp = _doc(tmp_path, [], [{"title": "d_EQ0007", "latex": "x^2",
                              "page": "007", "confidence": 0.9}])
    f = rt.findings_rows(json.loads(tp.read_text()), "d", tmp_path,
                         ink={"d_EQ0007": {"code": "C|+40"}})
    assert [x["identifier"] for x in f["flagged"]] == ["d_EQ0007"]
    assert f["unresolved"] == [] and f["doubted"] == []


def test_agreement_and_flag_are_disjoint():
    assert not (rt.INK_AGREES & rt.INK_FLAGS)


def test_a_doubted_row_is_not_ALSO_flagged(tmp_path):
    """Low confidence with an agreeing ink is doubted-but-correct; the
    branches are exclusive so no row is reported twice."""
    tp = _doc(tmp_path, [], [{"title": "d_EQ0008", "latex": "x^2",
                              "page": "008", "confidence": 0.01}])
    f = rt.findings_rows(json.loads(tp.read_text()), "d", tmp_path,
                         ink={"d_EQ0008": {"code": "K|+0"}})
    assert len(f["doubted"]) == 1 and f["flagged"] == []


def test_the_emission_closes_the_document_on_BOTH_paths(tmp_path):
    r"""513 — \end{document} was left inside the `if not findings:` block and
    all 21 findings builds aborted with "no legal \end found", while still
    reporting a page count from what TeX managed before giving up."""
    tp = _doc(tmp_path, [], [{"title": "d_EQ0009", "latex": "x^2",
                              "page": "009", "confidence": 0.99}])
    out = tmp_path / "report.tex"
    rt.build_report(tp, out=out, findings=True, formulas="none")
    tex = out.read_text()
    assert tex.rstrip().endswith(r"\end{document}")
    assert tex.count(r"\end{document}") == 1


def test_a_document_with_nothing_says_so_in_one_page(tmp_path):
    tp = _doc(tmp_path, [], [{"title": "d_EQ0010", "latex": "x^2",
                              "page": "010", "confidence": 0.99}])
    out = tmp_path / "report.tex"
    rt.build_report(tp, out=out, findings=True, formulas="none",
                    ink={"d_EQ0010": {"code": "K|+0"}})
    tex = out.read_text()
    assert "Nothing to report" in tex
    assert "longtable" not in tex.split(r"\begin{document}")[1]


def test_findings_omits_the_row_sections_entirely(tmp_path):
    tp = _doc(tmp_path, [], [{"title": "d_EQ0011", "latex": "a & b",
                              "page": "011"}])
    out = tmp_path / "report.tex"
    rt.build_report(tp, out=out, findings=True, formulas="none")
    tex = out.read_text()
    assert "Display equations" not in tex and "Inline formulas" not in tex
    assert "Unresolved (1)" in tex
