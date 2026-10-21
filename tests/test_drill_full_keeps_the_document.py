"""`drill --full` forgets DERIVED state. It must never lose the input.

Found by an auditing session on cc3a34ab: in the SELF-CONTAINED layout
(`<stem>/<stem>.pdf` — every document in the library, and every document the
autofolder has touched) `Sidecar.blob_dir` IS the folder that holds the
document, so `--full`'s `shutil.rmtree(blob_dir)` deleted the document. It
exited 0; the only sign was a mid-output "Model-lane read failed: File not
found". A licensed or personalised copy has no second download, so the test is
about the input, not about the tidiness of the wipe.
"""
from pathlib import Path

import pytest

from pdfdrill.cli import _wipe_derived


def _doc(tmp_path: Path, *, self_contained: bool) -> tuple[Path, Path]:
    """(pdf, blob_dir) in each layout, with one derived artifact in place."""
    if self_contained:
        folder = tmp_path / "doc"
        folder.mkdir()
        pdf = folder / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.7\nthe input\n")
        blob = folder                      # the layout under test
    else:
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.7\nthe input\n")
        blob = tmp_path / "doc.pdf.drill"
        blob.mkdir()
    (blob / "model.docmodel.json").write_text("{}")
    (blob / "inspect").mkdir()
    (blob / "inspect" / "page-1.png").write_bytes(b"png")
    return pdf, blob


def test_self_contained_wipe_keeps_the_document():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pdf, blob = _doc(Path(td), self_contained=True)
        _wipe_derived(blob, pdf)
        assert pdf.is_file(), "--full deleted the document"
        assert pdf.read_bytes() == b"%PDF-1.7\nthe input\n", "document was rewritten"


def test_self_contained_wipe_removes_the_derived_state():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pdf, blob = _doc(Path(td), self_contained=True)
        _wipe_derived(blob, pdf)
        assert not (blob / "model.docmodel.json").exists(), "a model survived --full"
        assert not (blob / "inspect").exists(), "a derived directory survived --full"


def test_self_contained_wipe_keeps_a_hand_placed_author_source():
    """In the LEGACY layout an author `.tex` sits beside the `.drill/` dir and
    `--full` never touched it. Keeping it here is what makes the two layouts
    behave the same — and keeping is the safe error."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pdf, blob = _doc(Path(td), self_contained=True)
        (blob / "doc.tex").write_text(r"\documentclass{article}")
        _wipe_derived(blob, pdf)
        assert (blob / "doc.tex").is_file(), "--full deleted an author source"


def test_legacy_layout_is_still_wiped_whole():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pdf, blob = _doc(Path(td), self_contained=False)
        _wipe_derived(blob, pdf)
        assert not blob.exists(), "the legacy blob dir should go entirely"
        assert pdf.is_file(), "--full deleted the document"


def test_losing_the_document_raises_instead_of_drilling_on():
    """The invariant is CHECKED, not assumed: the old code carried on and
    reported a read failure 30 lines later."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pdf, blob = _doc(Path(td), self_contained=True)
        pdf.unlink()                       # simulate the document gone
        with pytest.raises(RuntimeError, match="about to lose the document"):
            _wipe_derived(blob, pdf)
