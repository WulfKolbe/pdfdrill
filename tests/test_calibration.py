"""
semantic/calibration.py — CAL.PRECISION.WILSON + CAL.GATE (S6.3): per-producer
correct/total tallies from chatlog verdict feedback, Wilson lower bound as the
calibrated precision estimate, and the gate implemented AS a Readout (so it
inherits the monotone property tests). Synthetic tallies only — no LLM.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import calibration as C
from semantic import registry as R


def test_wilson_lower_bound_math():
    # exact 0 and small-sample humility
    assert C.wilson_lower(0, 0) is None                  # no data → no estimate
    assert C.wilson_lower(10, 10) < 1.0                  # never certain
    assert C.wilson_lower(10, 10) > 0.7
    assert C.wilson_lower(1, 10) < 0.3
    # more data at the same rate → tighter (higher) lower bound
    assert C.wilson_lower(95, 100) > C.wilson_lower(19, 20)


def test_record_and_tally_roundtrip():
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver
    g = SemanticGraph(); r = IdentityResolver(g)
    for ok in (True, True, True, False):
        C.record_verdict(g, r, "ask", ok)
    correct, total = C.tally(g, "ask")
    assert (correct, total) == (3, 4)
    est = C.precision_estimate(g, "ask")
    assert est is not None and 0.2 < est < 0.75          # Wilson-humble at n=4
    # an untallied producer has NO estimate — grounded absence
    assert C.precision_estimate(g, "claims_v1") is None
    # the record entity is a CONCEPT subtype question-record (no new EntityType)
    from semantic.entity import EntityType
    qrec = [e for e in g.entities.values()
            if e.type == EntityType.CONCEPT and e.subtype == "question-record"]
    assert len(qrec) == 1


def test_gate_is_a_readout_with_monotone_law():
    gate = C.CalGate(0.9)
    assert gate(0.95) is True and gate(0.5) is False
    entry = R.get_fn("CAL.GATE")
    assert entry is not None and "monotone" in entry.spec.laws
    assert R.get_fn("CAL.PRECISION.WILSON") is not None


def test_ask_precision_withholds_low_precision_producer():
    """ask --precision 0.9: a proposed part whose producer's calibrated
    estimate is LOW is withheld; a high-tally producer's part clears."""
    import tempfile, json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_ask import _make_model
    from pdfdrill.commands import cmd_ask
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver

    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        # seed the doc's semantic graph with a LOW ask tally (1/10 correct)
        g = SemanticGraph(); r = IdentityResolver(g)
        C.record_verdict(g, r, "ask", True)
        for _ in range(9):
            C.record_verdict(g, r, "ask", False)
        sem = pdf.parent / f"{pdf.stem}.drill" / f"{pdf.stem}.semantic.json"
        sem.parent.mkdir(parents=True, exist_ok=True)
        sem.write_text(json.dumps(g.to_dict()), encoding="utf-8")

        gated = cmd_ask(pdf, "how many facts could be added automatically?",
                        precision=0.9)
        assert "6769133" in gated                 # derived part still answers
        assert "withheld" in gated.lower()        # low-precision parts gone
        assert "baseline model" not in gated


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
