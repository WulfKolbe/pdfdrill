"""
Tests for the text-layer / OCR-mandatory detection in `pdfdrill size`
(_probe_text_layer + _format_size). Subprocess calls (pdffonts/pdftotext) are
monkeypatched so no real PDF is needed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands
from pdfdrill.sidecar import Sidecar


class _Run:
    def __init__(self, stdout): self.stdout = stdout


def _patch(monkeypatch, *, fonts_rows: int, page1_text: str):
    """Fake pdffonts (header + N rows) and pdftotext (page-1 text)."""
    header = "name type enc emb sub uni id\n---- ---- --- --- --- --- --\n"
    fonts_out = header + "".join(f"F{i} Type1 x y z w {i}\n" for i in range(fonts_rows))

    def fake_run(cmd, **kw):
        if cmd[0] == "pdffonts":
            return _Run(fonts_out)
        if cmd[0] == "pdftotext":
            return _Run(page1_text)
        return _Run("")
    monkeypatch.setattr(commands.subprocess, "run", fake_run)


def test_scan_no_text_no_fonts_needs_ocr(monkeypatch):
    _patch(monkeypatch, fonts_rows=0, page1_text="\n \n")
    has, nf, nc = commands._probe_text_layer(Path("scan.pdf"))
    assert has is False and nf == 0 and nc == 0


def test_born_digital_has_text(monkeypatch):
    _patch(monkeypatch, fonts_rows=12, page1_text="Abstract. We introduce ...")
    has, nf, nc = commands._probe_text_layer(Path("paper.pdf"))
    assert has is True and nf == 12 and nc > 4


def test_image_pdf_with_stray_stamp_font_still_needs_ocr(monkeypatch):
    # a scan that carries 1 font (a stamp) but no extractable text -> still OCR
    _patch(monkeypatch, fonts_rows=1, page1_text="   ")
    has, nf, nc = commands._probe_text_layer(Path("stamped_scan.pdf"))
    assert has is False and nf == 1 and nc == 0


def test_format_size_messages():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # scanned
        sc = Sidecar(Path(d) / "scan.pdf")
        sc.set_evidence("pages", 1); sc.set_evidence("bytes", 40_000_000)
        sc.set_evidence("producer", "pdf-lib"); sc.set_evidence("text_layer", False)
        msg = commands._format_size(sc)
        assert "NO text layer" in msg and "OCR required" in msg
        # born-digital
        sc2 = Sidecar(Path(d) / "ok.pdf")
        sc2.set_evidence("pages", 10); sc2.set_evidence("bytes", 1_000_000)
        sc2.set_evidence("producer", "pdfTeX"); sc2.set_evidence("text_layer", True)
        assert "has a text layer" in commands._format_size(sc2)


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
