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
