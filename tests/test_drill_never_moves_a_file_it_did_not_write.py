"""
P11: filing a PDF into its own folder must never move a file pdfdrill did
not write.

`doclock.ensure_doc_folder` files a loose PDF into `<stem>/` when a second
PDF shares its directory. It went through `relocate`'s planner, which takes
EVERY `X.*` sibling, so on 2026-11-26 a `drill` moved the session's own log
`lib_3f.out` along with `lib_3f.pdf`. An owner's `X.tex` (the source of
`X.pdf`), notes in `X.txt` or a script's output would go the same way.

Moved: the PDF, its sidecar, its blob directory, and siblings whose suffix
only pdfdrill writes (readings, caches, the e-print archive). Everything else
stays where it was, and every move is reported.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import doclock


def _pdf(p: Path):
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


def test_a_foreign_same_stem_file_stays_where_it_was(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFDRILL_NO_AUTOFOLDER", raising=False)
    a = _pdf(tmp_path / "a.pdf")
    _pdf(tmp_path / "other.pdf")                   # a second document (`B.pdf` would be our own output)
    (tmp_path / "a.out").write_text("my own log")
    (tmp_path / "a.tex").write_text("\\documentclass{article}")  # the owner's source
    (tmp_path / "a.lines.json").write_text("{}")   # a reading pdfdrill wrote
    new = Path(doclock.ensure_doc_folder(a))
    assert new == tmp_path / "a" / "a.pdf" and new.is_file()
    assert (tmp_path / "a.out").read_text() == "my own log"
    assert (tmp_path / "a.tex").is_file()
    assert not (tmp_path / "a" / "a.out").exists()
    assert (tmp_path / "a" / "a.lines.json").is_file()


def test_every_move_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFDRILL_NO_AUTOFOLDER", raising=False)
    a = _pdf(tmp_path / "a.pdf")
    _pdf(tmp_path / "other.pdf")
    (tmp_path / "a.lines.json").write_text("{}")
    (tmp_path / "a.out").write_text("x")
    doclock.ensure_doc_folder(a)
    moved, left = doclock.last_filing()
    assert {p.name for p, _ in moved} == {"a.pdf", "a.lines.json"}
    assert [p.name for p in left] == ["a.out"]
