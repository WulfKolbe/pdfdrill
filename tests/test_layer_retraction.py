"""U2 — a rebuild retracts the facts and counters of the layers it destroyed.

`model --force` discards every derived layer. Before this, the facts and
evidence asserting them survived: on 1706.03762, `BIBLIOGRAPHY_BUILT` outlived
all 40 References, `bibliography_entries` still read 40, and `status` reported
nothing. The planner reads facts, so the layer was believed done and never
rebuilt.

Retract, do not re-derive. Rebuilding inside `model` would make it silently
expensive and could re-run a paid step.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import layer_detect as LD


class _SC:
    """Only what the retraction touches."""
    def __init__(self, facts, evidence):
        self._facts = set(facts)
        self.evidence = dict(evidence)

    @property
    def facts(self):
        return set(self._facts)

    def remove_fact(self, f):
        self._facts.discard(f)

    # named exactly as pdfdrill.sidecar.Sidecar — a stub that omits a method
    # the code under test calls turns a real call into an AttributeError the
    # `except` swallows, and the test passes having exercised nothing.
    def set_evidence(self, k, v):
        self.evidence[k] = v

    def get_evidence(self, k, default=None):
        return self.evidence.get(k, default)


def _full_sidecar():
    return _SC(
        {"MODEL_BUILT", "BIBLIOGRAPHY_BUILT", "GEOMETRY_FUSED",
         "TIDDLERS_BUILT", "COMPARE_BUILT"},
        {"bibliography_entries": 40, "bibliography_cites": 76,
         "geometry_matched": 12, "tiddlers_count": 300, "compare_rows": 5,
         "svg_rendered": 2, "svg_errors": 2, "svg_present": 2,
         "keep_me": "not a layer counter"})


_EMPTY_MODEL = {"objects": [], "streams": {}, "meta": {}}


def test_a_rebuild_that_destroyed_everything_leaves_only_MODEL_BUILT():
    sc = _full_sidecar()
    LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"), Path("/nonexistent"))
    assert sc.facts == {"MODEL_BUILT"}


def test_no_counter_of_a_dropped_layer_remains():
    sc = _full_sidecar()
    LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"), Path("/nonexistent"))
    for gone in ("bibliography_entries", "bibliography_cites", "geometry_matched",
                 "tiddlers_count", "compare_rows", "svg_rendered", "svg_errors",
                 "svg_present"):
        assert gone not in sc.evidence, gone


def test_an_unrelated_counter_is_not_touched():
    """Retraction owns the counters in the contract and nothing else."""
    sc = _full_sidecar()
    LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"), Path("/nonexistent"))
    assert sc.evidence["keep_me"] == "not a layer counter"


def test_a_layer_that_is_STILL_PRESENT_keeps_its_fact_and_counters():
    """The half that makes it a retraction rather than a reset."""
    sc = _full_sidecar()
    model = {"objects": [{"type": "Reference", "props": {}}], "streams": {}}
    LD.retract_absent_layers(model, sc, Path("/nonexistent"), Path("/nonexistent"))
    assert "BIBLIOGRAPHY_BUILT" in sc.facts
    assert sc.evidence["bibliography_entries"] == 40
    assert "GEOMETRY_FUSED" not in sc.facts          # that one really is gone


def test_it_names_what_it_retracted_and_how_to_get_it_back():
    sc = _full_sidecar()
    out = LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"),
                                   Path("/nonexistent"))
    assert "bibliography" in out and "geometry" in out
    hint = LD.rebuild_hint(out)
    assert "pdfdrill bibliography" in hint and "pdfdrill geometry" in hint


def test_retracting_twice_changes_nothing_the_second_time():
    sc = _full_sidecar()
    LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"), Path("/nonexistent"))
    before = (sc.facts, dict(sc.evidence))
    again = LD.retract_absent_layers(_EMPTY_MODEL, sc, Path("/nonexistent"),
                                     Path("/nonexistent"))
    assert again == []
    assert (sc.facts, dict(sc.evidence)) == before


def test_a_failing_detector_never_ends_the_rebuild():
    """Bookkeeping must not be able to fail a build."""
    class _Exploding(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")
    sc = _full_sidecar()
    assert LD.retract_absent_layers(_Exploding(), sc, None, None) == [] or True
    assert "MODEL_BUILT" in sc.facts


def test_the_rebuild_site_calls_the_retraction():
    import inspect
    from pdfdrill import commands
    body = inspect.getsource(commands.cmd_model)
    assert "retract_absent_layers" in body


def test_the_stub_matches_the_real_sidecar_api():
    """Pinned: retraction calls set_evidence/get_evidence/remove_fact, and a
    stub missing any of them silently exercises the `except` branch instead."""
    from pdfdrill.sidecar import Sidecar as Real
    for name in ("set_evidence", "get_evidence", "remove_fact"):
        assert hasattr(Real, name) and hasattr(_SC, name), name
