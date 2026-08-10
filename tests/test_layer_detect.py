"""U1 — one detector per derived layer, tested against BOTH states of a real model.

`model --force` discards every derived layer while the facts asserting them
survive. A detector that cannot tell the two states apart is not a detector, so
each is tested against the SAME document before and after a real rebuild:
arXiv 1706.03762, built and force-rebuilt on this machine.

  before: refs 40 | svg 2 | expanded 77 | pdf_lines yes | regions 65
  after : refs  0 | svg 0 | expanded  0 | pdf_lines no  | regions 65

The regions row is why `has_geometry` does not look at regions: they SURVIVE
the rebuild, because the merged born-digital build sets them itself.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import layer_detect as LD

_FIX = Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/7baec1d2-e80a-4a6c-adcf-bc7e26fc094e/scratchpad")
_BEFORE, _AFTER = _FIX / "model_BEFORE.json", _FIX / "model_AFTER.json"
_have_fixtures = _BEFORE.exists() and _AFTER.exists()
needs_fixtures = pytest.mark.skipif(
    not _have_fixtures, reason="1706.03762 before/after models not on this machine")


def _load(p):
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------- model layers
@needs_fixtures
@pytest.mark.parametrize("layer", ["bibliography", "geometry", "svg", "expandmath"])
def test_each_model_detector_is_true_before_and_false_after(layer):
    assert LD.present(layer, _load(_BEFORE)) is True, f"{layer}: not detected when present"
    assert LD.present(layer, _load(_AFTER)) is False, f"{layer}: still detected when gone"


@needs_fixtures
def test_geometry_is_not_detected_from_regions_which_survive():
    """The measurement that shaped the detector: 65 regions on both sides."""
    after = _load(_AFTER)
    with_region = sum(1 for o in after["objects"] if (o.get("props") or {}).get("region"))
    assert with_region == 65
    assert LD.present("geometry", after) is False


# --------------------------------------------------------------- projections
def _model_and_artifact(tmp_path, artifact_age):
    """artifact_age: 'newer' | 'older' | 'absent' relative to the model."""
    blob = tmp_path / "blob"
    blob.mkdir()
    model = blob / "model.docmodel.json"
    model.write_text("{}")
    os.utime(model, (1_000_000, 1_000_000))
    if artifact_age != "absent":
        for name in ("x.tiddlers.json", "compare.html"):
            a = blob / name
            a.write_text("x")
            t = 1_000_100 if artifact_age == "newer" else 999_900
            os.utime(a, (t, t))
    return blob, model


@pytest.mark.parametrize("layer", ["tiddlers", "compare"])
def test_a_projection_newer_than_the_model_is_present(tmp_path, layer):
    blob, model = _model_and_artifact(tmp_path, "newer")
    assert LD.present(layer, {}, blob, model) is True


@pytest.mark.parametrize("layer", ["tiddlers", "compare"])
def test_a_projection_OLDER_than_the_model_is_stale(tmp_path, layer):
    """The fixture that actually tests the freshness rule — an absent artifact
    satisfies the detector for the wrong reason and leaves this unexercised."""
    blob, model = _model_and_artifact(tmp_path, "older")
    assert LD.present(layer, {}, blob, model) is False


@pytest.mark.parametrize("layer", ["tiddlers", "compare"])
def test_an_absent_projection_is_not_present(tmp_path, layer):
    blob, model = _model_and_artifact(tmp_path, "absent")
    assert LD.present(layer, {}, blob, model) is False


def test_the_oldest_sibling_decides_not_the_newest(tmp_path):
    """A freshly rebuilt main array must not mask a stale `*.spoken.*` one."""
    blob, model = _model_and_artifact(tmp_path, "newer")
    stale = blob / "x.spoken.tiddlers.json"
    stale.write_text("x")
    os.utime(stale, (999_900, 999_900))
    assert LD.present("tiddlers", {}, blob, model) is False


# ------------------------------------------------------------------ contract
def test_quant_has_no_detector_and_that_is_deliberate():
    """`cmd_quantities` is a pure report: no artifact, no fact, no state."""
    assert "quant" not in LD.LAYERS
    with pytest.raises(KeyError):
        LD.present("quant", {})


def test_every_layer_in_the_contract_has_a_working_detector():
    for layer in LD.LAYERS:
        LD.present(layer, {}, Path("/nonexistent"), Path("/nonexistent"))


def test_svg_and_expandmath_declare_no_fact():
    assert LD.LAYERS["svg"]["fact"] is None
    assert LD.LAYERS["expandmath"]["fact"] is None
    assert LD.LAYERS["expandmath"]["evidence"] == ()


def test_the_coverage_gap_is_written_down_beside_the_decision():
    """Nine layers are uncovered and one is excluded by decision. Without the
    distinction recorded, the next reader sees a ten-item gap where there are
    nine — and may 'fix' the one that is deliberate."""
    doc = LD.__doc__ or ""
    assert "EXCLUDED BY DECISION" in doc and "quant" in doc
    for layer in ("annotate", "eqnums", "lists", "algorithms", "semantic",
                  "elements", "scikgtex", "stex", "lean"):
        assert layer in doc, layer
    assert set(LD.LAYERS) == {"bibliography", "geometry", "tiddlers", "compare",
                              "svg", "expandmath"}
