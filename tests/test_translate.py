"""
Tests for the DeepL translation route (pdfdrill.deepl_client + cmd_translate).

No real API call: the DeepL HTTP layer is faked. Covers batch order/empty
passthrough, graceful HTTP-error degradation, the tag→field mapping, and the
cmd_translate transform (translation under the original field name, original
preserved under org_<field>, prose-only, idempotent).
"""
import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import deepl_client, net, commands


class _Resp:
    def __init__(self, body): self._b = body.encode("utf-8")
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _fake_urlopen(translations):
    def f(req, timeout=None, host=None):
        return _Resp(json.dumps({"translations": [{"text": t} for t in translations]}))
    return f


def test_translate_batch_order_and_empty_passthrough(monkeypatch):
    monkeypatch.setattr(deepl_client, "get", lambda *a, **k: "KEY")
    # Only non-empty items are sent; the response maps back to their slots.
    monkeypatch.setattr(net, "urlopen", _fake_urlopen(["Good morning.", "The result."]))
    out = deepl_client.translate_batch(["Guten Morgen.", "", "Das Ergebnis."], "EN-US", "DE")
    assert out == ["Good morning.", "", "The result."]


def test_translate_batch_http_error_returns_originals(monkeypatch):
    monkeypatch.setattr(deepl_client, "get", lambda *a, **k: "KEY")
    def boom(req, timeout=None, host=None):
        raise urllib.error.HTTPError("u", 456, "Quota", {}, io.BytesIO(b"quota exceeded"))
    monkeypatch.setattr(net, "urlopen", boom)
    src = ["Hallo", "Welt"]
    assert deepl_client.translate_batch(src, "EN-US", "DE") == src   # graceful


def test_translate_batch_networkblocked_propagates(monkeypatch):
    monkeypatch.setattr(deepl_client, "get", lambda *a, **k: "KEY")
    def blocked(req, timeout=None, host=None):
        raise net.NetworkBlocked("blocked api.deepl.com")
    monkeypatch.setattr(net, "urlopen", blocked)
    try:
        deepl_client.translate_batch(["x"], "EN-US")
        assert False
    except net.NetworkBlocked:
        pass


def test_field_mapping():
    f = commands._translate_field_for
    assert f({"tags": "paragraph DOC"}) == "text"
    assert f({"tags": "footnote DOC"}) == "text"
    assert f({"tags": "section DOC"}) == "caption"
    assert f({"tags": "equation DOC"}) is None
    assert f({"tags": "code DOC"}) is None
    assert f({"tags": ""}) is None


def _setup(tmp):
    from pdfdrill.sidecar import Sidecar
    pdf = tmp / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
    sc.set_evidence("bibkey", "doc"); sc.save()
    tids = [
        {"title": "doc_PARA_0001", "tags": "paragraph doc", "type": "text/vnd.tiddlywiki",
         "text": "Die Kette beschreibt Elektronen."},
        {"title": "doc_H1", "tags": "section doc", "caption": "Einleitung", "text": "{{x||PARA}}"},
        {"title": "doc_EQ0001", "tags": "equation doc", "latex": "E=mc^2", "text": "$E=mc^2$"},
    ]
    (sc.blob_dir / "doc.tiddlers.json").write_text(json.dumps(tids))
    return pdf, sc.blob_dir


def test_cmd_translate_transform(monkeypatch):
    monkeypatch.setattr(deepl_client, "available", lambda: True)
    # Fake batch: uppercase as a stand-in "translation" (deterministic).
    monkeypatch.setattr(deepl_client, "translate_batch",
                        lambda texts, *a, **k: [t.upper() for t in texts])
    with tempfile.TemporaryDirectory() as d:
        pdf, blob = _setup(Path(d))
        out = commands.cmd_translate(pdf, target_lang="EN-US", source_lang="DE")
        assert "Translated 2" in out                      # PARA text + section caption
        res = json.loads((blob / "doc.en-us.tiddlers.json").read_text())
        by = {t["title"]: t for t in res}
        para = by["doc_PARA_0001"]
        assert para["org_text"] == "Die Kette beschreibt Elektronen."  # original kept
        assert para["text"] == "DIE KETTE BESCHREIBT ELEKTRONEN."       # translation in `text`
        assert "translated" in para["tags"].split() and para["translated_lang"] == "EN-US"
        assert by["doc_H1"]["org_caption"] == "Einleitung"             # section -> caption
        assert "org_text" not in by["doc_EQ0001"]                       # equation untouched
        # Idempotent: re-run translates nothing more.
        out2 = commands.cmd_translate(pdf, target_lang="EN-US")
        assert "Nothing to translate" in out2


def test_translate_model_prose_inplace():
    # the model-prose translator (basis of `translate --md`) translates prose
    # object fields in place and leaves math/code objects untouched.
    from docmodel.core import Document, DocObject
    doc = Document()
    doc.add(DocObject(type="Paragraph", id="p1", props={"text": "Hallo Welt"}))
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Einleitung"}))
    doc.add(DocObject(type="ListItem", id="l1", props={"content": "erstens"}))
    doc.add(DocObject(type="Equation", id="e1", props={"latex": "E=mc^2"}))
    n = commands.translate_model_prose(
        doc, lambda texts, *a, **k: [t.upper() for t in texts],
        target_lang="EN-US", source_lang="DE")
    assert n == 3
    assert doc.objects["p1"].props["text"] == "HALLO WELT"
    assert doc.objects["s1"].props["caption"] == "EINLEITUNG"
    assert doc.objects["l1"].props["content"] == "ERSTENS"
    assert doc.objects["e1"].props["latex"] == "E=mc^2"   # math untouched


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    fns = [test_translate_batch_order_and_empty_passthrough,
           test_translate_batch_http_error_returns_originals,
           test_translate_batch_networkblocked_propagates,
           test_field_mapping, test_cmd_translate_transform,
           test_translate_model_prose_inplace]
    for fn in fns:
        mp = _MP()
        try:
            fn(mp) if fn.__code__.co_argcount else fn(); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(fns)} tests passed.")
