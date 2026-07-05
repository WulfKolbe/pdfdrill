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
