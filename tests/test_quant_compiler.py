"""
S3.3: check_quantities wired into the compiler — VER.EQ.RECOMPUTE + PHY.BOUNDS
over QUANTITY entities, graded warnings in the existing style (a failed
recompute is critical), and the outcome attached as an Evidence row
(produced_by='arith', prop='verifies'|'refutes') on the Quantity entity.
"""
import sys
import types
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.entity import EntityType
from semantic import build, compiler


def _o(id, t, **props):
    ns = types.SimpleNamespace(id=id, type=t, props=props)
    ns.parent = None
    return ns


def _doc_with(quant):
    fo = _o("q1", "Formula", latex="x", flow_index=1, page=3, quant=[quant])
    d = types.SimpleNamespace()
    d.objects = {"q1": fo}
    d.meta = {"bibkey": "t", "title": "T"}
    return d


def _ingest(quant):
    g = SemanticGraph()
    r = IdentityResolver(g)
    doc = _doc_with(quant)
    build.ingest_docmodel(g, r, doc, "t",
                          quant_records=[{**quant, "obj_id": "q1"}])
    return g


def _qent(g):
    return next(e for e in g.entities.values() if e.type == EntityType.QUANTITY)


def test_good_derivation_verifies():
    g = _ingest({"kind": "derivation", "value": 6769133, "unit": None,
                 "dimension": None, "raw": "d",
                 "payload": {"lhs_terms": [7871085, 0.86], "op": "mul",
                             "rhs": 6769133}})
    warns = compiler.check_quantities(g)
    assert not [w for w in warns if w.severity == "critical"]
    q = _qent(g)
    ver = [e for e in q.evidence if e.produced_by == "arith"]
    assert ver and ver[0].prop == "verifies"


def test_refuted_derivation_is_critical_and_attaches_refutes():
    g = _ingest({"kind": "derivation", "value": 6769133, "unit": None,
                 "dimension": None, "raw": "d",
                 "payload": {"lhs_terms": [7871085, 0.68], "op": "mul",
                             "rhs": 6769133}})
    warns = compiler.check_quantities(g)
    crit = [w for w in warns if w.severity == "critical"]
    assert crit and crit[0].code == "quantity_refuted"
    q = _qent(g)
    ref = [e for e in q.evidence if e.produced_by == "arith"]
    assert ref and ref[0].prop == "refutes"
    # the whole compile() result includes the check + flips validity
    res = compiler.compile(g)
    assert res.validity == "invalid"
    assert any(w.code == "quantity_refuted" for w in res.warnings)


def test_bounds_violation_is_warning():
    g = _ingest({"kind": "ratio", "value": 130, "unit": "%",
                 "dimension": "ratio", "raw": "130%"})
    warns = compiler.check_quantities(g)
    assert any(w.code == "quantity_bounds" and w.severity == "warning"
               for w in warns)


def test_rerun_does_not_duplicate_arith_evidence():
    g = _ingest({"kind": "derivation", "value": 6, "unit": None,
                 "dimension": None, "raw": "d",
                 "payload": {"lhs_terms": [2, 3], "op": "mul", "rhs": 6}})
    compiler.check_quantities(g)
    compiler.check_quantities(g)
    q = _qent(g)
    assert sum(1 for e in q.evidence if e.produced_by == "arith") == 1


def test_zero_quantities_tolerated():
    g = SemanticGraph()
    assert compiler.check_quantities(g) == []


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
