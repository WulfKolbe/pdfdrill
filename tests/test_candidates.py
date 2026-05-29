"""
Functional tests for the external-candidate flow (candidates export + ingest).
No network: a synthetic model is written under a temp <pdf>.drill/ and the
sidecar is pre-marked MODEL_BUILT so no rebuild/MathPix call happens.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.sidecar import Sidecar
from pdfdrill.commands import cmd_candidates, cmd_ingest, MODEL_BUILT


def _setup(tmp: Path) -> Path:
    pdf = tmp / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i in range(2):
        doc.add(DocObject(type="Equation", props={
            "latex": f"x_{{{i}}}", "cdn_url": f"https://cdn/{i}.jpg",
            "refnum": str(i), "page": 1,
        }))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(
        json.dumps(doc.to_dict()), encoding="utf-8")
    sc.add_fact(MODEL_BUILT)
    sc.save()
    return pdf


def test_candidates_export_then_ingest_round_trip():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pdf = _setup(tmp)

        msg = cmd_candidates(pdf, provider="llm")
        assert "2 'llm' candidate slots" in msg

        man_path = tmp / "paper.pdf.drill" / "candidates.llm.json"
        manifest = json.loads(man_path.read_text())
        assert manifest["provider"] == "llm"
        assert len(manifest["equations"]) == 2
        assert all(e["latex"] == "" for e in manifest["equations"])
        assert all(e["cdn_url"] for e in manifest["equations"])

        # Simulate the LLM filling in each entry's latex.
        for e in manifest["equations"]:
            e["latex"] = "LLM:" + e["eq_id"][-4:]
        man_path.write_text(json.dumps(manifest), encoding="utf-8")

        out = cmd_ingest(pdf, str(man_path), provider="llm")
        assert "Ingested 2 'llm'" in out

        model = json.loads((tmp / "paper.pdf.drill" / "model.docmodel.json").read_text())
        cands = [r for o in model["objects"] for r in o["realizations"]
                 if r.get("provenance") == "llm" and r.get("role") == "latex_candidate"]
        assert len(cands) == 2
        assert all(c["props"]["latex"].startswith("LLM:") for c in cands)


def test_ingest_is_idempotent_without_force():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pdf = _setup(tmp)
        cmd_candidates(pdf, provider="llm")
        man_path = tmp / "paper.pdf.drill" / "candidates.llm.json"
        manifest = json.loads(man_path.read_text())
        for e in manifest["equations"]:
            e["latex"] = "a+b"
        man_path.write_text(json.dumps(manifest), encoding="utf-8")

        cmd_ingest(pdf, str(man_path), provider="llm")
        out2 = cmd_ingest(pdf, str(man_path), provider="llm")
        assert "already present" in out2

        model = json.loads((tmp / "paper.pdf.drill" / "model.docmodel.json").read_text())
        cands = [r for o in model["objects"] for r in o["realizations"]
                 if r.get("provenance") == "llm"]
        assert len(cands) == 2  # not duplicated


def test_ingest_accepts_bare_list():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        pdf = _setup(tmp)
        model = json.loads((tmp / "paper.pdf.drill" / "model.docmodel.json").read_text())
        ids = [o["id"] for o in model["objects"] if o["type"] == "Equation"]
        bare = tmp / "bare.json"
        bare.write_text(json.dumps([{"eq_id": ids[0], "latex": "z", "confidence": 0.8}]))
        out = cmd_ingest(pdf, str(bare), provider="gpt")
        assert "Ingested 1 'gpt'" in out
        model2 = json.loads((tmp / "paper.pdf.drill" / "model.docmodel.json").read_text())
        cand = [r for o in model2["objects"] for r in o["realizations"]
                if r.get("provenance") == "gpt"][0]
        assert cand["score"] == 0.8


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
