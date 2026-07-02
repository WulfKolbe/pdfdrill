"""
S6.2 (+A4): `pdfdrill ask` — gated, grounded answering. The answer is composed
in a PRODUCT TUPLE per part (value, witnesses, count, calibrated_precision) and
collapses ONLY at the final rendering: the grounded/derived/proposed label is a
READOUT, --precision suppresses `proposed` parts and says what was withheld,
and abstention (no grounded/derived part at all) is the bottom of the status
space — an explicit no-grounded-answer with zero paragraphs quoted.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_ask
from pdfdrill.sidecar import Sidecar
from pdfdrill import model_io
from docmodel.core import Document, DocObject


def _make_model(d: Path) -> Path:
    """A drilled fixture modeled on 2303.11082: a measured, verifiable
    derivation bound in a paragraph + unrelated prose (incl. BERT-large with
    NO parameter count anywhere)."""
    pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4")
    doc = Document(); doc.meta["bibkey"] = "doc"
    doc.add(DocObject(type="Formula", id="q1", props={
        "latex": "d", "flow_index": 1, "page": 9,
        "quant": [{"kind": "derivation", "value": 6769133, "unit": None,
                   "dimension": None, "raw": "d", "witness": ["q1"],
                   "payload": {"lhs_terms": [7871085, 0.86], "op": "mul",
                               "rhs": 6769133}}]}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We could add {{doc_FO0001||FO}} new facts automatically.",
        "page": 9, "flow_index": 2,
        "meas": [{"concept": "addable facts", "concept_source": "section",
                  "measure": "could add",
                  "quantity_ref": {"obj_id": "q1", "idx": 0},
                  "conditions": {"accuracy": 0.82},
                  "sentence_span": [0, 40], "witness": ["p1", "q1"]}]}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "We compare against BERT-large as the baseline model.",
        "page": 3, "flow_index": 3}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_io.save_model(sc.blob_dir / "model.docmodel.json", doc)
    sc.add_fact("MODEL_BUILT")
    sc.save()
    return pdf


def test_grounded_derived_answer_with_proof_block():
    with tempfile.TemporaryDirectory() as d:
        out = cmd_ask(_make_model(Path(d)),
                      "how many facts could be added automatically?")
        assert "6769133" in out
        assert "derived" in out                       # the VER-checked label
        # the proof block cites the witness ids — no lookup, they flowed through
        assert "p1" in out and "q1" in out
        assert "computed" in out                      # the recompute detail
        assert "accuracy" in out                      # the conditions surface


def test_no_grounded_answer_quotes_nothing():
    with tempfile.TemporaryDirectory() as d:
        out = cmd_ask(_make_model(Path(d)),
                      "what is BERT-large's parameter count?")
        assert "no grounded answer" in out.lower()
        # zero paragraphs quoted — the baseline prose must NOT leak in
        assert "baseline model" not in out


def test_precision_gate_withholds_and_says_so():
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        # ungated: the proposed prose context may accompany the derived part
        full = cmd_ask(pdf, "how many facts could be added automatically?")
        # gated: proposed parts suppressed, and the report SAYS what was withheld
        gated = cmd_ask(pdf, "how many facts could be added automatically?",
                        precision=0.9)
        assert "6769133" in gated                     # the derived part survives
        assert "withheld" in gated.lower()
        assert "proposed" in gated.lower()


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
