"""
Tests for the MathPix-free tesseract OCR input path (pdfdrill.ocr_lines +
cmd_ocr).

The subprocess part (pdftoppm + tesseract) isn't exercised here; instead the
pure assembler `lines_json_from_words` is fed synthetic parsed-TSV words, and
the result is run through the real docmodel converter to prove it is
MathPix-compatible. cmd_ocr's guards (refuse to clobber a MathPix lines.json,
graceful when tools are missing) are checked with a temp dir.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import ocr_lines
from pdfdrill.commands import cmd_ocr


def _words():
    # Two lines on page 1, one on page 2 (geometry.parse_tsv word shape).
    return [
        {"page": 1, "block": 1, "line": 1, "x0": 10, "y0": 10, "x1": 50, "y1": 22, "text": "Hello"},
        {"page": 1, "block": 1, "line": 1, "x0": 55, "y0": 10, "x1": 95, "y1": 22, "text": "world"},
        {"page": 1, "block": 1, "line": 2, "x0": 10, "y0": 30, "x1": 70, "y1": 42, "text": "Second"},
        {"page": 2, "block": 1, "line": 1, "x0": 10, "y0": 10, "x1": 60, "y1": 22, "text": "Page2"},
    ]


def test_lines_json_from_words_shape():
    lj = ocr_lines.lines_json_from_words(_words(), {1: (600, 800), 2: (600, 800)})
    assert lj["source"] == "tesseract"
    assert [p["page"] for p in lj["pages"]] == [1, 2]
    p1 = lj["pages"][0]
    assert p1["page_width"] == 600 and p1["page_height"] == 800
    assert p1["image_id"] is None
    # Two words on the same (block,line) merged into one line, x-sorted.
    assert p1["lines"][0]["text"] == "Hello world"
    assert p1["lines"][0]["type"] == "text"
    r = p1["lines"][0]["region"]
    assert r["top_left_x"] == 10 and r["top_left_y"] == 10
    assert r["width"] == 85 and r["height"] == 12
    assert len(p1["lines"]) == 2
    assert lj["pages"][1]["lines"][0]["text"] == "Page2"


def test_blank_page_still_listed():
    # page_dims has a page with no words -> still appears (blank).
    lj = ocr_lines.lines_json_from_words(
        [{"page": 1, "block": 1, "line": 1, "x0": 1, "y0": 1, "x1": 9, "y1": 9, "text": "x"}],
        {1: (100, 100), 2: (100, 100)},
    )
    assert [p["page"] for p in lj["pages"]] == [1, 2]
    assert lj["pages"][1]["lines"] == []


def test_lines_json_feeds_the_docmodel():
    """The OCR lines.json must build a model exactly like a MathPix one."""
    from docmodel.core import Document
    from docmodel.main import ingest_lines_json, load_config, load_modules, DEFAULT_CONFIG_PATH

    lj = ocr_lines.lines_json_from_words(_words(), {1: (600, 800), 2: (600, 800)})
    doc = Document()
    ingest_lines_json(doc, lj)
    for mod in load_modules(load_config(DEFAULT_CONFIG_PATH), bibkey="T"):
        mod.process_document(doc)
    pages = doc.objects_of_type("Page")
    paras = doc.objects_of_type("Paragraph")
    assert len(pages) == 2
    assert len(paras) >= 1            # text lines became prose
    assert any("Hello world" in (p.props.get("text") or "") for p in paras)


def test_cmd_ocr_refuses_to_clobber_mathpix():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        # A MathPix-style lines.json (no "source" key) next to it.
        (Path(d) / "doc.lines.json").write_text(json.dumps({"pages": []}))
        out = cmd_ocr(pdf)
        assert "Refusing to overwrite" in out


def test_cmd_ocr_graceful_when_tools_missing(monkeypatch):
    monkeypatch.setattr(ocr_lines, "tools_available", lambda: (False, "no tesseract here"))
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        out = cmd_ocr(pdf)
        assert out == "no tesseract here"


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    fns = [test_lines_json_from_words_shape, test_blank_page_still_listed,
           test_lines_json_feeds_the_docmodel, test_cmd_ocr_refuses_to_clobber_mathpix]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    mp = _MP()
    try:
        test_cmd_ocr_graceful_when_tools_missing(mp); print("PASS test_cmd_ocr_graceful_when_tools_missing")
    finally:
        mp.undo()
    print(f"\nAll {len(fns) + 1} tests passed.")
