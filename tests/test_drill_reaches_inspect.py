"""`drill` promises an inspect.html. On the geometry lane it produced none.

Found by an auditing session (drillgroup T-0046 §Audit, at 28b64cef). `drill`'s
own summary says "Ends with an inspect.html you can open", unconditionally. Its
phase 4 was gated on `MODEL_BUILT in Sidecar(pdf).facts`, but on the GEOMETRY
lane phase 3 runs `gemmaocr --geometry-only`, which writes a lines.json and no
model — so the gate was false, the tail was skipped, and `drill <scan>` exited 0
with no inspect.html and a timing table with no `inspect` line.

Measured on a fresh 10-page scan (hilbert1902, keyless, no detector): 40.70 s
spent, nothing to open. Run standalone on exactly that state, `pdfdrill inspect`
built the model itself (79 equations, 50 paragraphs) and wrote a 1.6 MB
inspect.html with 133 elements. So the gate was not merely wrong, it was
unnecessary: the condition is "a READING exists", not "a model exists".
"""
from pathlib import Path


def test_the_gate_asks_whether_a_reading_exists_not_whether_a_model_does():
    src = (Path(__file__).resolve().parents[1] / "src" / "pdfdrill" / "cli.py").read_text()
    assert "_has_reading" in src, "drill's phase-4 gate is not the reading check"
    assert "_lines_json_path(pdf).is_file()" in src, (
        "the gate does not count a lines.json as a reading, so the geometry "
        "lane still cannot reach `inspect`")


def test_drill_still_skips_the_tail_when_nothing_was_read():
    """The gate must stay closed for a paid lane that was NAMED and not run:
    an inspector of nothing is worse than the note naming the command."""
    src = (Path(__file__).resolve().parents[1] / "src" / "pdfdrill" / "cli.py").read_text()
    i = src.index("_has_reading")
    assert "if _has_reading:" in src[i:i + 400], (
        "the tail is no longer conditional at all — a paid lane that was not "
        "run would get an inspector of nothing")


def test_drills_promise_still_says_it_ends_with_an_inspect_html():
    """If the promise is ever weakened, this test should be the thing that
    notices — the defect was the gap between the promise and the behaviour."""
    y = (Path(__file__).resolve().parents[1] / ".claude" / "skills" / "pdfdrill"
         / "commands.yaml").read_text()
    assert "Ends with an inspect.html" in y, (
        "drill no longer promises an inspect.html; if that is deliberate, the "
        "geometry-lane fix and this test need revisiting together")
