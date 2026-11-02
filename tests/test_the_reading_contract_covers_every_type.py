"""T-0107 gate — a new MathPix line type cannot vanish silently.

The contract (docs/contracts/reading-types.json, destination
~/drillgroup/contracts/) lists every line type the library's MathPix
readings contain, with the modules that read it. This test holds the code to
that list in both directions:

  * every type in the contract is either READ by a module or marked
    declared-only, never left without a status;
  * every type pdfdrill's own type_contract knows is covered by the contract
    -- by MathPix's list or by `pdfdrill_only_types`, the names our readers
    use and MathPix never emits -- so the two lists cannot drift apart;
  * a type that is in neither is REPORTED, not ignored -- the planted-type
    case, which is what makes this a gate rather than a description.

`reading_contract.unknown_types` is the function `pdfdrill lines-check`
(T-0109) will call on a real file; this test calls it on a planted name.
"""
import json
from pathlib import Path

import pytest

from docmodel import reading_contract as RC

CONTRACT = Path(__file__).resolve().parent.parent / "docs/contracts/reading-types.json"


class TestTheContractItself:
    def test_the_file_parses_and_names_its_contract(self):
        d = json.loads(CONTRACT.read_text(encoding="utf-8"))
        assert d["contract"] == "reading/1"
        assert d["producer"] == "mathpix"
        assert d["files"] > 1000 and d["lines"] > 1_000_000

    def test_it_was_measured_over_the_library_not_recalled(self):
        d = json.loads(CONTRACT.read_text(encoding="utf-8"))
        assert d["library"].endswith("pdfdrill-library")
        # MathPix is one producer in two API vintages (contract §4a); both
        # must be recorded, because they carry different fields.
        assert set(d["classes"]) == {"mathpix-classic", "mathpix-newer"}
        assert (d["classes"]["mathpix-classic"]["lines"]
                + d["classes"]["mathpix-newer"]["lines"] == d["lines"]), (
            "the two classes must account for every measured line")
        # And the four names the first draft credited to MathPix must NOT be
        # in its vocabulary: they came from 34 files of ours (§1a).
        names = {t["name"] for t in d["types"]}
        for bogus in ("caption", "equation", "formula", "rotated_text"):
            assert bogus not in names, (
                "%s is pdfdrill's own type; no MathPix file in the library "
                "carries it" % bogus)
        assert d["measured_at"].startswith("20")

    def test_every_type_has_a_status(self):
        for t in RC.load_contract()["types"]:
            assert t["status"] in ("read", "declared-only"), t
            if t["status"] == "read":
                assert t["readers"], t["name"]
            else:
                assert t["readers"] == [], t["name"]

    def test_every_type_carries_its_measurement(self):
        for t in RC.load_contract()["types"]:
            assert t["measured_lines"] >= 1, t["name"]
            assert t["measured_docs"] >= 1, t["name"]


class TestAPlantedTypeIsReported:
    """The gate. A name the contract has never seen must come back."""

    def test_an_unknown_type_is_returned(self):
        assert RC.unknown_types(["text", "math", "flurble_block"]) == ["flurble_block"]

    def test_a_contract_type_is_not_returned(self):
        assert RC.unknown_types(["text", "qed_symbol", "x_axis_tick_label"]) == []

    def test_the_order_is_the_order_seen_and_duplicates_collapse(self):
        assert RC.unknown_types(["zzz", "text", "aaa", "zzz"]) == ["zzz", "aaa"]

    def test_the_declared_only_types_count_as_known(self):
        """They are IN the contract, named as unread. Unknown means absent
        from the contract, not absent from the code -- conflating the two
        would make the gate fire on all seven of them forever."""
        names = [t["name"] for t in RC.load_contract()["types"]
                 if t["status"] == "declared-only"]
        assert names, "the contract must record the unread types"
        assert RC.unknown_types(names) == []


class TestTheTwoListsCannotDrift:
    def test_every_type_pdfdrill_declares_is_in_the_contract(self):
        tc = pytest.importorskip("docmodel.type_contract")
        declared = RC.declared_line_types(tc)
        if not declared:
            pytest.skip("type_contract exposes no line-type list to compare")
        missing = RC.unknown_types(sorted(declared))
        assert missing == [], (
            "pdfdrill declares line types the contract does not list: %s. "
            "Re-measure (tools/reading-contract/measure.py) and regenerate, "
            "or the two lists have drifted." % missing)

    def test_the_two_vocabularies_are_kept_apart(self):
        """MathPix's list and pdfdrill's own are DIFFERENT lists.

        The first version of this gate compared pdfdrill's 38 declared types
        against MathPix's and would have failed for ever on `rotated_text`,
        which our reader emits and MathPix does not. A gate that cannot be
        satisfied gets switched off, so the contract records the boundary and
        this test holds it: the two lists must not overlap, and the union
        must cover what pdfdrill declares.
        """
        mathpix = set(RC.type_names())
        ours = {t["name"] if isinstance(t, dict) else t
                for t in RC.pdfdrill_only_types()}
        assert ours, "the contract must name the types MathPix does not emit"
        assert not (mathpix & ours), (
            "a type cannot be both MathPix's and pdfdrill-only: %s"
            % sorted(mathpix & ours))

    def test_a_pdfdrill_only_type_is_known_not_unknown(self):
        """`rotated_text` is correct, declared, and absent from MathPix. It
        must not reach a human as an unknown type."""
        ours = [t["name"] if isinstance(t, dict) else t
                for t in RC.pdfdrill_only_types()]
        assert RC.unknown_types(ours) == []
