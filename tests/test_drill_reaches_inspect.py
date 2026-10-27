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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import cli, commands, ocr_router as R      # noqa: E402
from pdfdrill.sidecar import Sidecar                     # noqa: E402


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


# --------------------------------------------------------------------------- #
#  …and the same three tests again, as BEHAVIOUR.
#
#  An auditing session (finding E) pointed out that everything above greps
#  `cli.py` for a variable name. That holds the shape of the fix in place and
#  proves nothing about what `drill` does: rename `_has_reading` and the tests
#  fail while the behaviour is fine; break the dispatch around it and they
#  pass while `drill` produces no inspect.html again — which is the exact
#  defect they were written for.
#
#  The real thing costs 53 s (measured: hilbert1902, 10 pages, the geometry
#  lane). What the GATE needs is not the lane: it is a lines.json on disk and
#  no model. So the lane is stubbed and the question asked directly.
# --------------------------------------------------------------------------- #

def _seed_scan(tmp_path) -> Path:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 10)
    sc.set_evidence("text_layer", False)
    sc.set_evidence("needs_ocr", True)
    for fact in (commands.SIZE_KNOWN, commands.FONTS_KNOWN,
                 commands.ABSTRACT_ABSENT, commands.TOC_ABSENT):
        sc.add_fact(fact)
    sc.save()
    return pdf


def _stub_tail(monkeypatch, reached):
    for name in ("cmd_geometry", "cmd_inspect"):
        monkeypatch.setattr(commands, name,
                            (lambda n: lambda *a, **k: reached.append(n) or "")(name))


def test_the_geometry_lane_actually_reaches_inspect(tmp_path, monkeypatch):
    """The defect, as behaviour: a lines.json and no model must still reach it."""
    pdf = _seed_scan(tmp_path)
    reached: list[str] = []
    lines_json = commands._lines_json_path(pdf)

    def fake_lane(*a, **k):
        lines_json.parent.mkdir(parents=True, exist_ok=True)
        lines_json.write_text('{"pages": [{"lines": []}]}', encoding="utf-8")
        return "stub geometry reading"

    monkeypatch.setattr(commands, "cmd_gemmaocr", fake_lane)
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    _stub_tail(monkeypatch, reached)
    out = cli._do_drill([str(pdf)])
    assert reached == ["cmd_geometry", "cmd_inspect"], (
        f"drill did not reach the inspector on the geometry lane: {reached!r}")
    assert "inspect" in out


def test_a_named_but_unrun_paid_lane_reaches_nothing(tmp_path, monkeypatch):
    """The other side of the same gate: nothing on disk, so no inspector of
    nothing. Driven by giving the install a MathPix key and no free lane."""
    pdf = _seed_scan(tmp_path)
    reached: list[str] = []
    monkeypatch.setattr(R, "keys_present", lambda: frozenset({R.MATHPIX_KEY}))
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    _stub_tail(monkeypatch, reached)
    out = cli._do_drill([str(pdf)])
    assert reached == [], f"drill inspected a document it never read: {reached!r}"
    assert "NOT RUN by `drill`" in out and "costs money" in out


def test_an_inspector_with_no_page_images_reaches_drills_exit_status(
        tmp_path, monkeypatch):
    """Rule 41, one level up. `inspect` carries EXIT_LANE_NOT_RUN for an
    inspector whose every page is blank; a caller of `drill` must not have to
    read the inspect section to learn that the artifact it promised has no
    pages in it. `drill` already makes exactly this statement for a lane that
    was reported and not run."""
    from pdfdrill.cli import EXIT_LANE_NOT_RUN, Report
    pdf = _seed_scan(tmp_path)
    lines_json = commands._lines_json_path(pdf)

    def fake_lane(*a, **k):
        lines_json.parent.mkdir(parents=True, exist_ok=True)
        lines_json.write_text('{"pages": [{"lines": []}]}', encoding="utf-8")
        return "stub geometry reading"

    monkeypatch.setattr(commands, "cmd_gemmaocr", fake_lane)
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    monkeypatch.setattr(commands, "cmd_geometry", lambda *a, **k: "")
    monkeypatch.setattr(commands, "cmd_inspect", lambda *a, **k: Report(
        "scan.pdf: the inspector has 0 of 10 page images, so every box sits "
        "on a blank page.", EXIT_LANE_NOT_RUN))
    out = cli._do_drill([str(pdf)])
    assert "0 of 10 page images" in out, out
    assert getattr(out, "exit_code", 0) == EXIT_LANE_NOT_RUN, (
        "drill reported success over an inspector with no pages (exit "
        f"{getattr(out, 'exit_code', 0)})")


def test_no_inspect_still_stops_at_geometry(tmp_path, monkeypatch):
    """`--no-inspect` is the one documented way to get the tail without it."""
    pdf = _seed_scan(tmp_path)
    reached: list[str] = []
    lines_json = commands._lines_json_path(pdf)

    def fake_lane(*a, **k):
        lines_json.parent.mkdir(parents=True, exist_ok=True)
        lines_json.write_text('{"pages": [{"lines": []}]}', encoding="utf-8")
        return ""

    monkeypatch.setattr(commands, "cmd_gemmaocr", fake_lane)
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    _stub_tail(monkeypatch, reached)
    cli._do_drill([str(pdf), "--no-inspect"])
    assert reached == ["cmd_geometry"], f"--no-inspect was not honoured: {reached!r}"
