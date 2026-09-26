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


# --------------------------------------------------------------------------
# The HOST belongs in the folder name — 807.
# --------------------------------------------------------------------------

def test_the_folder_stem_names_its_archive():
    from pdfdrill.sources import archive_stem
    assert archive_stem("arxiv", "2510.04618v1") == "arxiv.2510.04618v1"
    assert archive_stem("vixra", "1702.0234v1") == "vixra.1702.0234v1"
    assert archive_stem("arxiv", "math/0309136") == "arxiv.math_0309136"


def _archive_doc(root, folder):
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{folder}.pdf").write_bytes(b"%PDF-1.4\n")
    return d / f"{folder}.pdf"


def test_a_bare_id_still_finds_its_prefixed_folder(tmp_path):
    """Nobody types `arxiv.2510.04618v1`. They type the id, off the paper."""
    from pdfdrill.sources import library_pdf_for
    want = _archive_doc(tmp_path, "arxiv.2510.04618v1")
    for q in ("2510.04618v1", "arxiv.2510.04618v1", "2510.04618.pdf"):
        assert library_pdf_for(q, tmp_path) == want, q


def test_a_bare_id_finds_a_version_it_did_not_ask_for(tmp_path):
    """An id in a citation rarely carries a version, and the folder always
    does."""
    from pdfdrill.sources import library_pdf_for
    want = _archive_doc(tmp_path, "arxiv.2510.04618v1")
    assert library_pdf_for("2510.04618", tmp_path) == want


def test_an_id_with_a_dot_keeps_everything_after_it(tmp_path):
    """`Path("2510.04618").stem` is `"2510"` — the id's own dot reads as an
    extension. That silently truncated every dotted id; it went unnoticed only
    because the unprefixed lookup matched first."""
    from pdfdrill.sources import library_pdf_for
    _archive_doc(tmp_path, "arxiv.2510")            # a decoy the bug would hit
    want = _archive_doc(tmp_path, "arxiv.2510.04618v1")
    assert library_pdf_for("2510.04618", tmp_path) == want


def test_the_two_archives_do_not_shadow_each_other(tmp_path):
    """`1702.0234` is a valid id in both. The prefix is what separates them,
    and a bare query must not silently pick the other archive's paper."""
    from pdfdrill.sources import library_pdf_for
    vx = _archive_doc(tmp_path, "vixra.1702.0234v1")
    assert library_pdf_for("vixra.1702.0234v1", tmp_path) == vx
    ax = _archive_doc(tmp_path, "arxiv.1702.02340v1")
    assert library_pdf_for("arxiv.1702.02340v1", tmp_path) == ax


def test_the_arxiv_id_survives_a_reopen(tmp_path):
    """THE ONE THAT NEARLY GOT AWAY. The arXiv id drives every FREE downstream
    route — the e-print LaTeX, the abstract, the bibtex entry. With the host in
    the name, `Path("arxiv.2510.04618v1.pdf").stem` is not a bare id, so reading
    it with `bare_arxiv_id` alone returned None and a reopened paper would have
    been pushed quietly off the free lanes onto OCR.
    """
    from pdfdrill import sources as S
    pdf = _archive_doc(tmp_path, "arxiv.2510.04618v1")
    info = S.resolve_input("2510.04618v1", dest_dir=tmp_path)
    assert info["path"] == pdf
    assert info["arxiv_id"] == "2510.04618v1"


def test_a_vixra_folder_yields_no_arxiv_id(tmp_path):
    """The prefix is load-bearing in both directions: a viXra document must not
    hand an arXiv id to a route that would fetch the wrong archive."""
    from pdfdrill import sources as S
    _archive_doc(tmp_path, "vixra.1702.0234v1")
    info = S.resolve_input("vixra.1702.0234v1", dest_dir=tmp_path)
    assert info["arxiv_id"] is None


def test_an_old_style_id_round_trips_through_the_filename(tmp_path):
    """`math/0309136` cannot be a filename; `archive_stem` writes it with an
    underscore and `archive_ident` reads the slash back."""
    from pdfdrill.sources import archive_stem, archive_ident
    stem = archive_stem("arxiv", "math/0309136")
    assert stem == "arxiv.math_0309136"
    assert archive_ident(stem) == ("arxiv", "math/0309136")


def test_find_docs_never_mistakes_an_artifact_for_a_document(tmp_path):
    """A migrated doc folder is full of PDFs that are not documents — report.pdf,
    evidence-*.pdf, residuals.pdf. Called legacy drills, they all "relocate"
    into one <library>/report/ and overwrite each other. Measured: 400+ of them
    in this library the day the documented default (no paths = the library root)
    was wired up."""
    from pdfdrill import relocate as R
    lib = tmp_path
    doc = lib / "2510.04618"
    (doc / "inspect").mkdir(parents=True)
    (doc / "2510.04618.pdf").write_bytes(b"%PDF")          # the document
    (doc / "report.pdf").write_bytes(b"%PDF")              # an artifact
    (doc / "evidence-equation.pdf").write_bytes(b"%PDF")   # an artifact
    (doc / "inspect" / "residuals.pdf").write_bytes(b"%PDF")
    legacy = lib / "loose" / "paper.pdf"                   # a real legacy drill
    legacy.parent.mkdir()
    legacy.write_bytes(b"%PDF")

    found = R.find_docs(lib)
    assert found == [legacy.resolve()]
