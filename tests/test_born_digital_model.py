"""
Finding B (sandbox test): `route` promises "born-digital → text-layer (free)"
but cmd_model had NO born-digital route — MathPix (needs key) → arXiv-source
(arXiv only) → slow/lossy tesseract OCR. pdfdrill already ships chars_to_lines
(pdfplumber text layer → lines.json); cmd_model must use it for a born-digital
doc before tesseract, so a keyless born-digital PDF builds free and fast.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def _dump(nchars):
    """A pdfplumber-shape char dump with `nchars` chars on one page."""
    chars = [{"x0": 10 + i, "x1": 15 + i, "y0": 700, "y1": 712, "text": "x"}
             for i in range(nchars)]
    return {"source": "pdfplumber-chars", "total_pages": 1,
            "pages": [{"page_number": 1, "width": 612, "height": 792, "chars": chars}]}


def test_write_born_digital_lines_from_text_layer(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        monkeypatch.setattr(C, "_pdfplumber_char_dump", lambda p: _dump(200))
        assert C._write_born_digital_lines(pdf) is True
        lj = C._lines_json_path(pdf)
        assert lj.exists()
        data = json.loads(lj.read_text())
        assert data["source"] == "pdfplumber-chars"
        assert data["pages"] and data["pages"][0]["lines"]


def test_born_digital_dump_prefers_pdfminer(monkeypatch):
    """pdfminer.six is the born-digital engine now (it replaced pdfplumber). When
    available, `_born_digital_char_dump` uses it; pdfplumber is only the fallback."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
        miner = {"source": "pdfminer-chars", "total_pages": 1,
                 "pages": [{"page_number": 1, "width": 612, "height": 792,
                            "chars": [{"x0": 1, "x1": 2, "y0": 700, "y1": 712,
                                       "text": "a"}]}]}
        monkeypatch.setattr(C, "_pdfminer_char_dump", lambda p: miner)
        monkeypatch.setattr(C, "_pdfplumber_char_dump",
                            lambda p: (_ for _ in ()).throw(AssertionError("pdfplumber used")))
        assert C._born_digital_char_dump(pdf)["source"] == "pdfminer-chars"


def test_born_digital_dump_falls_back_to_pdfplumber(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
        monkeypatch.setattr(C, "_pdfminer_char_dump",
                            lambda p: (_ for _ in ()).throw(RuntimeError("no pdfminer")))
        monkeypatch.setattr(C, "_pdfplumber_char_dump", lambda p: _dump(5))
        assert C._born_digital_char_dump(pdf)["source"] == "pdfplumber-chars"


def test_write_born_digital_lines_false_when_no_text_layer(monkeypatch):
    """A scan (pdfplumber finds ~no chars) → False, so cmd_model falls to OCR."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "scan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        monkeypatch.setattr(C, "_pdfplumber_char_dump", lambda p: _dump(0))
        assert C._write_born_digital_lines(pdf) is False
        assert not C._lines_json_path(pdf).exists()


def test_write_born_digital_lines_false_on_pdfplumber_error(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        def boom(p): raise RuntimeError("pdfplumber failed")
        monkeypatch.setattr(C, "_pdfplumber_char_dump", boom)
        assert C._write_born_digital_lines(pdf) is False


def test_born_digital_source_triggers_math_gate():
    """The NEEDS_VISION_OCR math gate must treat pdfplumber-chars like tesseract
    (both are keyless TEXT-only builds that can't type equations)."""
    assert C._is_keyless_textonly_source("tesseract") is True
    assert C._is_keyless_textonly_source("pdfplumber-chars") is True
    assert C._is_keyless_textonly_source("mathpix") is False


if __name__ == "__main__":
    import inspect
    class MP:
        def setattr(self, o, n, v): setattr(o, n, v)
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(MP()) if inspect.signature(t).parameters else t()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")


def test_cmd_model_prefers_born_digital_over_arxiv_source(monkeypatch, tmp_path):
    """The no-OCR default: a born-digital doc builds via the pdfplumber text
    stream (geometry) — the arXiv LaTeX source (no geometry) is NOT the base, so
    inspect/locate work without a MathPix key. Order: mathpix → born-digital →
    (scan only) source/ocr."""
    import json
    from pdfdrill import commands as C
    from docmodel.core import Document, DocObject
    pdf = tmp_path / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
    called = []
    monkeypatch.setattr(C, "cmd_mathpix", lambda p: called.append("mathpix"))
    monkeypatch.setattr(C, "_build_arxiv_source_model",
                        lambda *a, **k: (called.append("arxiv_source"), "src")[1])

    def bd(p):
        called.append("born_digital")
        C._lines_json_path(p).write_text("{}")   # presence suffices; build mocked
        return True
    monkeypatch.setattr(C, "_write_born_digital_lines", bd)

    def fake_run(**k):
        doc = Document(); doc.meta["bibkey"] = k.get("bibkey", "x")
        doc.add(DocObject(type="Page", props={"page": 1}))
        doc.meta["pages"] = [{"page": 1}]
        d = doc.to_dict(); json.dump(d, open(k["out_path"], "w")); return d
    monkeypatch.setattr("docmodel.main.run", fake_run)

    C.cmd_model(pdf)
    assert "born_digital" in called          # the pdfplumber route was used
    assert "arxiv_source" not in called      # source is NOT the born-digital base


def test_cmd_model_auto_merges_latex_for_arxiv_born_digital(monkeypatch, tmp_path):
    """The merge is AUTOMATIC: a born-digital arXiv doc (pdfminer geometry) also
    gets the e-print's gold LaTeX overlaid — pdfdrill extracts AND merges."""
    import json
    from pdfdrill import commands as C
    from docmodel.core import Document, DocObject
    pdf = tmp_path / "2502.20855v2.pdf"; pdf.write_bytes(b"%PDF-1.4")
    called = []
    monkeypatch.setattr(C, "cmd_mathpix", lambda p: None)
    monkeypatch.setattr(C, "_build_arxiv_source_model", lambda *a, **k: None)
    monkeypatch.setattr(C, "_arxiv_id_for", lambda p, sc: "2502.20855v2")
    monkeypatch.setattr(C, "cmd_injectlatex", lambda p: called.append("latex"))

    def bd(p):
        C._lines_json_path(p).write_text('{"source":"pdfplumber-chars"}')
        return True
    monkeypatch.setattr(C, "_write_born_digital_lines", bd)

    def fake_run(**k):
        doc = Document(); doc.meta["bibkey"] = k.get("bibkey", "x")
        doc.add(DocObject(type="Page", props={"page": 1})); doc.meta["pages"] = [{"page": 1}]
        d = doc.to_dict(); json.dump(d, open(k["out_path"], "w")); return d
    monkeypatch.setattr("docmodel.main.run", fake_run)

    C.cmd_model(pdf)
    assert "latex" in called            # gold LaTeX auto-overlaid onto the pdfminer base


def test_cmd_model_no_latex_merge_for_non_arxiv(monkeypatch, tmp_path):
    """A non-arXiv born-digital doc has no e-print — pdfminer only, no merge call."""
    import json
    from pdfdrill import commands as C
    from docmodel.core import Document, DocObject
    pdf = tmp_path / "local.pdf"; pdf.write_bytes(b"%PDF-1.4")
    called = []
    monkeypatch.setattr(C, "cmd_mathpix", lambda p: None)
    monkeypatch.setattr(C, "_arxiv_id_for", lambda p, sc: None)   # not arXiv
    monkeypatch.setattr(C, "cmd_injectlatex", lambda p: called.append("latex"))
    monkeypatch.setattr(C, "_write_born_digital_lines",
                        lambda p: (C._lines_json_path(p).write_text('{"source":"pdfplumber-chars"}'), True)[1])

    def fake_run(**k):
        doc = Document(); doc.meta["bibkey"] = "x"
        doc.add(DocObject(type="Page", props={"page": 1})); doc.meta["pages"] = [{"page": 1}]
        d = doc.to_dict(); json.dump(d, open(k["out_path"], "w")); return d
    monkeypatch.setattr("docmodel.main.run", fake_run)

    C.cmd_model(pdf)
    assert "latex" not in called        # no e-print → no merge
