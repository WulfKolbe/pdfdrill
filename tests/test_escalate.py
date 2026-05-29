"""
Functional test for the Phase-3 closed loop: escalate -> ingest -> relearn.
A flagged equation (single low-confidence snip reading) gets a corroborating
LLM reading; relearn should report it resolved. No network.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill.sidecar import Sidecar
from pdfdrill.commands import cmd_escalate, cmd_ingest, cmd_relearn, MODEL_BUILT


def _setup(tmp: Path) -> Path:
    pdf = tmp / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    doc = Document()
    doc.meta["bibkey"] = "T"
    e = DocObject(type="Equation", props={
        "latex": "E=mc^2", "refnum": "1", "page": 1, "cdn_url": "https://cdn/x.jpg"})
    e.add_realization(Realization(stream="snip", role="latex_candidate",
                                  provenance="snip", score=0.30,
                                  props={"latex": "E=mc^2"}))   # single, low conf
    doc.add(e)
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
    sc.add_fact(MODEL_BUILT)
    sc.save()
    return pdf


def test_escalate_ingest_relearn_resolves_flag():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pdf = _setup(tmp)

        msg = cmd_escalate(pdf)
        assert "Escalated 1" in msg
        man = tmp / "paper.pdf.drill" / "escalate.llm.json"
        manifest = json.loads(man.read_text())
        assert len(manifest["equations"]) == 1
        assert "low_confidence" in manifest["equations"][0]["current_flags"]

        # Corroborating LLM reading.
        manifest["equations"][0]["latex"] = "E = mc^{2}"
        man.write_text(json.dumps(manifest))

        cmd_ingest(pdf, str(man), provider="llm")
        out = cmd_relearn(pdf)
        assert "1 resolved" in out

        sc = Sidecar(pdf)
        assert sc.get_evidence("relearn_resolved") == 1


def test_relearn_without_escalation_is_noop():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pdf = _setup(tmp)
        out = cmd_relearn(pdf)
        assert "No open escalation" in out


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
