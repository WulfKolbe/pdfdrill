"""
Self-contained document folders: a doc folder named after its PDF holds the PDF
AND all artifacts (blob_dir = pdf.parent). A legacy sibling `<name>.pdf.drill/`
still works (back-compat); an ad-hoc PDF (parent not named after it, no sibling)
gets a sibling `.drill` as before. See
docs/superpowers/specs/2026-07-14-self-contained-doc-folders.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.sidecar import Sidecar


def test_self_contained_doc_folder(tmp_path):
    # <root>/2502.20855v2/2502.20855v2.pdf  ->  blob_dir is the folder itself
    folder = tmp_path / "2502.20855v2"
    folder.mkdir()
    pdf = folder / "2502.20855v2.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    assert sc.blob_dir == folder
    assert sc.json_path == folder / "2502.20855v2.drill.json"


def test_legacy_sibling_layout_still_works(tmp_path):
    # <dir>/X.pdf with an existing X.pdf.drill/  ->  use the sibling (back-compat)
    d = tmp_path / "Downloads"
    d.mkdir()
    pdf = d / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    (d / "paper.pdf.drill").mkdir()
    sc = Sidecar(pdf)
    assert sc.blob_dir == d / "paper.pdf.drill"
    assert sc.json_path == d / "paper.pdf.drill.json"


def test_ad_hoc_pdf_gets_sibling_drill(tmp_path):
    # a one-off PDF whose parent is NOT named after it and has no .drill  ->
    # sibling .drill (unchanged default; artifacts don't pollute the folder)
    d = tmp_path / "scratch"
    d.mkdir()
    pdf = d / "random.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    assert sc.blob_dir == d / "random.pdf.drill"
    assert sc.json_path == d / "random.pdf.drill.json"


def test_stray_legacy_dir_does_not_flip_self_contained(tmp_path):
    """A self-contained doc with a SELF sidecar (`<stem>.drill.json`) stays
    self-contained even if a stray `<name>.pdf.drill/` appears inside its folder
    (an old hardcoded-legacy-path bug created one → the whole doc flipped to
    legacy and `md`/artifacts split into `<name>.pdf.drill/`)."""
    folder = tmp_path / "Zwiebeln"; folder.mkdir()
    pdf = folder / "Zwiebeln.pdf"; pdf.write_bytes(b"%PDF-1.4")
    Sidecar(pdf).save()                                     # writes Zwiebeln.drill.json
    (folder / "Zwiebeln.pdf.drill").mkdir()                 # a stray legacy dir
    sc = Sidecar(pdf)
    assert sc.blob_dir == folder                            # NOT flipped to legacy
    assert sc.json_path == folder / "Zwiebeln.drill.json"


def test_genuine_pre_selfcontained_legacy_wins(tmp_path):
    """A doc at `<stem>/<stem>.pdf` drilled BEFORE self-contained folders (a legacy
    `.drill.json`/`.drill/` and NO self sidecar) keeps using the legacy store."""
    folder = tmp_path / "old"; folder.mkdir()
    pdf = folder / "old.pdf"; pdf.write_bytes(b"%PDF-1.4")
    (folder / "old.pdf.drill").mkdir()
    (folder / "old.pdf.drill.json").write_text("{}")
    sc = Sidecar(pdf)
    assert sc.blob_dir == folder / "old.pdf.drill"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
