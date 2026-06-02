"""
Tests for bundle segmentation (pdfdrill.segment) — pure partition logic:
id-value grouping (type-agnostic), continuity ordering, duplicate flagging,
sender labelling, unidentified singletons.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import segment as seg


def test_segment_groups_orders_dedups_and_labels():
    # Doc "111": Steuernummer on p1 (seq 2) + Aktenzeichen SAME value on p2
    # (seq 1) must merge; p5 is a duplicate of seq 1. Doc "999": Stadt Köln p3.
    # p4 has no signature -> unidentified singleton.
    cont = {
        1: {"seq_in_doc": 2, "doc_total": 2},
        2: {"seq_in_doc": 1, "doc_total": 2},
        3: {"seq_in_doc": 1},
        4: {},
        5: {"seq_in_doc": 1, "doc_total": 2},
    }
    ent = {
        1: {"ids": [("STEUERNUMMER", "111")]},
        2: {"ids": [("AKTENZEICHEN", "111")]},
        3: {"ids": [("KASSENZEICHEN", "999")]},
        4: {"ids": []},
        5: {"ids": [("STEUERNUMMER", "111")]},
    }
    pt = {1: "Finanzamt Köln writes ...", 2: "...", 3: "Stadt Köln Mahnung",
          4: "loose page", 5: "copy"}
    docs = seg.segment(cont, ent, pt)

    by_id = {d["identifier"]: d for d in docs}
    assert "111" in by_id and "999" in by_id
    d111 = by_id["111"]
    assert d111["pages"] == [2, 1]            # ordered by continuity seq (1,2)
    assert d111["duplicates"] == [5]          # p5 = duplicate of seq 1
    assert d111["label"] == "Finanzamt Köln"  # labelled by sender
    assert d111["total"] == 2
    d999 = by_id["999"]
    assert d999["pages"] == [3] and d999["label"] == "Stadt Köln"
    assert any(d["label"] == "(unidentified)" and d["pages"] == [4] for d in docs)
    # Documents are returned in first-page order.
    assert [d["pages"][0] for d in docs] == sorted(d["pages"][0] for d in docs)


def test_sender_of():
    assert seg.sender_of("Bescheid vom Finanzamt Bergisch Gladbach, ...") == "Finanzamt Bergisch"
    assert seg.sender_of("Rechnung der Burkhardt Kundendienst GmbH") == "Burkhardt Kundendienst GmbH"
    assert seg.sender_of("no sender here") == ""


if __name__ == "__main__":
    test_segment_groups_orders_dedups_and_labels(); print("PASS partition")
    test_sender_of(); print("PASS sender_of")
    print("\nAll tests passed.")
