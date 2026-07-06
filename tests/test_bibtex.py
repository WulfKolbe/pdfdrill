"""
`pdfdrill bibtex` augmentation: an arXiv input must NOT yield @misc{unknown2023}.
The embedded PDF metadata is usually empty, so bibtex augments from the FREE
arXiv abs-page metadata (title/authors) and warns when still a placeholder.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import sources
from pdfdrill.commands import (_augment_bibtex, _is_placeholder_bib, _arxiv_year)
from pdfdrill.sidecar import Sidecar


def test_is_placeholder_bib():
    assert _is_placeholder_bib({"title": "", "author": "", "citekey": "unknown2023"})
    assert _is_placeholder_bib(None)
    assert not _is_placeholder_bib({"title": "Real Title", "author": "", "citekey": "x2023"})
    assert not _is_placeholder_bib({"title": "", "author": "A B", "citekey": "b2023"})


def test_arxiv_year():
    assert _arxiv_year("2305.04710v1") == "2023"
    assert _arxiv_year("2104.13478") == "2021"
    assert _arxiv_year("math/0309136") == "2003"
    assert _arxiv_year("") == ""


def test_augment_from_arxiv_metadata(monkeypatch):
    monkeypatch.setattr(sources, "fetch_arxiv_metadata", lambda aid: {
        "title": "ElasticHash: Semantic Image Similarity Search",
        "authors": ["Nikolaus Korfhage", "Markus Mühling", "Bernd Freisleben"],
        "primary_category": "cs.CV", "arxiv_id": aid,
    })
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "2305.04710v1.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        sc.set_evidence("source_arxiv_id", "2305.04710v1")
        bib = {"title": "", "author": "", "year": "", "citekey": "unknown2023",
               "entry_type": "misc", "pages": 10, "url": ""}
        note = _augment_bibtex(bib, pdf, sc)
        assert note == ""                                  # no warning — it's real now
        assert bib["title"].startswith("ElasticHash")
        assert bib["author"] == "Nikolaus Korfhage and Markus Mühling and Bernd Freisleben"
        assert bib["entry_type"] == "misc"                 # canonical arXiv @misc form
        assert bib["year"] == "2023"
        assert bib["citekey"] == "korfhage2023"            # NOT unknown2023
        assert bib["arxiv_id"] == "2305.04710v1"
        assert bib["eprint"] == "2305.04710v1"             # eprint/archivePrefix present
        assert bib["archive_prefix"] == "arXiv"


def test_placeholder_warns_when_no_source(monkeypatch):
    # not arXiv, no model, empty metadata → stays a placeholder + warns
    def _no_arxiv(s):  # bare_arxiv_id / parse_arxiv_id both miss a plain stem
        return None
    monkeypatch.setattr(sources, "bare_arxiv_id", _no_arxiv)
    monkeypatch.setattr(sources, "parse_arxiv_id", _no_arxiv)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "scan_001.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        bib = {"title": "", "author": "", "year": "2023", "citekey": "unknown2023",
               "entry_type": "misc", "pages": 3, "url": ""}
        note = _augment_bibtex(bib, pdf, sc)
        assert "PLACEHOLDER" in note and "abstract" in note
        assert _is_placeholder_bib(bib)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
