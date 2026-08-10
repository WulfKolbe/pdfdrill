"""U3 — status names the layers a rebuild dropped, and how to get each back.

Before U2, `model --force` discarded every derived layer and `status` said
nothing, because the facts asserting them survived. U2 retracts those facts —
which makes the loss invisible in the OTHER direction unless status reports it.
So the two halves have to land together.

The record is filtered by the live detector, so a layer leaves the list the
moment its command re-runs; nothing has to remember to clear it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import layer_detect as LD


class _SC:
    def __init__(self, facts=(), evidence=None):
        self._facts = set(facts)
        self.evidence = dict(evidence or {})

    @property
    def facts(self):
        return set(self._facts)

    def remove_fact(self, f):
        self._facts.discard(f)

    def set_evidence(self, k, v):
        self.evidence[k] = v

    def get_evidence(self, k, default=None):
        return self.evidence.get(k, default)


_EMPTY = {"objects": [], "streams": {}, "meta": {}}
_NOPATH = Path("/nonexistent")


def test_retraction_records_what_it_dropped():
    sc = _SC({"BIBLIOGRAPHY_BUILT", "GEOMETRY_FUSED"},
             {"bibliography_entries": 40, "geometry_matched": 3})
    LD.retract_absent_layers(_EMPTY, sc, _NOPATH, _NOPATH)
    assert set(sc.get_evidence("retracted_layers")) >= {"bibliography", "geometry"}


def test_status_lists_a_layer_that_is_still_missing():
    sc = _SC(evidence={"retracted_layers": ["bibliography", "geometry"]})
    assert LD.still_retracted(sc, _EMPTY, _NOPATH, _NOPATH) == ["bibliography", "geometry"]


def test_a_layer_drops_off_the_list_once_it_is_rebuilt():
    """The record is not cleared by anyone — the detector decides."""
    sc = _SC(evidence={"retracted_layers": ["bibliography", "geometry"]})
    back = {"objects": [{"type": "Reference", "props": {}}], "streams": {}}
    assert LD.still_retracted(sc, back, _NOPATH, _NOPATH) == ["geometry"]


def test_nothing_recorded_means_nothing_reported():
    assert LD.still_retracted(_SC(), _EMPTY, _NOPATH, _NOPATH) == []


def test_an_unknown_layer_name_in_the_record_is_ignored():
    """A record written by an older version must not raise KeyError."""
    sc = _SC(evidence={"retracted_layers": ["bibliography", "quant", "invented"]})
    assert LD.still_retracted(sc, _EMPTY, _NOPATH, _NOPATH) == ["bibliography"]


def test_the_hint_names_the_command_for_every_layer():
    hint = LD.rebuild_hint(["bibliography", "geometry", "tiddlers", "compare",
                            "svg", "expandmath"])
    for cmd in ("pdfdrill bibliography", "pdfdrill geometry", "pdfdrill tiddlers",
                "pdfdrill compare", "pdfdrill svg", "pdfdrill expandmath"):
        assert cmd in hint, cmd


def test_the_status_line_says_dropped_and_names_the_commands():
    from pdfdrill.commands import _retracted_status_lines
    import inspect
    src = inspect.getsource(_retracted_status_lines)
    assert "still_retracted" in src and "rebuild_hint" in src
    assert "dropped by the last model rebuild" in src


def test_cmd_status_calls_it():
    import inspect
    from pdfdrill import commands
    assert "_retracted_status_lines" in inspect.getsource(commands.cmd_status)
