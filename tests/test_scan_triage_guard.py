"""
Scan-triage commands (continuity / ordered / autosegment) do full-page OCR to
segment a SCANNED multi-document bundle. The sandbox test found they don't
short-circuit on a BORN-DIGITAL doc — they OCR every page and time out. The
guard returns a clear message (skip the OCR) when the doc has a text layer.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill.sidecar import Sidecar


def _pdf_with_text_layer(d, value):
    pdf = Path(d) / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    sc.set_evidence("text_layer", value)
    sc.add_fact(C.SIZE_KNOWN)
    sc.save()
    return pdf


def test_guard_blocks_born_digital():
    with tempfile.TemporaryDirectory() as d:
        pdf = _pdf_with_text_layer(d, True)
        msg = C._born_digital_scan_guard(pdf, "autosegment")
        assert msg is not None
        assert "born-digital" in msg.lower() and "autosegment" in msg


def test_guard_allows_scan():
    with tempfile.TemporaryDirectory() as d:
        pdf = _pdf_with_text_layer(d, False)          # a scan → no guard
        assert C._born_digital_scan_guard(pdf, "ordered") is None


def test_autosegment_short_circuits_born_digital(monkeypatch):
    """cmd_autosegment must return the guard message WITHOUT calling per-page OCR
    on a born-digital doc."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _pdf_with_text_layer(d, True)
        called = []
        monkeypatch.setattr(C, "_per_page_ocr_text",
                            lambda *a, **k: called.append(1) or {})
        out = C.cmd_autosegment(pdf)
        assert not called                              # OCR never ran
        assert "born-digital" in out.lower()


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
