"""
A3 (2606.28429v1): witnesses flow THROUGH aggregation, not attached after.
Quantity records carry their witness (source node); measurement binding unions
the witnesses in the product space (value × witness_set, ⊞ = (op, ∪)) via the
named WitnessUnion accumulator; the verifier passes the witness component
through — its output tuple carries the contributing spans WITHOUT any lookup.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import quantities as Q
from semantic import measurements as M
from semantic import verify as V


def test_quantity_records_carry_their_witness():
    class Obj:
        def __init__(self, id, type, props):
            self.id, self.type, self.props = id, type, props
    class Doc:
        objects = {"f1": Obj("f1", "Formula", {"latex": r"82\%", "flow_index": 1})}
    recs = Q.quantity_records(Doc())
    assert recs[0]["witness"] == ["f1"]         # the source node, structurally


def test_measurement_unions_witnesses_in_the_product_space():
    """PARA_0048 shape: the measurement's witness is the ∪ of the paragraph +
    every bound FO node (measured AND condition) — three entries."""
    def _o(id, t, **props):
        return types.SimpleNamespace(id=id, type=t, props=props)
    fo1 = _o("q1", "Formula", latex=r"5,550,689", flow_index=1,
             quant=[{"kind": "number", "value": 5550689, "unit": None,
                     "dimension": None, "raw": "x", "witness": ["q1"]}])
    fo2 = _o("q2", "Formula", latex=r"82\%", flow_index=2,
             quant=[{"kind": "ratio", "value": 82, "unit": "%",
                     "dimension": "ratio", "raw": "82%", "witness": ["q2"]}])
    sec = _o("s1", "Section", caption="KBC", flow_index=0)
    para = _o("p1", "Paragraph", flow_index=3, parent_section="s1",
              text=("we could add {{X_FO0001||FO}} new facts with an accuracy "
                    "of {{X_FO0002||FO}} automatically."))
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in (fo1, fo2, sec, para)}
    d.meta = {"bibkey": "X"}
    recs = M.measurement_records(d)
    assert len(recs) == 1
    assert sorted(recs[0]["witness"]) == ["p1", "q1", "q2"]


def test_verifier_output_carries_witnesses_without_lookup():
    """The acceptance: verify a derivation whose record carries three witness
    nodes — the output tuple has them, and the verifier touches NO doc/graph."""
    qrec = {"kind": "derivation", "value": 6769133, "unit": None,
            "dimension": None, "raw": "d", "witness": ["p1", "q1", "q2"],
            "payload": {"lhs_terms": [7871085, 0.86], "op": "mul",
                        "rhs": 6769133}}
    out = V.verify_derivation(qrec)
    assert out["ok"] is True
    assert sorted(out["witness"]) == ["p1", "q1", "q2"]   # no lookup step
    # a witness-less record still verifies, with an empty witness component
    out2 = V.verify_derivation({k: v for k, v in qrec.items() if k != "witness"})
    assert out2["ok"] is True and out2["witness"] == []


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
