r"""A directory is not a document.

~/pdfdrill-library/BH1/ holds two:

    BH1.pdf           -> blob_dir BH1/                        (self-contained)
    BH1-9add65ca.pdf  -> blob_dir BH1/BH1-9add65ca.pdf.drill/ (legacy)

blob_dir_for has always resolved both correctly. What went wrong was every
ad-hoc scan that walked DIRECTORIES and took sorted(glob("*.drill.json"))[0]
plus <dir>/model.docmodel.json — reading one document's sidecar against the
other's model. On BH1 that read a 4-page pdfminer stub and reported the
319-page MathPix book (5,244 maths objects) as having no mathematics, and a
keyless purge skipped the stub because it had been classified by its neighbour.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.sidecar import iter_documents, blob_dir_for


def _pdf(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4")
    return p


def test_two_documents_in_one_directory_are_both_found(tmp_path):
    d = tmp_path / "BH1"
    _pdf(d / "BH1.pdf")
    _pdf(d / "BH1-9add65ca.pdf")
    got = {p.name for p, _b, _j in iter_documents(tmp_path)}
    assert got == {"BH1.pdf", "BH1-9add65ca.pdf"}


def test_each_document_gets_its_own_blob_dir(tmp_path):
    """The property the directory-based scans violated: two documents in one
    folder must not share a blob_dir, or one reads the other's artifacts."""
    d = tmp_path / "BH1"
    _pdf(d / "BH1.pdf")
    _pdf(d / "BH1-9add65ca.pdf")
    blobs = {p.name: b for p, b, _j in iter_documents(tmp_path)}
    assert blobs["BH1.pdf"] == d                      # self-contained
    assert blobs["BH1-9add65ca.pdf"] == d / "BH1-9add65ca.pdf.drill"
    assert blobs["BH1.pdf"] != blobs["BH1-9add65ca.pdf"]


def test_each_document_gets_its_own_sidecar(tmp_path):
    d = tmp_path / "BH1"
    _pdf(d / "BH1.pdf")
    _pdf(d / "BH1-9add65ca.pdf")
    js = {p.name: j.name for p, _b, j in iter_documents(tmp_path)}
    assert js["BH1.pdf"] != js["BH1-9add65ca.pdf"]


def test_report_pdf_is_not_a_document(tmp_path):
    d = tmp_path / "doc"
    _pdf(d / "doc.pdf")
    _pdf(d / "report.pdf")
    assert {p.name for p, _b, _j in iter_documents(tmp_path)} == {"doc.pdf"}


def test_projector_outputs_are_not_documents(tmp_path):
    """.scikg.pdf, .glossaries.pdf and the standalone formula report are OUTPUTS
    of a document that sit beside it; counting them inflates a corpus census."""
    d = tmp_path / "2510.11170v2"
    _pdf(d / "2510.11170v2.pdf")
    _pdf(d / "2510.11170v2.scikg.pdf")
    _pdf(d / "2510.11170v2.glossaries.pdf")
    _pdf(d / "Formula Report — 2510.11170v2.lines.json.pdf")
    assert {p.name for p, _b, _j in iter_documents(tmp_path)} == {"2510.11170v2.pdf"}


def test_pdfs_inside_a_blob_dir_are_artifacts(tmp_path):
    """A rasterised page or extracted attachment inside <name>.pdf.drill/ is an
    artifact OF a document, not another document."""
    d = tmp_path / "doc"
    _pdf(d / "doc.pdf")
    _pdf(d / "other.pdf.drill" / "page-001.pdf")
    assert {p.name for p, _b, _j in iter_documents(tmp_path)} == {"doc.pdf"}


def test_documents_at_the_root_are_found(tmp_path):
    """The library root itself holds loose documents (3 of them in practice)."""
    _pdf(tmp_path / "Zwiebeln.pdf")
    _pdf(tmp_path / "sub" / "sub.pdf")
    assert {p.name for p, _b, _j in iter_documents(tmp_path)} == {"Zwiebeln.pdf", "sub.pdf"}


def test_agrees_with_blob_dir_for(tmp_path):
    """The enumerator must not invent its own layout rule."""
    d = tmp_path / "BH1"
    _pdf(d / "BH1.pdf")
    _pdf(d / "BH1-9add65ca.pdf")
    for pdf, blob, js in iter_documents(tmp_path):
        assert (blob, js) == blob_dir_for(pdf)


def test_empty_and_missing_roots_are_safe(tmp_path):
    assert list(iter_documents(tmp_path)) == []
    assert list(iter_documents(tmp_path / "nope")) == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
