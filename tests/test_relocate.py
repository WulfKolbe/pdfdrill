"""
`pdfdrill relocate` — migrate legacy scattered drills into the self-contained
library layout: <library>/<stem>/ holding the PDF + every X.* sibling + the
flattened X.pdf.drill/ contents. Pure planner tested here; apply is a shutil.move
loop. See docs/superpowers/specs/2026-07-14-self-contained-doc-folders.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import relocate as R


def _legacy_doc(d: Path, stem="2502.20855v2"):
    """Create a legacy scattered doc under d and return its pdf path."""
    pdf = d / f"{stem}.pdf"; pdf.write_bytes(b"%PDF-1.4")
    (d / f"{stem}.lines.json").write_text("{}")
    (d / f"{stem}.tex.zip").write_bytes(b"zip")
    (d / f"{stem}.pdf.drill.json").write_text("{}")        # sidecar state
    blob = d / f"{stem}.pdf.drill"; blob.mkdir()
    (blob / "model.docmodel.json").write_text("{}")
    (blob / f"{stem}.tiddlers.json").write_text("[]")
    (blob / "texsrc").mkdir()
    (blob / "texsrc" / "main.tex").write_text("x")
    return pdf


def test_plan_relocation_moves_pdf_siblings_and_blob(tmp_path):
    d = tmp_path / "Downloads"; d.mkdir()
    lib = tmp_path / "library"
    pdf = _legacy_doc(d)
    moves = R.plan_relocation(pdf, lib)
    dsts = {str(dst.relative_to(lib)) for _src, dst in moves}
    # PDF + loose siblings land in <stem>/ ; sidecar renamed; blob flattened
    assert "2502.20855v2/2502.20855v2.pdf" in dsts
    assert "2502.20855v2/2502.20855v2.lines.json" in dsts
    assert "2502.20855v2/2502.20855v2.tex.zip" in dsts
    assert "2502.20855v2/2502.20855v2.drill.json" in dsts          # renamed from .pdf.drill.json
    assert "2502.20855v2/model.docmodel.json" in dsts             # blob flattened
    assert "2502.20855v2/2502.20855v2.tiddlers.json" in dsts
    assert "2502.20855v2/texsrc" in dsts                          # subdir moved whole
    # the .pdf.drill dir itself is NOT a move target (only its contents)
    assert not any(str(dst).endswith(".pdf.drill") for _s, dst in moves)


def test_plan_relocation_already_migrated_is_noop(tmp_path):
    lib = tmp_path / "library"
    folder = lib / "2502.20855v2"; folder.mkdir(parents=True)
    pdf = folder / "2502.20855v2.pdf"; pdf.write_bytes(b"%PDF-1.4")
    assert R.plan_relocation(pdf, lib) == []


def test_apply_relocation_moves_files_and_reads_work(tmp_path):
    d = tmp_path / "Downloads"; d.mkdir()
    lib = tmp_path / "library"
    pdf = _legacy_doc(d)
    moved, skipped = R.apply_relocation(pdf, lib)
    assert moved > 0 and skipped == 0
    newpdf = lib / "2502.20855v2" / "2502.20855v2.pdf"
    assert newpdf.exists()
    assert (lib / "2502.20855v2" / "model.docmodel.json").exists()
    assert (lib / "2502.20855v2" / "texsrc" / "main.tex").exists()
    assert not pdf.exists()                                       # moved, not copied
    # the Sidecar now resolves to the self-contained folder
    from pdfdrill.sidecar import Sidecar
    sc = Sidecar(newpdf)
    assert sc.blob_dir == lib / "2502.20855v2"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
