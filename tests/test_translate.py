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


def test_translate_model_prose_inplace():
    # Model is translated IN PLACE: translation replaces the field, original kept
    # under `<field>_source`; math untouched; idempotent; --force re-translates
    # from the preserved original (never from the translation).
    from docmodel.core import Document, DocObject
    doc = Document()
    doc.add(DocObject(type="Paragraph", id="p1", props={"text": "Hallo Welt"}))
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Einleitung"}))
    doc.add(DocObject(type="ListItem", id="l1", props={"content": "erstens"}))
    doc.add(DocObject(type="Equation", id="e1", props={"latex": "E=mc^2"}))
    up = lambda texts, *a, **k: [t.upper() for t in texts]

    n = commands.translate_model_prose(doc, up, "EN-US", "DE")
    assert n == 3
    p = doc.objects["p1"]
    assert p.props["text"] == "HALLO WELT" and p.props["text_source"] == "Hallo Welt"
    assert doc.objects["s1"].props["caption_source"] == "Einleitung"
    assert doc.objects["l1"].props["content_source"] == "erstens"
    assert doc.objects["e1"].props["latex"] == "E=mc^2"          # math untouched

    # idempotent: already-translated objects (they carry _source) are skipped
    assert commands.translate_model_prose(doc, up, "EN-US", "DE") == 0

    # --force re-translates FROM the preserved original, not the translation
    n2 = commands.translate_model_prose(
        doc, lambda t, *a, **k: [x + "!" for x in t], "EN-US", "DE", force=True)
    assert n2 == 3
    assert doc.objects["p1"].props["text"] == "Hallo Welt!"      # from text_source
    assert doc.objects["p1"].props["text_source"] == "Hallo Welt"


def test_translate_tiddler_file_inplace():
    # the tiddler-level pass translates prose tiddler text/caption IN the same
    # file (transclusion tokens preserved), keeps the original under _source,
    # and leaves equation tiddlers untouched.
    up = lambda texts, *a, **k: [t.upper() for t in texts]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.tiddlers.json"
        p.write_text(json.dumps([
            {"title": "a", "tags": "paragraph", "text": "hallo {{a||FO}} welt"},
            {"title": "b", "tags": "section", "caption": "einleitung", "text": "{{x||PARA}}"},
            {"title": "c", "tags": "equation", "latex": "E=mc^2", "text": "$E=mc^2$"},
        ]))
        n = commands._translate_tiddler_file_inplace(p, up, "EN-US", "DE")
        assert n == 2
        res = {t["title"]: t for t in json.loads(p.read_text())}
        assert res["a"]["text"] == "HALLO {{A||FO}} WELT"        # token preserved (fake upper)
        assert res["a"]["text_source"] == "hallo {{a||FO}} welt"  # original kept
        assert res["b"]["caption"] == "EINLEITUNG"
        assert "text_source" not in res["c"]                      # equation untouched


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
           test_field_mapping, test_translate_model_prose_inplace,
           test_translate_tiddler_file_inplace]
    for fn in fns:
        mp = _MP()
        try:
            fn(mp) if fn.__code__.co_argcount else fn(); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(fns)} tests passed.")
