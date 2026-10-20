"""
`pdfdrill route --run` executes the chosen lane, and the five lanes of the
contract (docs/LANES.md) each dispatch to the command `route` NAMED:

  * born_digital → pdfminer → lines.json → cmd_model                 (FREE)
  * source       → cmd_model, which takes the author's LaTeX itself   (FREE)
  * gemma        → cmd_gemmaocr → cmd_model --no-source           (METERED)
  * mathpix      → cmd_mathpix --force → cmd_model                   (PAID)
  * geometry     → cmd_gemmaocr --geometry-only, and STOPS there      (FREE)

The report and the execution must not drift apart, which is why each of these
asserts the command, not just the output. Dispatch is tested with the lane
commands monkeypatched (no real OCR, no network, no spend).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill import ocr_router as R


def _dec(lane):
    return R.RouteDecision(lane=lane, reason="r", command="c", cost="x")


def test_execute_born_digital_runs_pdfminer_then_model(monkeypatch):
    calls = []
    monkeypatch.setattr(C, "_run_born_digital",
                        lambda pdf: calls.append("born") or "MODEL built (pdfminer)")
    out = C._execute_lane(Path("x.pdf"), _dec("born_digital"))
    assert calls == ["born"] and "MODEL built" in out
    assert "born-digital" in out.lower()


def test_execute_gemma_runs_gemmaocr_then_model(monkeypatch):
    """The METERED model lane, not the old 50 s/page vision call. `--no-source`
    because a scan this lane read has no author's LaTeX to prefer."""
    order = []
    monkeypatch.setattr(C, "cmd_gemmaocr",
                        lambda pdf, **k: order.append(("gemmaocr", k)) or "GEMMA")
    monkeypatch.setattr(C, "cmd_model",
                        lambda pdf, **k: order.append(("model", k)) or "MODEL")
    out = C._execute_lane(Path("x.pdf"), _dec("gemma"))
    assert [n for n, _ in order] == ["gemmaocr", "model"]
    assert order[1][1].get("no_source") is True
    assert "GEMMA" in out and "MODEL" in out


def test_execute_source_lane_is_model(monkeypatch):
    calls = []
    monkeypatch.setattr(C, "cmd_model",
                        lambda pdf, **k: calls.append("model") or "MODEL")
    out = C._execute_lane(Path("x.pdf"), _dec("source"))
    assert calls == ["model"] and "MODEL" in out


def test_execute_geometry_lane_is_free_and_stops_at_the_lines_json(monkeypatch):
    """No words are read, so `model` is not its consumer — a model keeps what
    has prose. Running one here would print ten empty Paragraphs and look like
    a failure."""
    order = []
    monkeypatch.setattr(C, "cmd_gemmaocr",
                        lambda pdf, **k: order.append(("gemmaocr", k)) or "SHAPE")
    monkeypatch.setattr(C, "cmd_model",
                        lambda pdf, **k: order.append(("model", k)) or "MODEL")
    out = C._execute_lane(Path("x.pdf"), _dec("geometry"))
    assert [n for n, _ in order] == ["gemmaocr"]
    assert order[0][1].get("geometry_only") is True
    assert "SHAPE" in out


def test_execute_mathpix_runs_mathpix_force_then_model(monkeypatch):
    order = []
    monkeypatch.setattr(C, "cmd_mathpix",
                        lambda pdf, force=False: order.append(("mathpix", force)) or "MP")
    monkeypatch.setattr(C, "cmd_model",
                        lambda pdf, **k: order.append(("model", None)) or "MODEL")
    out = C._execute_lane(Path("x.pdf"), _dec("mathpix"))
    assert order == [("mathpix", True), ("model", None)]
    assert "MP" in out and "MODEL" in out


def test_born_digital_prefers_drillpdfse_then_model(monkeypatch, tmp_path):
    """_run_born_digital shells DRILLPDFse's lines_json.py (writing the sibling
    lines.json) then builds the model — the free pdfminer route."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    lj = tmp_path / "paper.lines.json"

    def fake_run(cmd, **kw):
        # simulate DRILLPDFse producing the lines.json
        lj.write_text('{"source":"pdfminer","pages":[]}')
        class R2:
            returncode = 0; stdout = ""; stderr = ""
        return R2()
    monkeypatch.setenv("DRILLPDFSE_DIR", str(tmp_path))
    (tmp_path / "lines_json.py").write_text("# stub")
    monkeypatch.setattr(C.subprocess, "run", fake_run)
    monkeypatch.setattr(C, "cmd_model", lambda pdf, **k: "MODEL from pdfminer")
    out = C._run_born_digital(pdf)
    assert lj.exists() and "pdfminer" in out.lower() and "MODEL" in out


def test_born_digital_falls_back_when_no_drillpdfse(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setenv("DRILLPDFSE_DIR", str(tmp_path / "absent"))
    monkeypatch.setattr(C, "cmd_model", lambda pdf, **k: "MODEL (pdfdrill own build)")
    out = C._run_born_digital(pdf)
    assert "MODEL" in out


def test_route_without_run_reports_and_hints(monkeypatch, tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    # pretend size already classified it born-digital
    from pdfdrill.sidecar import Sidecar
    sc = Sidecar(pdf)
    sc.set_evidence("text_layer", True)
    sc.set_evidence("needs_ocr", False)
    sc.set_evidence("pages", 10)
    sc.add_fact(C.SIZE_KNOWN)
    sc.save()
    fired = []
    monkeypatch.setattr(C, "_execute_lane", lambda *a: fired.append(1) or "RAN")
    out = C.cmd_route(pdf, run=False)
    assert not fired and "--run" in out           # reports, does NOT execute


if __name__ == "__main__":
    import types
    # minimal monkeypatch shim for standalone run
    class MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n, None))); setattr(o, n, v)
        def setenv(self, k, v): import os; os.environ[k] = v
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
    import inspect, tempfile
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        mp = MP()
        try:
            params = inspect.signature(t).parameters
            args = []
            td = None
            if "monkeypatch" in params: args.append(mp)
            if "tmp_path" in params:
                td = tempfile.mkdtemp(); args.append(Path(td))
            t(*args); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
        finally:
            mp.undo()
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
