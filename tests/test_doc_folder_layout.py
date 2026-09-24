"""One folder per document, everything under it — 785.

The layout a DOWNLOAD gets is `<library>/<stem>/<stem>.pdf` with every
artifact beside it. A PDF copied into the library by hand did not get it: it
stayed at the root, `blob_dir_for` chose the legacy layout, and one document
became four entries side by side — `x.pdf`, `x.pdf.drill/`,
`x.pdf.drill.json`, `x.profile.json`. An agent told to drill a reading list
produces exactly that and then has to tidy up after itself, which is work
nobody should have had to do.

And the other half: a download that FAILED left the folder it had already
created, empty. `pdf_in_folder` finds no PDF there, so the bare name stops
resolving and `add <id>` answers "Not found" about a name the user can see a
directory for. Four were sitting in the library.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.sources import adopt_into_doc_folder


def _pdf(at: Path, name: str = "paper.pdf") -> Path:
    at.mkdir(parents=True, exist_ok=True)
    p = at / name
    p.write_bytes(b"%PDF-1.4\n%stub\n")
    return p


def test_a_loose_library_pdf_moves_into_its_own_folder(tmp_path):
    pdf = _pdf(tmp_path)
    out = adopt_into_doc_folder(pdf, tmp_path)
    assert out == tmp_path / "paper" / "paper.pdf"
    assert out.is_file() and not pdf.exists()


def test_a_pdf_outside_the_library_is_never_moved(tmp_path):
    """Someone's Downloads folder, a working directory, a mounted share —
    pdfdrill reorganises its OWN storage and nothing else."""
    elsewhere = tmp_path / "Downloads"
    pdf = _pdf(elsewhere)
    assert adopt_into_doc_folder(pdf, tmp_path / "library") == pdf
    assert pdf.is_file()


import pytest


@pytest.mark.parametrize("sibling", [
    "paper.pdf.drill.json", "paper.lines.json", "paper.md",
    "paper.tex.zip", "paper.profile.json",
])
def test_a_document_that_has_been_worked_on_is_left_where_it_is(tmp_path, sibling):
    """Moving the PDF away from its own `lines.json` re-acquires it — by the
    paid route if a key is set. Every sibling named after the document is work
    the move would separate from it, so any one of them declines."""
    pdf = _pdf(tmp_path)
    (tmp_path / sibling).write_text("{}")
    assert adopt_into_doc_folder(pdf, tmp_path) == pdf
    assert pdf.is_file()


def test_a_document_already_in_its_folder_is_not_nested_again(tmp_path):
    pdf = _pdf(tmp_path / "paper")
    assert adopt_into_doc_folder(pdf, tmp_path / "paper") == pdf
    assert not (tmp_path / "paper" / "paper" ).exists()


def test_an_occupied_target_is_not_overwritten(tmp_path):
    """`test.pdf` at the root and a DIFFERENT `test/test.pdf` already in the
    library is a real case. Declining is the only safe answer."""
    pdf = _pdf(tmp_path)
    other = _pdf(tmp_path / "paper")
    other.write_bytes(b"%PDF-1.4\n%different\n")
    assert adopt_into_doc_folder(pdf, tmp_path) == pdf
    assert other.read_bytes().endswith(b"different\n")


def test_a_failed_download_leaves_no_empty_folder(tmp_path, monkeypatch):
    from pdfdrill import sources

    def boom(url, dest):
        raise OSError("connection reset")

    monkeypatch.setattr(sources, "download", boom)
    dest = sources._doc_dest(tmp_path, "2609.24972.pdf")
    assert dest.parent.is_dir()                    # created ahead of the bytes
    try:
        sources._download_into_doc_folder("https://example.invalid/x.pdf", dest)
    except OSError:
        pass
    assert not dest.parent.exists(), \
        "an empty doc folder makes the bare name stop resolving for good"


# --------------------------------------------------------------------------
# A bare name has to mean what the user can SEE.
# --------------------------------------------------------------------------

def test_a_bare_name_resolves_with_or_without_the_extension(tmp_path):
    """The layout names the folder after the STEM — `1001850/1001850.pdf` — and
    a user reading that folder types the file they can see: `add 1001850.pdf`.
    The folder has no extension, so the lookup missed and the answer was "Not
    found" for a document sitting right there. `add Zwiebeln` worked and `add
    Zwiebeln.pdf` did not, which is not a distinction anyone can hold.
    """
    from pdfdrill.sources import library_pdf_for

    doc = _pdf(tmp_path / "1001850", "1001850.pdf")
    assert library_pdf_for("1001850", tmp_path) == doc
    assert library_pdf_for("1001850.pdf", tmp_path) == doc


def test_a_loose_pdf_at_the_library_root_is_still_found(tmp_path):
    """The pre-adoption layout, and anything dropped in by hand."""
    from pdfdrill.sources import library_pdf_for

    loose = _pdf(tmp_path, "notes.pdf")
    assert library_pdf_for("notes.pdf", tmp_path) == loose
    assert library_pdf_for("notes", tmp_path) == loose


def test_a_folder_wins_over_a_loose_file_of_the_same_name(tmp_path):
    """Most specific first: the drilled document, not the stray copy beside it."""
    from pdfdrill.sources import library_pdf_for

    _pdf(tmp_path, "paper.pdf").write_bytes(b"%PDF-1.4\n%loose\n")
    inside = _pdf(tmp_path / "paper", "paper.pdf")
    inside.write_bytes(b"%PDF-1.4\n%drilled\n")
    assert library_pdf_for("paper.pdf", tmp_path) == inside


def test_a_name_that_is_not_there_is_still_not_there(tmp_path):
    """Widening the lookup must not start inventing documents."""
    from pdfdrill.sources import library_pdf_for

    assert library_pdf_for("nothing.pdf", tmp_path) is None


def test_not_found_says_where_it_looked(tmp_path, monkeypatch):
    """"Not found: 1001850.pdf" is true and useless — the document was in the
    library the whole time, one directory down, and the user had just listed
    it. A lookup that searched three places must say which ones, because the
    next move depends entirely on which was wrong: a typo, the wrong working
    directory, or a document that is really not there."""
    from pdfdrill import cli, config as cfg

    (tmp_path / "Zwiebeln").mkdir()
    (tmp_path / "Zwiebeln" / "Zwiebeln.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(cfg, "library_root", lambda: tmp_path)

    msg = cli._not_found_message("Zwiebln.pdf", tmp_path / "Zwiebln.pdf")
    assert "Not found: Zwiebln.pdf" in msg
    assert str(tmp_path) in msg, "the library it searched must be named"
    assert "did you mean: Zwiebeln?" in msg, \
        "a typo is the case that sends people here; substring matching misses it"


def test_a_name_with_no_near_miss_offers_none(tmp_path, monkeypatch):
    """Guessing is worse than silence: a wrong suggestion sends the reader
    looking for a document that does not exist."""
    from pdfdrill import cli, config as cfg

    (tmp_path / "Zwiebeln").mkdir()
    monkeypatch.setattr(cfg, "library_root", lambda: tmp_path)
    assert "did you mean" not in cli._not_found_message("quantum.pdf",
                                                        tmp_path / "quantum.pdf")
