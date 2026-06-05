"""
arXiv free-route wiring (no real network — fetch is monkeypatched):
  * cmd_mathpix SKIPS the paid upload for an arXiv input and points at the free
    routes (so `model` falls back to keyless OCR), unless --force.
  * cmd_abstract answers from the arXiv abs page (method "arxiv-abs-page") with no
    MathPix and no text-layer dependency.
The arXiv id is taken from the filename stem here (a downloaded <id>.pdf).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _arxiv_pdf(d: Path) -> Path:
    from pypdf import PdfWriter
    p = d / "2510.11170v2.pdf"          # stem IS the arxiv id
    w = PdfWriter(); w.add_blank_page(width=300, height=300)
    with open(p, "wb") as f:
        w.write(f)
    return p


def test_cmd_mathpix_skips_for_arxiv():
    from pdfdrill import commands
    with tempfile.TemporaryDirectory() as dd:
        pdf = _arxiv_pdf(Path(dd))
        out = commands.cmd_mathpix(pdf)
    assert "skipped" in out.lower() and "arXiv:2510.11170v2" in out
    assert "FREE" in out and "--force" in out


def test_cmd_abstract_uses_free_arxiv_route(monkeypatch):
    from pdfdrill import commands, sources
    monkeypatch.setattr(sources, "fetch_arxiv_metadata", lambda aid: {
        "arxiv_id": aid, "title": "EAGer", "authors": ["A", "B"],
        "abstract": "With the rise of reasoning language models, compute matters.",
        "primary_category": "cs.LG"})
    with tempfile.TemporaryDirectory() as dd:
        pdf = _arxiv_pdf(Path(dd))
        out = commands.cmd_abstract(pdf)
    assert "arxiv-abs-page" in out
    assert "reasoning language models" in out


if __name__ == "__main__":
    test_cmd_mathpix_skips_for_arxiv(); print("PASS mathpix-skip")

    class _MP:
        def setattr(self, o, n, v): setattr(o, n, v)
    test_cmd_abstract_uses_free_arxiv_route(_MP()); print("PASS abstract-route")
    print("\nAll tests passed.")
