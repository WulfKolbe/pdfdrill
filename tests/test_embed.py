"""
Test the --embed mode: projectors base64-embed CDN crops at emit time so the
HTML/tiddlers are self-contained. Network is monkeypatched.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors import common
from docops.projectors.formula_report import FormulaReportProjector
from docops.projectors.tiddlywiki import TiddlyWikiProjector


def _fake_fetch(monkey):
    common._embed_cache.clear()

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"\x89PNG\r\n\x1a\nDATA"
        class headers:
            @staticmethod
            def get_content_type(): return "image/png"
    import urllib.request
    monkey.setattr(urllib.request, "urlopen", lambda *a, **k: _R())


def _doc():
    d = Document()
    d.meta["bibkey"] = "DOC"
    d.add(DocObject(type="Equation", props={
        "latex": "x=1", "page": 1, "flow_index": 0,
        "cdn_url": "https://cdn.mathpix.com/cropped/abc.jpg"}))
    return d


def test_report_embed_inlines_image(monkeypatch):
    _fake_fetch(monkeypatch)
    proj = FormulaReportProjector(OperatorConfig(
        op="projector", classname="FormulaReportProjector", params={"embed": True}))
    h = proj.project(_doc())
    assert "data:image/png;base64," in h
    # The <img src> is the inlined data URI, not the crop URL …
    assert 'src="data:image/png;base64,' in h
    assert 'src="https://cdn.mathpix.com/cropped/abc.jpg"' not in h
    # … but the crop links to its full page (page_url == the crop URL here,
    # since the synthetic crop has no region query), kept live under --embed.
    assert '<a href="https://cdn.mathpix.com/cropped/abc.jpg"' in h


def test_report_default_keeps_url(monkeypatch):
    _fake_fetch(monkeypatch)
    proj = FormulaReportProjector(OperatorConfig(
        op="projector", classname="FormulaReportProjector"))
    h = proj.project(_doc())
    assert "cdn.mathpix.com/cropped/abc.jpg" in h          # URL kept
    assert "data:image/png" not in h


def test_tiddlers_embed_inlines_canonical_uri(monkeypatch):
    _fake_fetch(monkeypatch)
    proj = TiddlyWikiProjector(OperatorConfig(
        op="projector", classname="TiddlyWikiProjector", params={"embed": True}))
    tids = json.loads(proj.project(_doc()))
    eq = [t for t in tids if "equation" in t.get("tags", "")][0]
    assert eq["canonical_uri"].startswith("data:image/png;base64,")


def test_embed_fetch_failure_falls_back_to_url(monkeypatch):
    common._embed_cache.clear()
    import urllib.request
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert common.embed_image("https://x/y.jpg") == "https://x/y.jpg"


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        mp = _MP()
        try:
            if "monkeypatch" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                fn(mp)
            else:
                fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
        finally:
            mp.undo()
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
