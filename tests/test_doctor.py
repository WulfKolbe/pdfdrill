"""
Tests for `pdfdrill doctor` (requirement check) — system tools, the apt-get fix
line, and the LaTeX/dvisvgm support-set expansion.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_doctor


def test_doctor_all_present(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda t: "/usr/bin/" + t)
    out = cmd_doctor()
    assert "All system tools present" in out
    assert "apt-get install" not in out


def test_doctor_missing_latex_svg_expands_support_set(monkeypatch):
    # Everything present except latex + dvisvgm (the SVG route).
    present = {"pdftotext", "pdfimages", "pdftoppm", "pdfinfo", "tesseract",
               "pdflatex", "dvips"}
    monkeypatch.setattr(shutil, "which", lambda t: ("/usr/bin/" + t) if t in present else None)
    out = cmd_doctor()
    assert "[MISSING] latex" in out and "[MISSING] dvisvgm" in out
    fix = [l for l in out.splitlines() if l.strip().startswith("sudo apt-get install")][0]
    # The full LaTeX/SVG support set is offered, not just one package.
    for pkg in ("dvisvgm", "texlive-latex-base", "texlive-latex-extra",
                "texlive-pictures", "texlive-fonts-recommended"):
        assert pkg in fix


def test_doctor_missing_poppler(monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        lambda t: None if t.startswith("pdf") else "/usr/bin/" + t)
    out = cmd_doctor()
    assert "poppler-utils" in out
    assert "[MISSING] pdftotext" in out


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def undo(self):
            for o, n, v in reversed(self._u): setattr(o, n, v)
            self._u = []
    for fn in [test_doctor_all_present, test_doctor_missing_latex_svg_expands_support_set,
               test_doctor_missing_poppler]:
        mp = _MP()
        try:
            fn(mp); print(f"PASS {fn.__name__}")
        finally:
            mp.undo()
    print("\nAll tests passed.")
