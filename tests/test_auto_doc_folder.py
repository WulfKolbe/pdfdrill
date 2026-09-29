"""
830 — the first build gives a loose document its own folder.

Every build command writes FIXED names. `doc_dir = pdf.parent` (commands.py)
sends `evidence-<kind>.pdf` and `residuals.pdf` beside the PDF under names that
are identical for every document, and `report.pdf`/`B.pdf` likewise. Two PDFs
drilled in one directory therefore do not collide occasionally — they collide
always, and the second silently overwrites the first's reports.

The library never showed this because its documents already live in
`<stem>/<stem>.pdf`. A working directory like ~/Downloads is where it bites,
and a second CLI writing reports there is how it was noticed.

The move is `relocate`'s phase 1 pointed at the document's OWN parent, so the
PDF, its sidecar, the flattened `X.pdf.drill/` blobs and every `X.*` sibling
travel together. A `.lines.json` left behind would be worse than no move at
all — the next build would not find the MathPix conversion it is meant to read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.doclock import ensure_doc_folder                 # noqa: E402

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"


def test_a_lone_document_is_left_where_it_is(tmp_path):
    """A directory holding one document IS that document's folder. Moving it
    buys nothing and surprises every caller that expects its artefacts beside
    the path it passed."""
    p = tmp_path / "only.pdf"
    p.write_bytes(PDF)
    assert ensure_doc_folder(p) == p
    assert p.is_file()


def test_a_second_document_triggers_the_folder(tmp_path):
    a = tmp_path / "one.pdf"
    b = tmp_path / "two.pdf"
    a.write_bytes(PDF)
    b.write_bytes(PDF)
    got = ensure_doc_folder(a)
    assert got == tmp_path / "one" / "one.pdf"
    assert got.is_file()
    assert not a.exists()
    assert b.is_file(), "the other document must not be touched"


def test_the_siblings_travel_with_it(tmp_path):
    """The whole reason to reuse relocate's planner: a `.lines.json` left
    behind is a paid MathPix conversion the next build cannot find."""
    p = tmp_path / "doc.pdf"
    p.write_bytes(PDF)
    (tmp_path / "other.pdf").write_bytes(PDF)
    (tmp_path / "doc.lines.json").write_text(json.dumps({"pages": []}))
    (tmp_path / "doc.bib").write_text("@article{x,title={T}}")
    (tmp_path / "doc.md").write_text("# t")
    ensure_doc_folder(p)
    for name in ("doc.pdf", "doc.lines.json", "doc.bib", "doc.md"):
        assert (tmp_path / "doc" / name).is_file(), name
        assert not (tmp_path / name).exists(), name


def test_an_already_self_contained_document_is_a_no_op(tmp_path):
    """Every document in the library is this case."""
    d = tmp_path / "paper"
    d.mkdir()
    p = d / "paper.pdf"
    p.write_bytes(PDF)
    (tmp_path / "elsewhere.pdf").write_bytes(PDF)
    assert ensure_doc_folder(p) == p
    assert p.is_file()


def test_pdfdrills_own_output_is_not_a_second_document(tmp_path):
    """`report.pdf` and `evidence-*.pdf` are artefacts OF the document already
    there. Counting them would make the first build promote the folder it had
    just written into."""
    p = tmp_path / "doc.pdf"
    p.write_bytes(PDF)
    for gen in ("report.pdf", "evidence-equation.pdf", "residuals.pdf",
                "B.pdf", "formula-report.pdf"):
        (tmp_path / gen).write_bytes(PDF)
    assert ensure_doc_folder(p) == p
    assert p.is_file()


def test_the_opt_out(tmp_path, monkeypatch):
    p = tmp_path / "a.pdf"
    p.write_bytes(PDF)
    (tmp_path / "b.pdf").write_bytes(PDF)
    monkeypatch.setenv("PDFDRILL_NO_AUTOFOLDER", "1")
    assert ensure_doc_folder(p) == p
    assert p.is_file()


def test_it_returns_a_Path_not_a_string(tmp_path):
    """The handlers take `.stem`/`.parent` off this value. Returning a string
    failed 122 tests with `'str' object has no attribute 'stem'`."""
    p = tmp_path / "a.pdf"
    p.write_bytes(PDF)
    (tmp_path / "b.pdf").write_bytes(PDF)
    assert isinstance(ensure_doc_folder(p), Path)


def test_a_file_named_like_the_folder_is_left_alone(tmp_path):
    """`<stem>` already exists as a FILE: there is nowhere to move to, and
    guessing another name would scatter the document further."""
    p = tmp_path / "doc.pdf"
    p.write_bytes(PDF)
    (tmp_path / "other.pdf").write_bytes(PDF)
    (tmp_path / "doc").write_text("in the way")
    assert ensure_doc_folder(p) == p
    assert p.is_file()


def test_the_old_path_still_resolves(tmp_path, monkeypatch):
    """The move is ours; so is the cost of finding the document again. Every
    command line, script and shell history naming `<dir>/x.pdf` must keep
    working after the first build turns it into `<dir>/x/x.pdf`."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pdfdrill.cli import _pdf

    a = tmp_path / "one.pdf"
    a.write_bytes(PDF)
    (tmp_path / "two.pdf").write_bytes(PDF)
    moved = ensure_doc_folder(a)
    assert not a.exists()

    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    assert _pdf([str(a)]).resolve() == moved.resolve()
