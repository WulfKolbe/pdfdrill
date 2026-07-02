"""
semantic/registry.py — the function-spec registry (Stage 0 of the quantitative
semantic layer). Mirrors semantic/question.py's Question/REGISTRY shape: a frozen
spec dataclass + register/get/all + re-register-replaces semantics, plus an
`explain` dispatch that runs the registered impl and wraps the result with its
spec provenance.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import registry as R


def _toy_spec(version="1"):
    return R.FnSpec(
        fid="SIM.TOY.EQ",
        description="Toy equality metric: 1.0 iff a == b else 0.0.",
        version=version,
        params={"tolerance": 0},
        laws=("symmetric", "reflexive"),
    )


def test_register_and_lookup():
    spec = _toy_spec()
    R.register_fn(spec, lambda a, b: 1.0 if a == b else 0.0)
    got = R.get_fn("SIM.TOY.EQ")
    assert got is not None
    assert got.spec.fid == "SIM.TOY.EQ"
    assert got.spec.laws == ("symmetric", "reflexive")
    assert got.impl(3, 3) == 1.0 and got.impl(3, 4) == 0.0
    assert any(s.fid == "SIM.TOY.EQ" for s in R.all_fns())


def test_reregister_replaces_like_question_registry():
    R.register_fn(_toy_spec(version="1"), lambda a, b: 0.0)
    R.register_fn(_toy_spec(version="2"), lambda a, b: 1.0)   # replace
    got = R.get_fn("SIM.TOY.EQ")
    assert got.spec.version == "2"
    assert got.impl(1, 2) == 1.0                              # the NEW impl
    # exactly one entry per fid
    assert sum(1 for s in R.all_fns() if s.fid == "SIM.TOY.EQ") == 1


def test_explain_dispatch():
    R.register_fn(_toy_spec(version="3"), lambda a, b: 1.0 if a == b else 0.0)
    out = R.explain("SIM.TOY.EQ", 5, 5)
    assert out["fid"] == "SIM.TOY.EQ" and out["version"] == "3"
    assert out["result"] == 1.0
    assert out["args"] == (5, 5)
    # unknown fid → a clear error, not a KeyError deep inside
    try:
        R.explain("SIM.NO.SUCH")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "SIM.NO.SUCH" in str(e)


def test_spec_roundtrip_and_frozen():
    spec = _toy_spec()
    d = spec.to_dict()
    back = R.FnSpec.from_dict(d)
    assert back == spec
    try:
        spec.version = "9"
        assert False, "FnSpec must be frozen"
    except Exception:
        pass


def test_spaces_fields_and_laws_vocabulary():
    """A0 (2606.28429v1 amendment): FnSpec declares its semantic spaces
    (space_in/space_out, from the spaces.py vocabulary) and the laws vocabulary
    gains monotone / threshold-sound / componentwise. Legacy dicts (no spaces)
    load with empty strings."""
    spec = R.FnSpec(
        fid="SIM.TOY.SPACED", description="spaced toy", version="1",
        space_in="witness_set", space_out="count",
        laws=("monotone", "threshold-sound", "componentwise"))
    assert spec.space_in == "witness_set" and spec.space_out == "count"
    d = spec.to_dict()
    assert d["space_in"] == "witness_set" and d["space_out"] == "count"
    back = R.FnSpec.from_dict(d)
    assert back == spec
    legacy = {k: v for k, v in d.items() if k not in ("space_in", "space_out")}
    old = R.FnSpec.from_dict(legacy)
    assert old.space_in == "" and old.space_out == ""


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
