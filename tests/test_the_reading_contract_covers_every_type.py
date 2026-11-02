"""T-0107 gate — a new MathPix line type cannot vanish silently.

The contract (docs/contracts/reading-types.json, destination
~/drillgroup/contracts/) lists every line type the library's MathPix
readings contain, with the modules that read it. This test holds the code to
that list in both directions:

  * every type in the contract is either READ by a module or marked
    declared-only, never left without a status;
  * every type pdfdrill's own type_contract knows is in the contract, so the
    two lists cannot drift apart;
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
