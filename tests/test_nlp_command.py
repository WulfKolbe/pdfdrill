"""
Command-level tests for `pdfdrill nlp` (cmd_nlp).

These don't need the real Stanza model: a fake annotator is injected by
monkeypatching `docops.mutators.stanza_nlp.StanzaAnnotator`, so they exercise
the command's load → annotate → persist → summarize wiring deterministically.
A separate case checks the graceful "Stanza unavailable" message.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.sidecar import Sidecar
from pdfdrill import commands
from pdfdrill.commands import cmd_nlp, MODEL_BUILT, NLP_ENHANCED
import docops.mutators.stanza_nlp as stanza_mod
from docops.nlp_stanza import StanzaUnavailable


class _FakeAnnotator:
    """Returns one sentence with a single PERSON entity, regardless of input."""
    def __init__(self, *a, **k):
        pass

    def annotate(self, clean):
        if not clean.strip():
            return []
        return [{
            "index": 0,
            "text": clean,
            "tokens": [{"id": 1, "text": "X", "lemma": "x", "upos": "PROPN",
                        "xpos": "NNP", "feats": None, "head": 0, "deprel": "root"}],
            "entities": [{"text": "Burkhard Heim", "type": "PERSON",
                          "start_char": 0, "end_char": 13}],
        }]


class _DeadAnnotator:
    def __init__(self, *a, **k):
        pass

    def annotate(self, clean):
        raise StanzaUnavailable("no model")


def _make_model(tmp: Path) -> Path:
    """Write a tiny model.docmodel.json + a MODEL_BUILT sidecar; return pdf path."""
    pdf = tmp / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")  # just needs to exist
    doc = Document()
    for i, txt in enumerate(["Burkhard Heim proposed it.", "He lived in Potsdam."]):
        doc.add(DocObject(type="Paragraph", props={"text": txt, "flow_index": i}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(
        json.dumps(doc.to_dict()), encoding="utf-8")
    sc.add_fact(MODEL_BUILT)
    sc.save()
    return pdf


def test_cmd_nlp_annotates_and_persists(monkeypatch):
    monkeypatch.setattr(stanza_mod, "StanzaAnnotator", _FakeAnnotator)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_nlp(pdf)
        assert "annotated 2 prose object" in out
        assert "Burkhard Heim" in out
        # Persisted under props['nlp'].
        model = json.loads((Path(d) / "doc.pdf.drill" / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        annotated = [o for o in objs if (o.get("props") or {}).get("nlp")]
        assert len(annotated) == 2
        assert annotated[0]["props"]["nlp"]["engine"] == "stanza"
        # Fact recorded.
        assert Sidecar(pdf).has(NLP_ENHANCED)


def test_cmd_nlp_limit(monkeypatch):
    monkeypatch.setattr(stanza_mod, "StanzaAnnotator", _FakeAnnotator)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_nlp(pdf, limit=1)
        assert "annotated 1 prose object" in out


def test_cmd_nlp_graceful_when_unavailable(monkeypatch):
    monkeypatch.setattr(stanza_mod, "StanzaAnnotator", _DeadAnnotator)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_nlp(pdf)
        assert "NLP skipped" in out
        assert "pip install 'pdfdrill[nlp]'" in out
        # Nothing annotated, no NLP fact.
        assert not Sidecar(pdf).has(NLP_ENHANCED)


# Minimal monkeypatch shim so the file runs with plain `python3` too.
if __name__ == "__main__":
    class _MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)
            self._undo = []
    tests = [test_cmd_nlp_annotates_and_persists, test_cmd_nlp_limit,
             test_cmd_nlp_graceful_when_unavailable]
    for fn in tests:
        mp = _MP()
        try:
            fn(mp)
            print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(tests)} tests passed.")
