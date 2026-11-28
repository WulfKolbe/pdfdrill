r"""`pdfdrill glyphlines --only lines` writes lines.json alone (board 122).

The board's loop is PDF -> lines.json -> render -> judge; the reader's own
.glyphs.md and .glyphs.tex are not in it. The option skips them, and the
lines.json is byte-identical to the default's because it is written before
the projections. The default still writes all three.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("pdfreader.docmodel_six")
from pdfdrill import commands as C  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"
_REAL_PROJECTIONS = C._glyph_projections


def _run(tmp_path, monkeypatch, only):
    calls = []

    def counting(*a, **k):
        calls.append(1)
        return _REAL_PROJECTIONS(*a, **k)
    monkeypatch.setattr(C, "_glyph_projections", counting)
    pdf = tmp_path / "r00.pdf"
    shutil.copy(FIX, pdf)
    C.cmd_glyphlines(pdf, only_lines=only)
    return pdf, calls


def test_only_lines_skips_the_projections_and_keeps_lines_json(tmp_path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    pdf_only, calls_only = _run(a, monkeypatch, True)
    pdf_dflt, calls_dflt = _run(b, monkeypatch, False)
    assert calls_only == [] and calls_dflt == [1]
    lj_only = pdf_only.with_suffix(".lines.json")
    lj_dflt = pdf_dflt.with_suffix(".lines.json")
    assert lj_only.read_bytes() == lj_dflt.read_bytes()
    assert not list(a.glob("*.glyphs.*"))


def test_only_takes_lines_and_nothing_else():
    from pdfdrill import cli
    with pytest.raises(ValueError, match="only choice is `lines`"):
        cli._do_glyphlines(["--only", "md", str(FIX)])


def test_only_lines_skips_the_probes_and_the_default_runs_them(tmp_path, monkeypatch):
    from pdfdrill import cli, probes
    called = []
    monkeypatch.setattr(probes, "ensure", lambda *a, **k: called.append(1))
    monkeypatch.setattr(cli, "_SKIP_PROBES", True)
    pdf = tmp_path / "r00.pdf"
    shutil.copy(FIX, pdf)
    cli._probe_on_acquire(pdf)
    assert called == []
    monkeypatch.setattr(cli, "_SKIP_PROBES", False)
    pdf2 = tmp_path / "again" / "r00.pdf"
    pdf2.parent.mkdir()
    shutil.copy(FIX, pdf2)
    cli._probe_on_acquire(pdf2)
    assert called == [1]
