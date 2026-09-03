"""576 — a cache hit must not claim a build.

160 found this and wrote it down (docs/handover/04-lessons.md); it stayed
unfixed and cost 575 a whole sweep. Both times the reasoning was the same: the
line said "Built unified model", the exit code was 0, and nothing in either
told the caller that the rebuild guard had declined.
"""
import json
from pathlib import Path

from pdfdrill import commands as C
from pdfdrill.sidecar import Sidecar


def _sidecar_with_a_model(tmp_path, stamp=None):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    mp = C._model_path(sc)
    mp.parent.mkdir(parents=True, exist_ok=True)
    meta = {"build": stamp} if stamp else {}
    # The model holds what the sidecar claims, so a test that changes only one
    # of them is testing the thing it means to.
    counts = {"Formula": 386, "Equation": 60, "Paragraph": 89, "Section": 5}
    objs, n = {}, 0
    for t, c in counts.items():
        for _ in range(c):
            objs[f"o{n}"] = {"type": t}
            n += 1
    mp.write_text(json.dumps({"meta": meta, "objects": objs}))
    sc.set_evidence("model_object_counts", counts)
    sc.set_evidence("model_equations_with_cdn", 60)
    sc.set_evidence("model_source", "mathpix")
    sc.set_evidence("bibkey", "2501.06662")
    sc.set_evidence("model_path", "model.docmodel.json")
    sc.save()
    return sc


def test_a_real_build_still_says_built(tmp_path):
    out = C._format_model(_sidecar_with_a_model(tmp_path))
    assert out.startswith("Built unified model: 540 objects")
    assert "NOTHING WAS REBUILT" not in out


def test_a_cache_hit_says_already_current_and_names_the_sha(tmp_path):
    st = {"sha": "634408f704c10bb615fb1e4768cdd4b99acf831b", "dirty": False,
          "version": "0.1.0", "at": "2026-09-03T18:47:29+02:00"}
    out = C._format_model(_sidecar_with_a_model(tmp_path, st), built=False)
    assert "Built unified model" not in out, "a no-op must not claim a build"
    assert out.startswith("Already current at 634408f: 540 objects")
    assert "NOTHING WAS REBUILT" in out
    assert "`--force` rebuilds it" in out


def test_a_dirty_stamp_is_named_in_the_cache_hit(tmp_path):
    st = {"sha": "a" * 40, "dirty": True, "version": "0.1.0", "at": "x"}
    out = C._format_model(_sidecar_with_a_model(tmp_path, st), built=False)
    assert "at aaaaaaa-dirty:" in out


def test_an_unstamped_model_says_so_rather_than_inventing_a_sha(tmp_path):
    out = C._format_model(_sidecar_with_a_model(tmp_path), built=False)
    assert "no build stamp" in out
    assert "unstamped" not in out.split(":")[0], "don't read as a sha named 'unstamped'"


def test_the_two_forms_are_not_confusable(tmp_path):
    sc = _sidecar_with_a_model(tmp_path)
    assert C._format_model(sc) != C._format_model(sc, built=False)


def test_the_cache_hit_branch_passes_built_false():
    """The defect was never in the formatting — it was that the early-return
    branch called the same formatter as a real build."""
    import inspect
    src = inspect.getsource(C.cmd_model)
    line = [l for l in src.splitlines()
            if "return _format_model(sc" in l and "built=False" in l]
    assert line, "cmd_model's cache-hit early return must pass built=False"


def test_the_cache_hit_counts_the_model_not_the_stale_sidecar(tmp_path):
    """576 — measured: 7 of the 21 published sidecars disagree with their model,
    by 2 to 640 objects, because enrichment passes add objects and do not
    revise `model_object_counts`. The sentence names a sha read from the model,
    so it must count that same file."""
    sc = _sidecar_with_a_model(tmp_path)
    mp = C._model_path(sc)
    mp.write_text(json.dumps({"meta": {}, "objects": {
        "a": {"type": "Formula"}, "b": {"type": "Formula"},
        "c": {"type": "Citation"}}}))          # 3 objects; sidecar still says 540
    out = C._format_model(sc, built=False)
    assert "Already current (no build stamp: this model predates 575): 3 objects" in out
    assert "540" not in out, "the sidecar's stale count must not be quoted"
    assert "2 Formula" in out


def test_an_unreadable_model_falls_back_to_the_sidecar_rather_than_crashing(tmp_path):
    sc = _sidecar_with_a_model(tmp_path)
    C._model_path(sc).write_text("{not json")
    out = C._format_model(sc, built=False)
    assert "540 objects" in out, "a corrupt model must not break the summary"
