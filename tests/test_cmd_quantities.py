"""
S4.4: `pdfdrill quantities <pdf>` — the quantitative-layer prose report:
quantities by kind, measurements, the verification tally (verified/refuted/
uncheckable) and the top refuted item. Fast read path; hints at `enhance` when
the layer is absent.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_quantities
from pdfdrill.sidecar import Sidecar
from pdfdrill import model_io
from docmodel.core import Document, DocObject


def _make_model(d: Path, with_quant=True, corrupt=False) -> Path:
    pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4")
    doc = Document(); doc.meta["bibkey"] = "doc"
    factor = 0.68 if corrupt else 0.86
    props_fo = {"latex": "d", "flow_index": 1, "page": 9}
    if with_quant:
        props_fo["quant"] = [{"kind": "derivation", "value": 6769133,
                              "unit": None, "dimension": None, "raw": "d",
                              "payload": {"lhs_terms": [7871085, factor],
                                          "op": "mul", "rhs": 6769133}}]
    doc.add(DocObject(type="Formula", id="q1", props=props_fo))
    props_p = {"text": "We could add many facts.", "page": 9, "flow_index": 2}
    if with_quant:
        props_p["quant"] = [{"kind": "ratio", "value": 82, "unit": "%",
                             "dimension": "ratio", "raw": "82%"}]
        props_p["meas"] = [{"concept": "KBC", "concept_source": "section",
                            "measure": "could add",
                            "quantity_ref": {"obj_id": "q1", "idx": 0},
                            "conditions": {}, "sentence_span": [0, 24]}]
    doc.add(DocObject(type="Paragraph", id="p1", props=props_p))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_io.save_model(sc.blob_dir / "model.docmodel.json", doc)
    sc.add_fact("MODEL_BUILT")
    sc.save()
    return pdf


def test_report_counts_and_verification():
    with tempfile.TemporaryDirectory() as d:
        out = cmd_quantities(_make_model(Path(d)))
        assert "2 quantities" in out or "2 quantit" in out
        assert "derivation:1" in out.replace(" ", "") or "derivation: 1" in out
        assert "1 measurement" in out
        assert "1 verified" in out and "0 refuted" in out


def test_report_top_refuted():
    with tempfile.TemporaryDirectory() as d:
        out = cmd_quantities(_make_model(Path(d), corrupt=True))
        assert "1 refuted" in out
        assert "REFUTED" in out or "refuted:" in out.lower()
        assert "5352337" in out          # the recomputed value is shown


def test_hint_when_layer_absent():
    with tempfile.TemporaryDirectory() as d:
        out = cmd_quantities(_make_model(Path(d), with_quant=False))
        assert "enhance" in out and "quantity" in out


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
