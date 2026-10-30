"""The `status` Files list is what the drillui Outputs panel offers a reader,
and in the self-contained library layout NOTHING in it was clickable — the
document's own PDF included.

`status` printed each file as `p.relative_to(sc.pdf_path.parent)`. In the
library layout the PDF lives at `<stem>/<stem>.pdf`, so the doc folder IS the
parent and that call collapses every entry to a BARE basename
(`2001_Grec_Kanahori.pdf`). drillui refuses a bare filename on purpose — a
bare `foo.md` in the prose is almost always a filename from the document's
CONTENT, not an artifact (its rule 2 requires a directory component) — so the
list rendered as plain text under a header that promises "click in the Outputs
panel".

`_artref` exists for exactly this and says so in its docstring; it was simply
not used here. It returns the path relative to `blob_dir.parent`, which is
`<stem>/<file>` in the library layout and `<name>.pdf.drill/<file>` in the
legacy one.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C

#: drillui_term.html rule 2 — a path-like token in the prose is only taken as
#: an artifact when it carries a directory component. Mirrored here because it
#: is the contract the status list has to satisfy.
UI_TOKEN_RE = re.compile(
    r"(?<![\w/])((?:[\w.+~@%-]+/)+[\w.+~@%-]+\."
    r"(html|svg|pdf|md|json|txt|tex|log))\b(?!\.[a-z])")


def _files_block(text: str) -> list[str]:
    """The paths listed under the Files header, without their size suffix."""
    out = []
    in_block = False
    for line in text.splitlines():
        if line.startswith("Files (open in a tab"):
            in_block = True
            continue
        if in_block:
            m = re.match(r"^\s+(.+?)\s+\(\d+ KB\)$", line)
            if not m:
                break
            out.append(m.group(1))
    return out


def _library_doc(tmp_path: Path, stem: str = "Kana"):
    """A document in the self-contained layout: `<stem>/<stem>.pdf`."""
    folder = tmp_path / stem
    folder.mkdir()
    pdf = folder / f"{stem}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = C.Sidecar(pdf)
    sc.add_fact("SIZE_KNOWN")
    sc.save()
    (folder / f"{stem}.md").write_text("# hi\n", encoding="utf-8")
    (folder / "svg").mkdir()
    (folder / "svg" / "EQ1.svg").write_text("<svg/>", encoding="utf-8")
    assert sc.blob_dir == folder, sc.blob_dir       # the layout under test
    return pdf, sc, folder


def test_every_status_file_carries_its_doc_folder(tmp_path):
    pdf, sc, folder = _library_doc(tmp_path)
    listed = _files_block(C.cmd_status(pdf))
    assert listed, "no Files block in `status`"
    assert f"Kana/Kana.pdf" in listed, listed
    for rel in listed:
        assert rel.startswith("Kana/"), f"{rel!r} lost the doc folder"
        assert (folder.parent / rel).exists(), f"{rel!r} resolves nowhere"


def test_the_pdf_link_is_one_the_drillui_token_rule_accepts(tmp_path):
    pdf, sc, folder = _library_doc(tmp_path)
    listed = _files_block(C.cmd_status(pdf))
    pdfs = [r for r in listed if r.endswith(".pdf")]
    assert pdfs, listed
    for rel in pdfs:
        assert UI_TOKEN_RE.search(rel), f"drillui would not link {rel!r}"


def test_status_uses_artref_not_relative_to_the_pdf_parent():
    import inspect
    src = inspect.getsource(C.cmd_status)
    block = src.split("Files (open in a tab")[1][:900]
    assert "_artref(sc, p)" in block, block
    assert "relative_to(sc.pdf_path.parent)" not in block, block
