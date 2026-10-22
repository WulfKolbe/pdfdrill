"""A lane the install cannot run must be NAMED, not run.

Found by an auditing session (drillgroup T-0046 §Audit, finding B, at
19e097d1). On an install with no NumPy, `pdfdrill drill <scan>` rendered ten
page images (8.58 MB, measured on hilbert1902 in a numpy-free venv), died
inside the ink, printed "The pages already read are kept … and a rerun resumes
from them" over a directory holding zero readings, and exited 0.

Three separate defects, one shape — work spent for a reading that could not
happen, and a report asserting state nobody looked at:

1. `choose_route` asked `ink_available()` only inside `if detector is False`,
   so an install WITH the detector and WITHOUT NumPy was promised "a box and a
   type on every line". The halves are not symmetric: the ink FINDS the lines,
   the detector TYPES them. No detector is a weaker lane; no ink is no lane.
2. `drill` dispatched on `dec.lane == "geometry"` and never looked at
   `dec.cost`, so `cost="none"` — which means "this is the lane, and this
   install cannot run it" — ran it anyway.
3. `cmd_gemmaocr`'s failure note promised a resume for every failure, including
   `--geometry-only`, which reads no pages and can never have one.

docs/LANES.md: the geometry lane is the LAST RESORT, the reading a keyless
install can always reach. An install where it cannot run has no lane at all,
and that is the sentence the user needs — not ten PNGs and exit 0.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import cli, commands, ocr_router as R      # noqa: E402
from pdfdrill.sidecar import Sidecar                     # noqa: E402

SCAN = dict(text_layer=False, needs_ocr=True, page_count=10, keys=frozenset())


def test_no_ink_is_no_lane_even_with_the_detector():
    """THE CASE BUILT TO FAIL. This is the install the old check missed: the
    detector is a SEPARATE interpreter, so it is present on plenty of machines
    whose pdfdrill environment has no NumPy."""
    d = R.choose_route(**SCAN, detector=True, ink=False)
    assert d.lane == "geometry"
    assert d.cost == "none", (
        f"the route still offers the lane as {d.cost!r} with no ink half: "
        f"{d.reason}")
    assert "numpy" in d.reason.lower(), "the reason does not name what is absent"
    assert "numpy" in d.command.lower(), "the command does not say how to fix it"


def test_no_detector_is_still_a_lane():
    """The other half, unchanged — a weaker lane is not an absent one."""
    d = R.choose_route(**SCAN, detector=False, ink=True)
    assert (d.lane, d.cost) == ("geometry", "free")
    assert "NO type" in d.reason or "no type" in d.reason.lower()


def test_neither_half_is_also_no_lane():
    d = R.choose_route(**SCAN, detector=False, ink=False)
    assert (d.lane, d.cost) == ("geometry", "none")


def _seed_scan(tmp_path) -> Path:
    """A document already past `drill`'s cheap probes, routed as a keyless scan.

    The bytes are not a PDF on purpose: this test is about the DISPATCH, and
    nothing downstream of the dispatch may run. A real PDF here would hide the
    defect behind a parse error.
    """
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


def test_drill_does_not_run_a_lane_that_cannot_run(tmp_path, monkeypatch):
    pdf = _seed_scan(tmp_path)
    calls = []
    monkeypatch.setattr(commands, "cmd_gemmaocr",
                        lambda *a, **k: calls.append((a, k)) or "")
    monkeypatch.setattr(R, "ink_available", lambda: False)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    out = cli._do_drill([str(pdf)])
    assert not calls, (
        "drill called the geometry lane on an install that cannot run it — "
        "that is one page render per page, spent for nothing")
    assert "NOT RUN by `drill`" in out, (
        "drill did not say the lane was not run:\n" + out)
    assert "nothing was read" in out.lower()


def test_drill_does_run_it_when_the_lane_is_there(tmp_path, monkeypatch):
    """The guard must be the COST, not the lane — otherwise the fix for a
    missing NumPy silently retires the free lane for everyone."""
    pdf = _seed_scan(tmp_path)
    calls = []
    monkeypatch.setattr(commands, "cmd_gemmaocr",
                        lambda *a, **k: calls.append((a, k)) or "")
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    cli._do_drill([str(pdf)])
    assert calls and calls[0][1].get("geometry_only") is True, (
        f"drill no longer runs the free geometry lane: {calls!r}")


def test_gemmaocr_geometry_only_refuses_before_rendering(tmp_path, monkeypatch):
    pdf = _seed_scan(tmp_path)
    rendered = []
    from pdfdrill import pdf_reading
    monkeypatch.setattr(pdf_reading, "rasterize",
                        lambda *a, **k: rendered.append(a) or [])
    monkeypatch.setattr(R, "ink_available", lambda: False)
    out = commands.cmd_gemmaocr(pdf, geometry_only=True)
    assert not rendered, "the refusal came after the rasterizer had run"
    assert "NOT run" in out and "numpy" in out.lower()


def test_a_failed_read_does_not_claim_pages_it_never_read(tmp_path, monkeypatch):
    """The note promised a resume without looking at the directory."""
    pdf = _seed_scan(tmp_path)
    from pdfdrill import gemma_reader

    def boom(*a, **k):
        raise RuntimeError("ink geometry needs numpy")

    monkeypatch.setattr(gemma_reader, "fetch_gemma", boom)
    monkeypatch.setattr(R, "ink_available", lambda: True)   # past the guard
    out = commands.cmd_gemmaocr(pdf, geometry_only=True)
    assert "read failed" in out
    assert "already read are kept" not in out, (
        "the failure still claims pages were read:\n" + out)
    assert "nothing to resume" in out.lower()


# --------------------------------------------------------------------------- #
#  EXIT STATUS. The owner's decision (2026-10-21): non-zero for BOTH.
#
#  `drill` promises "Ends with an inspect.html you can open". When it reports a
#  lane and does not run it there is none — whether the install cannot run the
#  lane, or the lane costs money and `drill` never spends. Exiting 0 for that
#  makes the outcome unreadable to a script: every caller would have to parse
#  prose to learn whether it got a reading. The message is unchanged; only the
#  status is new.
# --------------------------------------------------------------------------- #

def test_the_exit_code_is_declared_once_and_is_not_zero():
    assert cli.EXIT_LANE_NOT_RUN == 3, (
        f"the documented code is 3; drill now returns {cli.EXIT_LANE_NOT_RUN}. "
        f"docs/LANES.md and the command's help quote it.")


def test_no_lane_on_this_install_exits_non_zero(tmp_path, monkeypatch):
    pdf = _seed_scan(tmp_path)
    monkeypatch.setattr(commands, "cmd_gemmaocr", lambda *a, **k: "")
    monkeypatch.setattr(R, "ink_available", lambda: False)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    out = cli._do_drill([str(pdf)])
    assert getattr(out, "exit_code", 0) == cli.EXIT_LANE_NOT_RUN, (
        "drill reported a lane it cannot run and still exited 0")
    assert "NOT RUN by `drill`" in out, "the message changed"
    assert f"exit {cli.EXIT_LANE_NOT_RUN}" in out, (
        "the output does not say what the status means")


def test_a_paid_lane_named_and_not_run_exits_non_zero_too(tmp_path, monkeypatch):
    """The owner chose both cases, and the reason is the same for both: there is
    no inspect.html either way."""
    pdf = _seed_scan(tmp_path)
    monkeypatch.setattr(R, "keys_present", lambda: frozenset({R.MATHPIX_KEY}))
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    out = cli._do_drill([str(pdf)])
    assert getattr(out, "exit_code", 0) == cli.EXIT_LANE_NOT_RUN, (
        "a paid lane was named and not run, and drill exited 0")
    assert "costs money" in out, "the paid-lane message changed"


def test_a_lane_that_DID_run_still_exits_zero(tmp_path, monkeypatch):
    """The guard that keeps this from becoming 'drill always fails'."""
    pdf = _seed_scan(tmp_path)
    lines_json = commands._lines_json_path(pdf)

    def fake_lane(*a, **k):
        lines_json.parent.mkdir(parents=True, exist_ok=True)
        lines_json.write_text('{"pages": [{"lines": []}]}', encoding="utf-8")
        return "stub reading"

    monkeypatch.setattr(commands, "cmd_gemmaocr", fake_lane)
    monkeypatch.setattr(commands, "cmd_geometry", lambda *a, **k: "")
    monkeypatch.setattr(commands, "cmd_inspect", lambda *a, **k: "")
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    out = cli._do_drill([str(pdf)])
    assert getattr(out, "exit_code", 0) == 0, (
        "the free lane ran and drill still reported a failure")


def test_main_returns_the_handlers_code():
    """The carrier has to survive `main`, which is what the shell sees."""
    r = cli.Report("body", cli.EXIT_LANE_NOT_RUN)
    assert isinstance(r, str) and str(r) == "body"
    assert getattr(r, "exit_code", 0) == cli.EXIT_LANE_NOT_RUN
    src = (ROOT / "src" / "pdfdrill" / "cli.py").read_text()
    assert 'return getattr(result, "exit_code", 0)' in src, (
        "main no longer reads the handler's exit code, so the status is lost "
        "between the handler and the shell")
