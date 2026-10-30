r"""A model is reused whatever code built it, and nobody is told.

Found on 2026-10-30 by running the owner's own command after a merge:
`pdfdrill md math/9807032` reused the model a nine-hour-old commit had built
(49 vs 52 Paragraph, before the macro-expansion fix) and projected it with the
NEW code, giving 8,221 words — neither the old output nor the new. Three
separate holes, all in this file's subject:

1. `_stale_or_absent` decides staleness from the INPUTS alone — a content-hash
   proof of the recorded inputs, else lines.json's mtime. Its own docstring is
   explicit that an untouched input means no rebuild. Which code wrote the model
   is never consulted.

2. The producing commit IS in the file and IS correct — the stale model said
   `meta["written"] = {sha: e83e600f…}` while the running code was db5eac9c —
   but `buildstamp.read_stamp` defaults to `which="build"`, and only
   `docmodel.main.run` writes that key. Everything saved through
   `model_io.save_model`, which is the whole LaTeX-source route, carries
   `written` and no `build`, so it reports as unstamped and `cmd_model` prints
   "(no build stamp: this model predates 575)" for a model built minutes ago.

3. `md` and `llmtext` never call `_stale_or_absent` at all: they check that the
   file exists. So fixing the staleness rule alone would not have caught this.

The owner's decision (2026-10-30): rebuild that document lazily — on demand,
only the document being run, only when the model-BUILDING code changed, free,
from the files already on disk, printing which builder it came from and which
it is now. Hence `builder_key`: a hash of the model-building sources, NOT the
repo sha, so an unrelated commit does not invalidate every model in the corpus.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import buildstamp                              # noqa: E402


# ── the builder's own identity, not the repo's ──────────────────────────────

def test_the_builder_key_is_stable_within_a_process():
    assert buildstamp.builder_key() == buildstamp.builder_key()


def test_the_builder_key_is_not_the_repo_sha():
    """Keyed to the model-building sources so an unrelated commit — a doc fix,
    a CLI string — does not mark every model in the library stale."""
    key = buildstamp.builder_key()
    assert key and key != (buildstamp.stamp().get("sha") or "")


def test_the_builder_key_changes_when_a_building_source_changes(tmp_path,
                                                               monkeypatch):
    a = tmp_path / "one.py"
    a.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(buildstamp, "_BUILDER_SOURCES", (a,))
    monkeypatch.setattr(buildstamp, "_BUILDER_CACHE", None)
    first = buildstamp.builder_key()
    a.write_text("x = 2\n", encoding="utf-8")
    monkeypatch.setattr(buildstamp, "_BUILDER_CACHE", None)
    assert buildstamp.builder_key() != first


def test_a_stamp_carries_the_builder_key():
    assert buildstamp.stamp().get("builder") == buildstamp.builder_key()


# ── the stamp is read under the key it was written with ────────────────────

def _model(tmp_path, meta: dict) -> Path:
    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps({"meta": meta, "objects": {}}), encoding="utf-8")
    return p


def test_read_stamp_finds_a_written_only_stamp(tmp_path):
    """The whole LaTeX-source route saves through `model_io.save_model`, which
    writes `written` and never `build`. Asking for `build` alone reported every
    one of those models as unstamped."""
    p = _model(tmp_path, {"written": {"sha": "abc1234", "dirty": False}})
    st = buildstamp.read_stamp(p)
    assert st and st.get("sha") == "abc1234"


def test_read_stamp_prefers_the_build_stamp_when_both_are_there():
    """`build` is the code that decided the object graph; `written` is the code
    that last touched the file. When both are known the builder is the answer."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _model(Path(d), {"build": {"sha": "bbb0000"},
                             "written": {"sha": "www0000"}})
        assert buildstamp.read_stamp(p).get("sha") == "bbb0000"


def test_read_stamp_still_honours_an_explicit_key(tmp_path):
    p = _model(tmp_path, {"build": {"sha": "bbb0000"},
                          "written": {"sha": "www0000"}})
    assert buildstamp.read_stamp(p, "written").get("sha") == "www0000"


def test_an_unstamped_model_is_still_none(tmp_path):
    assert buildstamp.read_stamp(_model(tmp_path, {"bibkey": "x"})) is None


# ── key_of can tell the generations apart ──────────────────────────────────

def test_key_of_separates_two_models_stamped_under_different_keys(tmp_path):
    """Before the fallback both answered "unstamped", so `spread`/`guard_lines`
    — the one place a stamp had teeth — could not tell two generations apart
    either. The guard was as blind as the rebuild."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    old = buildstamp.read_stamp(_model(tmp_path / "a", {"written": {"sha": "aaa"}}))
    new = buildstamp.read_stamp(_model(tmp_path / "b", {"written": {"sha": "bbb"}}))
    assert buildstamp.key_of(old) != buildstamp.key_of(new)
    assert "unstamped" not in (buildstamp.key_of(old), buildstamp.key_of(new))


# ── the comparison the rebuild hangs on ────────────────────────────────────

def test_a_model_built_by_the_running_builder_is_current(tmp_path):
    p = _model(tmp_path, {"written": dict(buildstamp.stamp())})
    assert buildstamp.builder_is_current(p) is True


def test_a_model_built_by_another_builder_is_not_current(tmp_path):
    st = dict(buildstamp.stamp())
    st["builder"] = "0" * 12
    p = _model(tmp_path, {"written": st})
    assert buildstamp.builder_is_current(p) is False


def test_a_model_with_no_builder_key_at_all_is_not_current(tmp_path):
    """Every model on disk today predates this field. They are not current —
    the owner's choice is to rebuild them lazily, one document at a time."""
    p = _model(tmp_path, {"written": {"sha": "abc1234", "dirty": False}})
    assert buildstamp.builder_is_current(p) is False


def test_a_missing_model_is_not_current(tmp_path):
    assert buildstamp.builder_is_current(tmp_path / "nope.json") is False


def test_the_rebuild_line_names_both_builders(tmp_path):
    st = dict(buildstamp.stamp())
    st["builder"] = "0123456789ab"
    p = _model(tmp_path, {"written": st})
    line = buildstamp.builder_change_note(p)
    assert "0123456" in line
    assert buildstamp.builder_key()[:7] in line


def test_there_is_no_note_when_the_builder_matches(tmp_path):
    p = _model(tmp_path, {"written": dict(buildstamp.stamp())})
    assert buildstamp.builder_change_note(p) == ""
