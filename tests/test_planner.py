"""
Prerequisite planner (src/pdfdrill/planner.py) — the state machine that reacts
when a process step has been missed and inserts it automatically.

Each command declares `requires:` (prerequisite commands) and `done_when:` (how
to detect a prereq is already satisfied) in commands.yaml. `plan()` resolves the
ordered missing steps from the current sidecar state; `pdfdrill steps <cmd> <pdf>`
shows the chain; `pdfdrill <cmd> --ensure` runs the missing OFFLINE prereqs first.

Safety: only offline, idempotent prereqs (model, bibliography) are ever
auto-run; paid/network steps (mathpix/bibfetch/vision/translate) are never
auto-inserted — `model` self-bootstraps OCR internally.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import planner


_REQ = {"model": [], "bibliography": ["model"], "report": ["model"],
        "bibfetch": ["bibliography"], "citedrill": ["bibliography"]}


def test_plan_inserts_missing_prereqs_deepest_first():
    steps = planner.plan("bibfetch", _REQ, satisfied=set())
    assert steps == ["model", "bibliography", "bibfetch"]    # deps first, target last


def test_plan_skips_satisfied_prereqs():
    steps = planner.plan("report", _REQ, satisfied={"model"})
    assert steps == ["report"]                               # model done -> only target
    steps2 = planner.plan("bibfetch", _REQ, satisfied={"model"})
    assert steps2 == ["bibliography", "bibfetch"]            # model done, bibliography missing


def test_plan_target_always_runs_even_if_marked_satisfied():
    # the planner never suppresses the explicitly-requested command
    steps = planner.plan("model", _REQ, satisfied={"model"})
    assert steps == ["model"]


def test_plan_is_cycle_safe():
    cyclic = {"a": ["b"], "b": ["a"]}
    steps = planner.plan("a", cyclic, satisfied=set())
    assert steps[-1] == "a" and "b" in steps                 # terminates, no infinite loop


def test_load_graph_from_manifest():
    man = {"commands": [
        {"name": "model", "done_when": "model"},
        {"name": "report", "requires": ["model"]},
        {"name": "size"}]}
    req, done = planner.load_graph(man)
    assert req == {"report": ["model"]}
    assert done == {"model": "model"}


def test_detect_done_specs(tmp_path=None):
    import tempfile
    from pdfdrill.sidecar import Sidecar
    d = Path(tempfile.mkdtemp())
    pdf = d / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    model_path = sc.blob_dir / "model.docmodel.json"
    # nothing built yet
    assert not planner.detect("model", sc, pdf, model_path)
    assert not planner.detect("fact:BIBLIOGRAPHY_BUILT", sc, pdf, model_path)
    # build the artifacts / fact
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("{}")
    sc.add_fact("BIBLIOGRAPHY_BUILT")
    assert planner.detect("model", sc, pdf, model_path)
    assert planner.detect("fact:BIBLIOGRAPHY_BUILT", sc, pdf, model_path)


def test_paid_steps_are_declared_but_never_auto_run():
    """The invariant EVOLVED (2026-08-18): a dependency that is not in the
    manifest is not a dependency, it is a hope — so paid/network steps ARE
    declared in requires chains (reporttex reads what mathpix populates).
    ensure() must NEVER run them: it names them on stderr instead."""
    man = planner.load_manifest()
    req, _ = planner.load_graph(man)
    paid = planner.network_commands(man)
    assert "mathpix" in paid and "cdncrops" in paid
    # the chains the audit demanded are actually declared
    assert "mathpix" in req.get("inspect", [])
    assert {"injectlatex", "cdncrops", "tiddlers"} <= set(req.get("reporttex", []))
    # ensure() skips paid steps and reports them, never calls their handler
    import io, contextlib, tempfile
    from pathlib import Path as _P
    called = []
    handlers = {name: (lambda n: lambda a: called.append(n) or "")(name)
                for name in ("model", "geometry", "tiddlers", "mathpix",
                             "cdncrops", "injectlatex", "bibliography")}
    with tempfile.TemporaryDirectory() as d:
        pdf = _P(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            planner.ensure("reporttex", pdf, handlers, str(pdf))
    assert "mathpix" not in called and "cdncrops" not in called
    assert "mathpix" in err.getvalue() and "pdfdrill mathpix" in err.getvalue()
    assert "model" in called                     # offline prereqs still run


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
