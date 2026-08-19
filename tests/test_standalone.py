"""P14 — standalone: each display equation compiled as its own document.

A formula that will not compile alone is already a finding, so failures are
reported with their identifiers, never silently dropped.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_standalone
from pdfdrill.sidecar import Sidecar


def _doc(tmp, tiddlers):
    pdf = Path(tmp) / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (Path(tmp) / "doc.tiddlers.json").write_text(json.dumps(tiddlers))
    return pdf


def test_standalone_renders_skips_and_reports_failures():
    if shutil.which("xelatex") is None or shutil.which("gs") is None:
        # bootstrap.sh installs both; without them the command reports, so
        # assert THAT contract instead of silently passing
        with tempfile.TemporaryDirectory() as d:
            out = cmd_standalone(_doc(d, []))
            assert "not installed" in out
        return
    tiddlers = [
        {"title": "doc_EQ0001", "latex": "a = b + c"},
        {"title": "doc_EQ0002", "latex": r"\frac{x}{y} = \alpha"},
        # unbalanced brace: cannot compile alone -> must be REPORTED
        {"title": "doc_EQ0003", "latex": r"\frac{x}{y"},
        {"title": "doc_FO0001", "latex": "ignored (not an EQ)"},
    ]
    with tempfile.TemporaryDirectory() as d:
        pdf = _doc(d, tiddlers)
        out = cmd_standalone(pdf)
        sa = Sidecar(pdf).blob_dir / "standalone"
        assert (sa / "doc_EQ0001.png").is_file()
        assert (sa / "doc_EQ0002.png").is_file()
        assert not (sa / "doc_EQ0003.png").exists()
        assert "2 equation(s) rendered" in out
        assert "doc_EQ0003" in out                    # the finding, by id
        assert "doc_EQ0003" in (sa / "_failures.txt").read_text()
        # no scratch left behind for successes
        assert not list(sa.glob("*.tex")) or (sa / "doc_EQ0003.tex").exists()

        out2 = cmd_standalone(pdf)                    # idempotent skip
        assert "2 already rendered, skipped" in out2

        out3 = cmd_standalone(pdf, only_id="doc_EQ0001")   # --id re-renders
        assert "1 equation(s) rendered" in out3
