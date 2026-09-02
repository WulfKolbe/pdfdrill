"""511 — a refinement whose two records disagree is a contradiction, not an absence."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import refine as rf


class R:
    def __init__(self, provenance, props):
        self.provenance, self.props = provenance, props


class O:
    def __init__(self, props, realizations=()):
        self.props, self.realizations = props, list(realizations)


def _verified(v="B"):
    return O({"latex": "A", rf.REFINED_FIELD: v},
             [R("change", {rf.REFINED_FIELD: v, "verified_by": "ink",
                           "basis": "measured", "author": "t"})])


def test_no_twin_prop_is_none():
    assert rf.refinement_state(O({"latex": "A"}))["state"] == rf.NONE
    assert rf.chosen_latex(O({"latex": "A"})) == ("A", {})


def test_agreeing_records_are_verified():
    st = rf.refinement_state(_verified())
    assert st["state"] == rf.VERIFIED and st["realization"] is not None
    assert rf.chosen_latex(_verified())[0] == "B"


def test_DISAGREEING_records_are_a_contradiction_not_an_absence():
    """502 changed the twin prop and not the realization. For a day the
    correction was silently un-accepted and the row would have projected
    \\mathscr{g}, which renders nothing because rsfs10 has no lowercase."""
    o = O({"latex": "A", rf.REFINED_FIELD: "NEW"},
          [R("change", {rf.REFINED_FIELD: "OLD", "verified_by": "source"})])
    st = rf.refinement_state(o)
    assert st["state"] == rf.CONTRADICTED
    assert st["prop"] == "NEW" and st["realization_value"] == "OLD"
    assert "NEW" in st["why"] and "OLD" in st["why"]


def test_a_change_realization_without_verified_by_is_unverified():
    o = O({"latex": "A", rf.REFINED_FIELD: "B"},
          [R("change", {rf.REFINED_FIELD: "B"})])
    assert rf.refinement_state(o)["state"] == rf.UNVERIFIED


def test_a_twin_prop_with_no_change_realization_is_orphaned():
    o = O({"latex": "A", rf.REFINED_FIELD: "B"}, [])
    st = rf.refinement_state(o)
    assert st["state"] == rf.ORPHANED and st["prop"] == "B"


def test_the_four_non_verified_states_are_DISTINGUISHABLE():
    """The whole point: they used to be one value, None."""
    states = {
        rf.refinement_state(O({"latex": "A"}))["state"],
        rf.refinement_state(O({"latex": "A", rf.REFINED_FIELD: "B"}, []))["state"],
        rf.refinement_state(O({"latex": "A", rf.REFINED_FIELD: "B"},
                              [R("change", {rf.REFINED_FIELD: "B"})]))["state"],
        rf.refinement_state(O({"latex": "A", rf.REFINED_FIELD: "N"},
                              [R("change", {rf.REFINED_FIELD: "O",
                                            "verified_by": "x"})]))["state"],
    }
    assert states == {rf.NONE, rf.ORPHANED, rf.UNVERIFIED, rf.CONTRADICTED}


def test_verified_change_still_returns_a_realization_or_None():
    """Its callers decide what to PROJECT and that contract is unchanged."""
    assert rf.verified_change(_verified()) is not None
    for o in (O({"latex": "A"}),
              O({"latex": "A", rf.REFINED_FIELD: "B"}, []),
              O({"latex": "A", rf.REFINED_FIELD: "N"},
                [R("change", {rf.REFINED_FIELD: "O", "verified_by": "x"})])):
        assert rf.verified_change(o) is None


def test_a_contradiction_projects_the_ORIGINAL_and_says_so():
    """A contradiction is not a licence to guess which record is right — but
    the row must not read as a clean unrefined one either."""
    o = O({"latex": "A", rf.REFINED_FIELD: "NEW"},
          [R("change", {rf.REFINED_FIELD: "OLD", "verified_by": "source"})])
    val, ev = rf.chosen_latex(o)
    assert val == "A"
    assert ev["refinement_state"] == rf.CONTRADICTED and ev["why"]


def test_a_clean_row_still_carries_no_evidence_dict():
    assert rf.chosen_latex(O({"latex": "A"}))[1] == {}
