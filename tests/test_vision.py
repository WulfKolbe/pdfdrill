"""
Tests for the OpenAI GPT-4o vision path (pdfdrill.openai_vision + cmd_vision).

No real API call: `openai_vision.analyze_image` is monkeypatched with a fake,
and `available` is forced. Covers crop collection (incl. CDN links embedded in
a table cell with LaTeX-escaped `\\&`), the selector→latex mapping, cmd_vision
wiring/persistence, and the graceful no-key path.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.sidecar import Sidecar
from pdfdrill import openai_vision
from pdfdrill import commands
from pdfdrill.commands import (
    cmd_vision, MODEL_BUILT, VISION_DONE, _collect_cdn_crops, _norm_crop_url,
)


_CDN = "https://cdn.mathpix.com/cropped/abc-20.jpg?height=821&width=1754&top_left_y=1564&top_left_x=255"


def test_result_to_latex_mapping():
    assert openai_vision.result_to_latex({"selector": "math", "math": "$$E=mc^2$$"}) == ("math", "E=mc^2")
    assert openai_vision.result_to_latex(
        {"selector": "tikzpicture", "tikzpicture": "\\begin{tikzpicture}\\end{tikzpicture}"}
    ) == ("tikzpicture", "\\begin{tikzpicture}\\end{tikzpicture}")
    assert openai_vision.result_to_latex({"selector": "table", "table": "\\begin{tabular}{ll}a&b\\end{tabular}"})[0] == "table"
    assert openai_vision.result_to_latex({"selector": "empty"}) == ("empty", "")


def _doc():
    doc = Document()
    doc.add(DocObject(type="Equation", props={"cdn_url": _CDN, "latex": "x"}))
    doc.add(DocObject(type="Picture", props={"url": _CDN.replace("-20", "-07")}))
    # A table with a CDN link embedded in a cell, LaTeX-escaped `\&`.
    cell = "\\begin{tabular}{l}![](" + _CDN.replace("-20", "-27").replace("&", "\\&") + ")\\end{tabular}"
    doc.add(DocObject(type="Table", props={"raw_text": cell}))
    return doc


def test_collect_cdn_crops_finds_embedded_table_crop():
    crops = _collect_cdn_crops(_doc())
    urls = {u for _o, u in crops}
    assert any(u.endswith("-20.jpg?height=821&width=1754&top_left_y=1564&top_left_x=255") for u in urls)
    assert any("-07.jpg" in u for u in urls)
    # The table-embedded crop is recovered with `\&` un-escaped to `&`.
    assert any("-27.jpg" in u and "\\&" not in u and "&" in u for u in urls)
    assert len(crops) == 3


def test_norm_crop_url_cleans_and_validates():
    # LaTeX-escaped `\&` (as MathPix leaves it in table cells) -> unescaped.
    dirty = "https://cdn.mathpix.com/cropped/abc-07.jpg?height=53\\&width=613\\&top_left_y=1\\&top_left_x=2"
    clean = _norm_crop_url(dirty)
    assert clean == "https://cdn.mathpix.com/cropped/abc-07.jpg?height=53&width=613&top_left_y=1&top_left_x=2"
    # Trailing punctuation trimmed.
    assert _norm_crop_url(_CDN + ").") == _CDN
    # Garbage (a cnt-array fragment) and truncated links are rejected.
    assert _norm_crop_url("0,54,3,70,5,102,cdn.mathpix.com/cropped") is None
    assert _norm_crop_url("https://cdn.mathpix.com/cropped/abc-07.jpg?height=53") is None  # missing fields
    assert _norm_crop_url("") is None


class _FakeVision:
    """Stand-in for openai_vision.analyze_image — returns a math result."""
    @staticmethod
    def analyze_image(url, **kw):
        return {"selector": "math", "math": "$$a+b$$", "gnuplot": "", "csv_data": ""}


def _make_model(tmp: Path) -> Path:
    pdf = tmp / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(_doc().to_dict()), encoding="utf-8")
    sc.add_fact(MODEL_BUILT)
    sc.save()
    return pdf


def test_cmd_vision_attaches_openai_provenance(monkeypatch):
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    monkeypatch.setattr(commands.__dict__.get("openai_vision", openai_vision), "analyze_image",
                        _FakeVision.analyze_image, raising=False)
    # cmd_vision does `from . import openai_vision`, so patch the module itself.
    monkeypatch.setattr(openai_vision, "analyze_image", _FakeVision.analyze_image)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf)
        assert "read 3 CDN crop" in out and "math" in out
        model = json.loads((Path(d) / "doc.pdf.drill" / "model.docmodel.json").read_text())
        objs = model["objects"] if isinstance(model["objects"], list) else list(model["objects"].values())
        oai = [r for o in objs for r in o.get("realizations", [])
               if r.get("provenance") == "openai"]
        assert len(oai) == 3
        assert oai[0]["props"]["selector"] == "math"
        assert oai[0]["props"]["latex"] == "a+b"
        assert Sidecar(pdf).has(VISION_DONE)


def test_cmd_vision_limit(monkeypatch):
    monkeypatch.setattr(openai_vision, "available", lambda: True)
    monkeypatch.setattr(openai_vision, "analyze_image", _FakeVision.analyze_image)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf, limit=1)
        assert "read 1 CDN crop" in out
        assert "not yet read" in out


def test_cmd_vision_graceful_without_key(monkeypatch):
    monkeypatch.setattr(openai_vision, "available", lambda: False)
    with tempfile.TemporaryDirectory() as d:
        pdf = _make_model(Path(d))
        out = cmd_vision(pdf)
        assert "OPENAI_API_KEY" in out
        assert not Sidecar(pdf).has(VISION_DONE)


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v, raising=True): self._u.append((o, n, getattr(o, n, None))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    plain = [test_result_to_latex_mapping, test_collect_cdn_crops_finds_embedded_table_crop]
    mpd = [test_cmd_vision_attaches_openai_provenance, test_cmd_vision_limit,
           test_cmd_vision_graceful_without_key]
    for fn in plain:
        fn(); print(f"PASS {fn.__name__}")
    for fn in mpd:
        mp = _MP()
        try:
            fn(mp); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print(f"\nAll {len(plain) + len(mpd)} tests passed.")
