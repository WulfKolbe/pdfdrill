"""431 — `model --force` must refuse over enrichments, as `rename` already does."""
import json
from pathlib import Path

from pdfdrill.commands import (ENRICHMENT_MARKERS, model_enrichments,
                               model_rebuild_blocked_by_enrichment)


def _model(tmp_path, objects):
    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps({"meta": {}, "objects": objects}))
    return p


def test_a_clean_model_does_not_refuse(tmp_path):
    """The guard must not fire on the 1,291 models that carry nothing: a
    refusal everyone learns to pass with a flag is not a guard."""
    p = _model(tmp_path, [{"id": "a", "props": {"latex": "x"},
                           "realizations": [{"provenance": "surface"}]}])
    assert model_enrichments(p) == {}
    assert model_rebuild_blocked_by_enrichment(model_enrichments(p), False) == ""


def test_every_marker_is_counted(tmp_path):
    """All five props plus the change realization. 430 measured each going to
    ZERO on a rebuild, so each has to be able to stop one."""
    props = {k: "v" for k in ENRICHMENT_MARKERS}
    p = _model(tmp_path, [{"id": "a", "props": props,
                           "realizations": [{"provenance": "change"}]}])
    got = model_enrichments(p)
    for k in ENRICHMENT_MARKERS:
        assert got.get(k) == 1, k
    assert got.get("change realizations") == 1


def test_the_refusal_names_what_would_be_lost(tmp_path):
    r"""A refusal that does not say what it is protecting invites the override.

    It must also name the ID REGENERATION: that is the part that reaches
    outside the model, and a reader deciding whether to pass the flag cannot
    weigh it if only the props are listed.
    """
    p = _model(tmp_path, [{"id": "a", "props": {"latex_refined": "x"},
                           "realizations": [{"provenance": "change"}]}])
    msg = model_rebuild_blocked_by_enrichment(model_enrichments(p), False)
    assert "1 latex_refined" in msg
    assert "1 change realizations" in msg
    assert "OBJECT IDS" in msg
    assert "--force-discard-enrichments" in msg


def test_the_override_lets_it_through(tmp_path):
    p = _model(tmp_path, [{"id": "a", "props": {"latex_refined": "x"},
                           "realizations": []}])
    assert model_rebuild_blocked_by_enrichment(model_enrichments(p), True) == ""


def test_both_overrides_are_reachable_from_the_cli():
    """431 — `force_discard_translation` was a cmd_model parameter no CLI path
    could set, so the refusal it guards had no documented way past it. That is
    400's defect: a flag that exists only in a signature is a dead end, not an
    override.
    """
    import inspect
    from pdfdrill import cli
    src = inspect.getsource(cli._do_model)
    assert "--force-discard-translation" in src
    assert "--force-discard-enrichments" in src
