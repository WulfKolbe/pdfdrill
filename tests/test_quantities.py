"""
semantic/quantities.py — SO.QUANT.EXTRACT (L6 quantity sublayer, S1.2).
Fixture LaTeX strings below are VERBATIM from 2303.11082's llm.txt (FO bodies):
FO0043 `5,550,689`, FO0044 `7,871,085 \\cdot 0.86=6,769,133`, FO0045 `82\\%`,
FO0046 `\\sim90\\%`, FO0007 `100,000`, `k=10`, `R@P90`, `\\$2`, `max.`+`2000`.
Negatives that must NOT be typed: `\\cdot`, `(s,r,o)`, `FT_{vocab}`,
`BERT_{large}`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import quantities as Q
from semantic import registry as R


def _one(latex):
    recs = Q.parse_latex_quantities(latex)
    assert len(recs) == 1, f"{latex!r}: expected 1 record, got {recs}"
    return recs[0]


def test_comma_group_number():
    r = _one(r"5,550,689")
    assert r["kind"] == "number" and r["value"] == 5550689
    assert r["raw"] == r"5,550,689"


def test_percent_ratio():
    r = _one(r"82\%")
    assert r["kind"] == "ratio" and r["value"] == 82
    assert r["unit"] == "%" and r["dimension"] == "ratio"
    assert not r.get("approx")


def test_sim_percent_is_approx():
    r = _one(r"\sim90\%")
    assert r["kind"] == "ratio" and r["value"] == 90 and r.get("approx") is True


def test_money():
    r = _one(r"\$2")
    assert r["kind"] == "money" and r["value"] == 2
    assert r["unit"] == "$" and r["dimension"] == "currency"


def test_assignment_k_equals_10():
    r = _one(r"k=10")
    assert r["kind"] == "number" and r["value"] == 10
    assert r.get("var") == "k"


def test_max_qualifier():
    r = _one(r"max. 2000")
    assert r["kind"] == "number" and r["value"] == 2000
    assert r.get("qualifier") == "max"


def test_named_metric_r_at_p90():
    r = _one(r"R@P90")
    assert r["kind"] == "named_metric"
    assert r["name"] == "R@P" and r["param"] == 90


def test_derivation():
    r = _one(r"7,871,085 \cdot 0.86=6,769,133")
    assert r["kind"] == "derivation"
    p = r["payload"]
    assert p["lhs_terms"] == [7871085, 0.86]
    assert p["op"] == "mul"
    assert p["rhs"] == 6769133


def test_sim_bare_number_is_approx():
    r = _one(r"\sim1000")
    assert r["kind"] == "number" and r["value"] == 1000 and r.get("approx") is True


def test_negatives_not_typed():
    for latex in [r"\cdot", r"(s,r,o)", r"FT_{vocab}", r"BERT_{large}",
                  r"[t_1,..,t_n]", r"\sim"]:
        assert Q.parse_latex_quantities(latex) == [], f"{latex!r} must yield []"


def test_prose_count_noun():
    recs = Q.parse_text_quantities("we could add 5,550,689 new facts to Wikidata")
    counts = [r for r in recs if r["kind"] == "count"]
    assert len(counts) == 1
    assert counts[0]["value"] == 5550689 and counts[0]["noun"] == "facts"


def test_prose_money_with_approx():
    recs = Q.parse_text_quantities("costs drop from approximately $2 to $0.4")
    money = [r for r in recs if r["kind"] == "money"]
    assert len(money) == 2
    assert money[0]["value"] == 2 and money[0].get("approx") is True
    assert money[1]["value"] == 0.4


def test_quantity_records_over_doc():
    """quantity_records walks Formula/Equation latex + prose, tagging obj_id."""
    class Obj:
        def __init__(self, id, type, props):
            self.id, self.type, self.props = id, type, props
    class Doc:
        objects = {
            "f1": Obj("f1", "Formula", {"latex": r"82\%", "flow_index": 1}),
            "f2": Obj("f2", "Formula", {"latex": r"FT_{vocab}", "flow_index": 2}),
            "e1": Obj("e1", "Equation", {"latex": r"7,871,085 \cdot 0.86=6,769,133",
                                         "flow_index": 3}),
            "p1": Obj("p1", "Paragraph", {"text": "we extracted 100,000 pairs",
                                          "flow_index": 4}),
        }
    recs = Q.quantity_records(Doc())
    by_obj = {}
    for r in recs:
        by_obj.setdefault(r["obj_id"], []).append(r)
    assert by_obj["f1"][0]["kind"] == "ratio"
    assert "f2" not in by_obj                       # negative stays untyped
    assert by_obj["e1"][0]["kind"] == "derivation"
    assert by_obj["p1"][0]["kind"] == "count" and by_obj["p1"][0]["noun"] == "pairs"


def test_registered_in_fn_registry():
    entry = R.get_fn("SO.QUANT.EXTRACT")
    assert entry is not None and entry.spec.version == "1"
    assert entry.impl is Q.quantity_records


def test_sympy_tree_path_wins_over_lexer():
    """S1.4: when an object carries props['math'] (the mathir srepr), the SymPy
    tree extraction is preferred; a missing/failed tree falls back to the lexer.
    Skips silently when the [math] extra (sympy) is absent."""
    try:
        import sympy  # noqa: F401
    except Exception:
        print("  (skip: sympy not installed)"); return

    class Obj:
        def __init__(self, id, type, props):
            self.id, self.type, self.props = id, type, props
    class Doc:
        objects = {
            # srepr says 7 (a fake tree) while the latex says 82\% — tree wins
            "f1": Obj("f1", "Formula", {"latex": r"82\%", "flow_index": 1,
                                        "math": {"srepr": "Integer(7)"}}),
            # a derivation via the tree: 2*3 = 6
            "f2": Obj("f2", "Formula", {
                "latex": r"2 \cdot 3=6", "flow_index": 2,
                "math": {"srepr": "Eq(Mul(Integer(2), Integer(3), evaluate=False),"
                                  " Integer(6), evaluate=False)"}}),
            # an unusable srepr → lexer fallback still types the ratio
            "f3": Obj("f3", "Formula", {"latex": r"82\%", "flow_index": 3,
                                        "math": {"srepr": "not-a-srepr(("}}),
        }
    recs = {r["obj_id"]: r for r in Q.quantity_records(Doc())}
    assert recs["f1"]["kind"] == "number" and recs["f1"]["value"] == 7
    assert recs["f1"].get("source") == "sympy"
    assert recs["f2"]["kind"] == "derivation"
    assert recs["f2"]["payload"]["lhs_terms"] == [2, 3]
    assert recs["f2"]["payload"]["op"] == "mul" and recs["f2"]["payload"]["rhs"] == 6
    assert recs["f3"]["kind"] == "ratio" and recs["f3"].get("source") != "sympy"


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
