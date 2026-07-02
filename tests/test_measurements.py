"""
semantic/measurements.py — SO.MEAS.BIND (S2.1): bind transcluded quantities to
the nearest concept + a measure verb, capturing co-occurring ratio conditions.
Fixture modeled on 2303.11082 PARA_0048: "…we could add {{…FO0043||FO}} new
facts … or {{…FO0044||FO}} with an accuracy of {{…FO0045||FO}} automatically."
(FO0043=5,550,689 / FO0044=the \\cdot derivation / FO0045=82%).
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import measurements as M
from semantic import registry as R


def _o(id, t, **props):
    return types.SimpleNamespace(id=id, type=t, props=props)


def _fixture_doc():
    """Three flow-ordered formulas (→ FO0001..FO0003 titles), one section, one
    paragraph whose sentence binds them exactly like PARA_0048."""
    fo1 = _o("q1", "Formula", latex=r"5,550,689", flow_index=1,
             quant=[{"kind": "count" if False else "number", "value": 5550689,
                     "unit": None, "dimension": None, "raw": "5,550,689"}])
    fo2 = _o("q2", "Formula", latex=r"7,871,085 \cdot 0.86=6,769,133", flow_index=2,
             quant=[{"kind": "derivation", "value": 6769133, "unit": None,
                     "dimension": None, "raw": r"7,871,085 \cdot 0.86=6,769,133",
                     "payload": {"lhs_terms": [7871085, 0.86], "op": "mul",
                                 "rhs": 6769133}}])
    fo3 = _o("q3", "Formula", latex=r"82\%", flow_index=3,
             quant=[{"kind": "ratio", "value": 82, "unit": "%",
                     "dimension": "ratio", "raw": r"82\%"}])
    sec = _o("s1", "Section", caption="Knowledge Base Completion Potential",
             flow_index=0)
    para = _o("p1", "Paragraph", flow_index=4, parent_section="s1",
              text=("Given the relation nativeLanguage we could add "
                    "{{2303.11082_FO0001||FO}} new facts in a human-in-a-loop "
                    "procedure or {{2303.11082_FO0002||FO}} with an accuracy of "
                    "{{2303.11082_FO0003||FO}} automatically."))
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in (fo1, fo2, fo3, sec, para)}
    d.meta = {"bibkey": "2303.11082"}
    return d


def test_two_measurements_with_conditions():
    doc = _fixture_doc()
    recs = M.measurement_records(doc)
    assert len(recs) == 2, f"expected 2 measurements, got {recs}"
    m1, m2 = recs
    # both carry the measure verb + the accuracy condition (82% → 0.82 canonical)
    for m in (m1, m2):
        assert m["measure"] == "could add"
        assert m["conditions"] == {"accuracy": 0.82}
        assert m["para_id"] == "p1"
        assert isinstance(m["sentence_span"], list) and len(m["sentence_span"]) == 2
        # concept: no concept token in the sentence → section-caption fallback
        assert m["concept"] == "Knowledge Base Completion Potential"
        assert m["concept_source"] == "section"
    assert m1["quantity_ref"]["obj_id"] == "q1"
    assert m2["quantity_ref"]["obj_id"] == "q2"
    # the condition ratio (q3) is a CONDITION, not its own measurement
    assert all(m["quantity_ref"]["obj_id"] != "q3" for m in recs)


def test_no_measure_verb_no_binding():
    doc = _fixture_doc()
    doc.objects["p1"].props["text"] = (
        "The value {{2303.11082_FO0001||FO}} appears in the table.")
    assert M.measurement_records(doc) == []


def test_registered_in_fn_registry():
    entry = R.get_fn("SO.MEAS.BIND")
    assert entry is not None and entry.spec.version == "1"
    assert entry.impl is M.measurement_records


def test_measurement_pass_stores_and_is_idempotent():
    from passes import PassContext, run_pipeline
    doc = _fixture_doc()
    ctx = PassContext(doc=doc)
    res = {r.name: r for r in run_pipeline(ctx, only={"quantity", "concepts",
                                                      "measurement"})}
    assert res["measurement"].status == "ran" and res["measurement"].changed
    meas = doc.objects["p1"].props["meas"]
    assert len(meas) == 2 and meas[0]["measure"] == "could add"
    res2 = {r.name: r for r in run_pipeline(ctx, only={"quantity", "concepts",
                                                       "measurement"})}
    assert res2["measurement"].changed is False


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
