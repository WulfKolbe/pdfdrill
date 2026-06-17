"""
Chat-proxy primitives end-to-end (offline, no LLM): cmd_retrieve transforms a
question into grounded context over a built model; cmd_chatlog stores a Q&A turn
as a sidecar transcript line + an answer kitem in the semantic graph. (The LLM
hop in between is the external drillui_chat proxy's `claude -p` call.)
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_retrieve, cmd_chatlog
from pdfdrill.sidecar import Sidecar
from pdfdrill import model_io
from docmodel.core import Document, DocObject


def _make_model(d: Path) -> Path:
    pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4")
    doc = Document()
    doc.meta["title"] = "A Note on Heat Kernels"
    doc.add(DocObject(type="Abstract", id="abs",
                      props={"text": "Heat kernels on graphs and their spectra."}))
    doc.add(DocObject(type="Paragraph", id="p1",
                      props={"text": "The graph Laplacian eigenvalues govern heat-kernel decay."}))
    doc.add(DocObject(type="Paragraph", id="p2",
                      props={"text": "Administrative notes, invoices, and unrelated matters."}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_io.save_model(sc.blob_dir / "model.docmodel.json", doc)
    sc.save()
    return pdf


def test_cmd_retrieve_json_returns_grounded_units():
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_retrieve(pdf, "how do Laplacian eigenvalues affect the heat kernel?",
                           k=3, as_json=True)
        obj = json.loads(out)
        ids = [u["id"] for u in obj["units"]]
        assert "p1" in ids and "p2" not in ids           # relevant in, irrelevant out
        assert "[p1]" in obj["prompt"]                    # prompt cites unit ids
        assert "Heat Kernels" in obj["prompt"]            # title threaded in


def test_cmd_retrieve_prose():
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_retrieve(pdf, "heat kernel eigenvalues", k=2)
        assert "[p1]" in out and "Top" in out


def test_cmd_chatlog_writes_transcript_and_kitem():
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        msg = cmd_chatlog(pdf, "Why does the heat kernel decay?",
                          "Because the Laplacian eigenvalues control the spectral "
                          "sum [p1].", units="p1,abs", model="claude-test")
        assert "kitem" in msg and "cited unit" in msg
        sc = Sidecar(pdf)
        # transcript
        turns = [json.loads(x) for x in
                 open(sc.blob_dir / "chat.jsonl", encoding="utf-8")]
        assert len(turns) == 1 and turns[0]["units"] == ["p1", "abs"]
        assert turns[0]["model"] == "claude-test"
        # answer kitem in the semantic graph, grounded in the cited units
        from semantic.graph import SemanticGraph
        from semantic.kitems import all_kitems, _own_spans
        g = SemanticGraph.from_dict(json.loads(
            (sc.blob_dir / "doc.semantic.json").read_text()))
        ks = all_kitems(g)
        assert len(ks) == 1 and ks[0].subtype == "answer"
        nodes = {s.get("node") for s in _own_spans(ks[0])}
        assert nodes == {"p1", "abs"}
        # the invocation is recorded as a Transformation(qid="ask")
        assert any(t.qid == "ask" for t in g.transformations.values())


def test_cmd_chatlog_second_turn_appends():
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        cmd_chatlog(pdf, "Q1", "A1 [p1]", units="p1", model="m")
        msg2 = cmd_chatlog(pdf, "Q2", "A2 [abs]", units="abs", model="m")
        assert "#2" in msg2
        sc = Sidecar(pdf)
        assert sum(1 for _ in open(sc.blob_dir / "chat.jsonl", encoding="utf-8")) == 2


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
