"""
`pdfdrill drill` — one command, the whole way, and never a paid one.

It stopped at Markdown, which on an arXiv paper left a geometry-less LaTeX
source model on disk and no inspector at all. The next command to ask for one
got 131 elements with 131 missing boxes, because `model` saw MODEL_BUILT and
returned the cached one.

Two things under test, and they are the two the user asked for:

  * the chain ENDS with an inspector when the lane is free;
  * it never reaches the paid half of a lane — the lane is NAMED, with its
    exact command, and not run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import cli as CLI
from pdfdrill import commands as C
from pdfdrill import ocr_router as R


def _pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


def _stub_probes(monkeypatch, ran):
    for name in ("cmd_size", "cmd_fonts", "cmd_abstract", "cmd_toc",
                 "cmd_md", "cmd_model", "cmd_status"):
        monkeypatch.setattr(C, name,
                            (lambda n: lambda p, **k: ran.append(n) or n)(name))
    monkeypatch.setattr(C, "cmd_geometry",
                        lambda p, **k: ran.append(("geometry", k)) or "GEOM")
    monkeypatch.setattr(C, "cmd_inspect",
                        lambda p, **k: ran.append("inspect") or "INSPECTOR")
    monkeypatch.setattr(C, "cmd_gemmaocr",
                        lambda p, **k: ran.append("gemmaocr") or "SPENT")
    monkeypatch.setattr(C, "cmd_mathpix",
                        lambda p, **k: ran.append("mathpix") or "SPENT")


def _free(lane="born_digital"):
    return R.RouteDecision(lane=lane, reason="free lane", command="pdfdrill model",
                           cost="free")


def _metered():
    return R.RouteDecision(lane="gemma", reason="a scan with a key",
                           command="pdfdrill gemmaocr <pdf>", cost="metered")


def test_a_free_lane_is_drilled_to_an_inspector(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(R, "route_for_sidecar", lambda sc: _free())
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: {"MODEL_BUILT"}))
    out = CLI._do_drill([str(pdf)])
    assert "inspect" in ran, ran
    assert "INSPECTOR" in out
    assert "cmd_model" in ran or "cmd_model" in str(ran)


def test_the_geometry_pass_is_asked_for_the_detector(tmp_path, monkeypatch):
    """`geometry --layout` is the free half of the OCR path, and it is the
    difference between a box-less inspector and a drawn one."""
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(R, "route_for_sidecar", lambda sc: _free())
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: {"MODEL_BUILT"}))
    CLI._do_drill([str(pdf)])
    geom = [k for n, k in (x for x in ran if isinstance(x, tuple))]
    assert geom and geom[0].get("layout") is True


def test_a_paid_lane_is_named_and_not_run(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(R, "route_for_sidecar", lambda sc: _metered())
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: set()))
    out = CLI._do_drill([str(pdf)])
    assert "gemmaocr" not in ran and "mathpix" not in ran
    assert "pdfdrill gemmaocr <pdf>" in out
    assert "NOT RUN" in out and "costs money" in out


def test_the_lane_and_its_reason_are_in_the_output(tmp_path, monkeypatch):
    """The reason a document took the lane it took belongs next to the result,
    not in a separate command the reader has to think to run."""
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(R, "route_for_sidecar", lambda sc: _free())
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: {"MODEL_BUILT"}))
    out = CLI._do_drill([str(pdf)])
    assert "--- lane ---" in out and "free lane" in out


def test_no_inspect_stops_before_the_inspector(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(R, "route_for_sidecar", lambda sc: _free())
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: {"MODEL_BUILT"}))
    out = CLI._do_drill([str(pdf), "--no-inspect"])
    assert "inspect" not in ran
    assert "INSPECTOR" not in out


def test_the_keyless_scan_lane_takes_the_free_geometry_pass(tmp_path,
                                                            monkeypatch):
    """A scan with no key: `drill` must not call `model` (which would refuse,
    there being no lines.json) and must not spend. It takes the free half of
    the OCR path and says what the result is for."""
    pdf = _pdf(tmp_path)
    ran: list = []
    _stub_probes(monkeypatch, ran)
    monkeypatch.setattr(
        R, "route_for_sidecar",
        lambda sc: R.RouteDecision(lane="geometry", reason="no key",
                                   command="pdfdrill gemmaocr <pdf> "
                                           "--geometry-only", cost="free"))
    monkeypatch.setattr(C.Sidecar, "facts", property(lambda self: set()))
    out = CLI._do_drill([str(pdf)])
    assert "gemmaocr" in ran and "cmd_model" not in ran
    assert "mathpix" not in ran
    assert "SPENT" in out            # the stub's output, i.e. the lane ran
