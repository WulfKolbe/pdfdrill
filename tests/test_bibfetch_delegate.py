"""
Keyless BibTeX delegation (cmd_bibfetch): with no PERPLEXITY_API_KEY, the
web-search BibTeX task is delegated to the Claude agent running pdfdrill — CLI
(`claude -p` synchronous) or sandbox (deferred request/response handshake) —
handed perplexity_client's OWN bibtex_prompt. The applied fields are identical
to the API path. Mirrors the vision delegation test.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands, perplexity_client, llm_delegate
from pdfdrill.commands import cmd_bibfetch, BIBFETCH_DONE
from pdfdrill.sidecar import Sidecar
from docmodel.core import Document, DocObject, Realization


def _make_model(d: Path) -> Path:
    """A minimal drilled doc with one truncated Reference (no bibtex yet)."""
    pdf = d / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc = Document()
    s = doc.ensure_stream("references")
    a = s.append(type="ref")
    r = DocObject(type="Reference", props={
        "citekey": "vaswani2017", "author": "Vaswani, A. et al.", "year": "2017",
        "title": "Attention Is All You Need", "raw_text": "Vaswani et al. 2017."})
    r.add_realization(Realization(stream="references", start=a, end=a, role="surface"))
    doc.add(r)
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
    sc.add_fact("BIBLIOGRAPHY_BUILT")
    sc.save()
    return pdf


def test_bibfetch_no_key_no_agent_is_graceful(monkeypatch):
    monkeypatch.setattr(perplexity_client, "available", lambda: False)
    monkeypatch.setattr(llm_delegate, "detect_runtime", lambda: llm_delegate.Runtime.NONE)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_bibfetch(pdf)
        assert "PERPLEXITY_API_KEY" in out
        assert not Sidecar(pdf).has(BIBFETCH_DONE)


def test_bibfetch_delegates_in_cli(monkeypatch):
    # No key, but a CLI Claude agent: delegate_batch answers synchronously with a
    # web-searched BibTeX; cmd_bibfetch applies it like the API path.
    monkeypatch.setattr(perplexity_client, "available", lambda: False)
    monkeypatch.setattr(llm_delegate, "detect_runtime", lambda: llm_delegate.Runtime.CLI)
    BIB = ("@inproceedings{vaswani2017, title={Attention Is All You Need}, "
           "author={Vaswani, Ashish and Shazeer, Noam and Polosukhin, Illia}, "
           "year={2017}, pages={5998--6008}, booktitle={NeurIPS}}")

    def fake_batch(tasks, **kw):
        res = {}
        for t in tasks:
            assert t.kind == "bibtex"
            assert "Attention Is All You Need" in t.prompt   # the REAL bibtex_prompt
            res[t.task_id] = {"bibtex": BIB, "citations": [],
                              "fields": perplexity_client.parse_bibtex_fields(BIB)}
        return res, None
    monkeypatch.setattr(llm_delegate, "delegate_batch", fake_batch)

    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_bibfetch(pdf)
        assert "delegating" in out and "cli" in out
        assert Sidecar(pdf).has(BIBFETCH_DONE)
        doc = Document.from_dict(json.load(open(Sidecar(pdf).blob_dir / "model.docmodel.json")))
        ref = [o for o in doc.objects.values() if o.type == "Reference"][0]
        assert "5998--6008" in ref.props["bibtex"]
        assert ref.props.get("entry_type") == "inproceedings"


def test_bibfetch_defers_in_sandbox(monkeypatch):
    monkeypatch.setattr(perplexity_client, "available", lambda: False)
    monkeypatch.setattr(llm_delegate, "detect_runtime", lambda: llm_delegate.Runtime.SANDBOX)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        sc = Sidecar(pdf)
        # pass 1: defer — request file written, instruction returned
        out1 = cmd_bibfetch(pdf)
        assert "deferred" in out1 and "PDFDRILL-LLM-DELEGATION" in out1
        reqs = sorted((sc.blob_dir / "llm").glob("*.req.json"))
        assert len(reqs) == 1 and not sc.has(BIBFETCH_DONE)
        # the agent answers with a fenced bibtex string (lenient path)
        tid = reqs[0].name[:-len(".req.json")]
        (sc.blob_dir / "llm" / (tid + ".resp.json")).write_text(json.dumps({
            "task_id": tid, "kind": "bibtex",
            "result": "```bibtex\n@inproceedings{vaswani2017, year={2017}, pages={5998--6008}}\n```"}))
        # pass 2: ingest
        out2 = cmd_bibfetch(pdf)
        assert "Enriched 1" in out2
        doc = Document.from_dict(json.load(open(sc.blob_dir / "model.docmodel.json")))
        ref = [o for o in doc.objects.values() if o.type == "Reference"][0]
        assert "5998--6008" in ref.props["bibtex"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
