"""A command that MOVES the document must not then read the old path.

`doclock.ensure_doc_folder` relocates a document into `<stem>/` when a SECOND
document shares its folder, so that two documents cannot overwrite each other's
`evidence-*.pdf` and `residuals.pdf` (854). That move is deliberate and stays.

It runs inside the `@_writes` decorator, i.e. AFTER the CLI resolved the path
and BEFORE the handler. So in

    pdf = _pdf(args)
    return _with_verdict(cmd_md(pdf, ...), pdf, md=True)

`cmd_md` is handed the moved path and writes its sidecar in the new
self-contained layout, while `_with_verdict` still holds the ORIGINAL path and
builds a Sidecar for the legacy layout — an empty one. Measured, installed
entry point, two PDFs in one folder:

    Extracted 2963 words of Markdown across 3 pages ...
    pdfdrill verdict: NOT REACHED — text: no reading

A run that read the whole document reported that it had read nothing. That is
T-0153's false-report class (rule 4), and the cause is one document with two
possible sidecars resolved twice with different answers.

The fix is not to look in both places; it is to resolve the layout ONCE and
publish it, the way `sources.adopt_into_doc_folder` publishes `_LAST_ADOPTION`
because "A MOVE THE USER DID NOT ASK FOR MUST BE REPORTED" (2026-10-22 audit).
"""
from pathlib import Path


def _stub(p: Path) -> Path:
    """A PDF for PATH logic only. `ensure_doc_folder` reads names and
    `is_file()`, never the bytes — `tests/test_doclock.py` uses the same stub.
    The real document goes through the acceptance run, not through here."""
    p.write_bytes(b"%PDF-1.4\n")
    return p


def _two_docs(tmp_path):
    """A folder holding two documents — the shape that triggers the move."""
    return (_stub(tmp_path / "1805.01788-p0003.pdf"),
            _stub(tmp_path / "other-doc.pdf"))


def test_ensure_doc_folder_publishes_the_move(tmp_path):
    """The move must be visible to the caller, not only to the handler."""
    from pdfdrill import doclock
    a, _b = _two_docs(tmp_path)
    doclock.reset_last_move()
    moved = doclock.ensure_doc_folder(a)
    assert moved != a, "a second document in the folder must trigger the move"
    assert moved.is_file()
    assert doclock.last_move() == (a, moved), (
        "ensure_doc_folder moved the document and did not say so; the caller "
        "cannot find the sidecar it wrote")


def test_the_current_path_of_a_moved_document(tmp_path):
    """`current_path` answers from the published move, not the filesystem."""
    from pdfdrill import doclock
    a, _b = _two_docs(tmp_path)
    doclock.reset_last_move()
    moved = doclock.ensure_doc_folder(a)
    assert doclock.current_path(a) == moved
    # a path nothing moved comes back unchanged
    assert doclock.current_path(_b) == _b


def test_a_document_alone_in_its_folder_is_not_moved(tmp_path):
    """One document is already its own folder's subject — nothing to collide."""
    from pdfdrill import doclock
    a = _stub(tmp_path / "alone.pdf")
    doclock.reset_last_move()
    assert doclock.ensure_doc_folder(a) == a
    assert doclock.last_move() is None
