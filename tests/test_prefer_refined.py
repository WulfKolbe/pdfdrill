"""233 — the consumer for latex_refined.

out/232 recorded a verified repair and then measured that it changed nothing:
every projector reads `latex`, and `latex` is never overwritten. The loop could
accept, verify and record corrections that nothing ever used. This is the
projector that uses them — and the model still does not change, because the
choice is made at read time.
"""
import pytest

from pdfdrill import refine as rf
from pdfdrill import report_tex as rt


class _R:
    def __init__(self, provenance, props):
        self.provenance, self.props = provenance, props
        self.stream, self.role = rf.REFINED_STREAM, "latex_candidate"


class _Obj:
    def __init__(self, props, reals=()):
        self.props, self.realizations = props, list(reals)


def _verified(orig=r"\mathscr{g}", new=r"\mathcal{J}", by="source"):
    return _Obj({"latex": orig, rf.REFINED_FIELD: new},
                [_R("change", {rf.REFINED_FIELD: new, "verified_by": by,
                               "basis": by, "author": "out/229"})])


# ------------------------------------------------------------- the chooser ---

def test_a_verified_refinement_is_chosen():
    val, ev = rf.chosen_latex(_verified())
    assert val == r"\mathcal{J}"
    assert ev["original"] == r"\mathscr{g}" and ev["basis"] == "source"


def test_the_prop_ALONE_is_not_enough():
    r"""A prop can be written by anything. out/232's point is that the recorded
    value is worth projecting only because something checked it — a refinement
    whose evidence has gone is not a refinement, it is an assertion."""
    o = _Obj({"latex": "a", rf.REFINED_FIELD: "b"})          # no realization
    assert rf.chosen_latex(o) == ("a", {})


def test_a_change_realization_with_no_verification_is_not_enough():
    o = _Obj({"latex": "a", rf.REFINED_FIELD: "b"},
             [_R("change", {rf.REFINED_FIELD: "b"})])        # no verified_by
    assert rf.chosen_latex(o) == ("a", {})


def test_evidence_for_a_DIFFERENT_value_does_not_license_this_one():
    """The realization must vouch for the value in the prop, not merely exist."""
    o = _Obj({"latex": "a", rf.REFINED_FIELD: "b"},
             [_R("change", {rf.REFINED_FIELD: "c", "verified_by": "ink"})])
    assert rf.chosen_latex(o) == ("a", {})


def test_an_ordinary_row_is_untouched():
    assert rf.chosen_latex(_Obj({"latex": "x"})) == ("x", {})


# ------------------------------------------------------------ the projector ---

TIDS = [
    {"title": "B_FO0175", "latex": r"\mathscr{g}",
     "latex_refined": r"\mathcal{J}", "refined_basis": "source",
     "refined_verified_by": "source", "refined_author": "out/229"},
    {"title": "B_EQ0001", "latex": "x=1"},
]


def test_refined_map_needs_the_verification_field():
    assert set(rt.refined_map(TIDS)) == {"B_FO0175"}
    assert rt.refined_map([{"title": "T", "latex": "a",
                            "latex_refined": "b"}]) == {}


def test_rows_project_the_refinement_only_when_asked():
    fo, _eq, _t, _d = rt.rows_for(TIDS, "B")
    assert fo[0][1] == r"\mathscr{g}"                 # default: the OCR reading
    fo, _eq, _t, _d = rt.rows_for(TIDS, "B", rt.refined_map(TIDS))
    assert fo[0][1] == r"\mathcal{J}"


def test_the_row_says_so_in_the_IDENTIFIER_column():
    r"""Beside \lowconf and for the same reason (out/064, HANDOVER rule 16):
    the Source, Rendered and Scan columns stay byte-identical, so a per-column
    ink probe still works and an unchanged column remains a free control."""
    marked = rt.row("B_FO0175", r"\mathcal{J}", "29",
                    refined={"basis": "source"})
    plain = rt.row("B_FO0175", r"\mathcal{J}", "29")
    assert "[refined: source]" in marked
    assert "[refined" not in plain
    # the difference is confined to the identifier cell
    assert marked.split("&", 1)[1] == plain.split("&", 1)[1]


def test_the_page_states_how_many_and_on_what_basis():
    note = rt.refined_note(rt.refined_map(TIDS))
    assert "1 row shows" in note
    assert "verified against the source" in note
    assert "B\\_FO0175" in note or "B_FO0175" in note
    assert "model is unchanged" in note


def test_no_note_when_nothing_was_refined():
    assert rt.refined_note({}) == ""
