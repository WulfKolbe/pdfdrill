"""
pdfdrill ls — the SHALLOW driller over a folder: run pdfinfo on every PDF (the
cheapest rung), store it in each file's sidecar, and report a compact table led
by the PRODUCER (the tool that made the PDF — the headline triage signal).
Idempotent (size is cached). `--images` adds the pdfimages count.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_format_ls_table_leads_with_producer():
    rows = [
        {"name": "a.pdf", "pages": 12, "mb": 1.2, "text": True,
         "producer": "pdfTeX-1.40.17", "images": None},
        {"name": "scan.pdf", "pages": 3, "mb": 8.0, "text": False,
         "producer": "", "images": None},
    ]
    out = C._format_ls(rows, images=False)
    assert "a.pdf" in out and "scan.pdf" in out
    assert "pdfTeX" in out and "producer" in out.lower()
    assert "no text" in out.lower() or "scan" in out.lower()   # scan flagged


def test_format_ls_with_images_column():
    rows = [{"name": "a.pdf", "pages": 5, "mb": 0.5, "text": True,
             "producer": "iText", "images": 7}]
    out = C._format_ls(rows, images=True)
    assert "7" in out and ("img" in out.lower() or "image" in out.lower())


def test_cmd_ls_scans_every_pdf_and_stores_sidecar(monkeypatch):
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for n, prod in (("paper.pdf", "pdfTeX"), ("book.pdf", "iText"),
                        ("scan.pdf", "")):
            (d / n).write_bytes(b"%PDF-1.4")
        (d / "notes.txt").write_text("ignored")     # non-pdf ignored

        seen = []

        def fake_size(pdf):
            seen.append(pdf.name)
            sc = Sidecar(pdf)
            prod = {"paper.pdf": "pdfTeX", "book.pdf": "iText"}.get(pdf.name, "")
            sc.set_evidence("pages", 10)
            sc.set_evidence("bytes", 1000)
            sc.set_evidence("producer", prod)
            sc.set_evidence("text_layer", pdf.name != "scan.pdf")
            sc.add_fact(C.SIZE_KNOWN)
            sc.save()
            return ""
        monkeypatch.setattr(C, "cmd_size", fake_size)

        out = C.cmd_ls(d)
        assert set(seen) == {"paper.pdf", "book.pdf", "scan.pdf"}   # all pdfs, txt skipped
        assert "paper.pdf" in out and "pdfTeX" in out and "iText" in out
        # producers persisted in each sidecar
        assert Sidecar(d / "paper.pdf").get_evidence("producer") == "pdfTeX"


def test_cmd_ls_empty_and_nondir(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        out = C.cmd_ls(Path(d))
        assert "no pdf" in out.lower()
    assert "not a directory" in C.cmd_ls(Path("/no/such/dir/xyz")).lower()


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
