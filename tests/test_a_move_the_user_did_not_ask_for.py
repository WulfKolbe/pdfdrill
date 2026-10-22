"""pdfdrill moved the user's PDF, in a directory it had no claim on, silently.

Found by an audit on a stranger's install (2026-10-22, main at cc02c9bb): `drill`
"moved the input PDF from the working directory into a new `<stem>/` folder, and
its output does not say so". Reproduced here on `pdfdrill size` — the cheapest,
read-only probe — with ONE lone PDF in a scratch directory.

`sources.adopt_into_doc_folder` files a loose PDF in the LIBRARY ROOT into its
own folder, which is the documented one-folder-per-document layout. Its own
docstring draws the boundary in as many words:

    Anywhere else — someone's Downloads folder, a working directory —
    nothing is ever moved.

That sentence was false on a fresh machine. The guard compares the PDF's parent
against `config.library_root()`, which falls back to `download_dir()`, which
falls back to `Path.cwd()`. With no `~/Downloads` and no config — a container,
which is where a stranger meets pdfdrill — the user's WORKING DIRECTORY *was*
the library root, so the guard passed and the file was adopted. An inferred root
is not a statement that pdfdrill may reorganise it. Same fallback family as
finding K (HANDOVER-RULES 37), one step worse: K wrote a marker into the cwd,
this moved the user's own input.

Two requirements, and the second matters even where the move is right: adoption
needs a DECLARED root, and a move nobody asked for has to be reported — the
next command the user types carries the old path.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _run(cwd: Path, home: Path, *args: str):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", ""),
           "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1",
           "PDFDRILL_SANDBOX": "1", "PDFDRILL_NO_PREFLIGHT": "1"}
    return subprocess.run([sys.executable, "-m", "pdfdrill", *args],
                          cwd=cwd, env=env, capture_output=True, text=True,
                          timeout=120)


def test_a_working_directory_is_not_a_library(tmp_path):
    """THE CASE BUILT TO FAIL. No ~/Downloads, no config: the cwd must not
    become a library just because every other candidate was absent."""
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / "paper.pdf").write_bytes(PDF)
    r = _run(work, home, "size", "paper.pdf")
    assert (work / "paper.pdf").is_file(), (
        "pdfdrill moved the user's PDF out of a directory it has no claim on; "
        f"the directory now holds {sorted(p.name for p in work.iterdir())}\n"
        f"{r.stdout}\n{r.stderr}")
    assert not (work / "paper" / "paper.pdf").exists()


def test_a_declared_library_root_still_gets_the_folder_layout(tmp_path):
    """The other direction — the feature must survive its own fix. A root the
    user CONFIGURED is a statement that pdfdrill may organise it."""
    home = tmp_path / "home"
    (home / ".config" / "pdfdrill").mkdir(parents=True)
    lib = tmp_path / "lib"
    lib.mkdir()
    (home / ".config" / "pdfdrill" / "config.json").write_text(
        json.dumps({"library_root": str(lib), "download_dir": str(lib)}))
    (lib / "paper.pdf").write_bytes(PDF)
    r = _run(lib, home, "size", "paper.pdf")
    assert (lib / "paper" / "paper.pdf").is_file(), (
        f"the declared library no longer gets the per-document layout:\n"
        f"{r.stdout}\n{r.stderr}")


def test_the_move_is_reported_where_the_user_will_see_it(tmp_path):
    """A document passed by name came back from a different path in silence,
    and the next command typed with the old path found nothing."""
    home = tmp_path / "home"
    (home / ".config" / "pdfdrill").mkdir(parents=True)
    lib = tmp_path / "lib"
    lib.mkdir()
    (home / ".config" / "pdfdrill" / "config.json").write_text(
        json.dumps({"library_root": str(lib), "download_dir": str(lib)}))
    (lib / "paper.pdf").write_bytes(PDF)
    r = _run(lib, home, "size", "paper.pdf")
    out = r.stdout + r.stderr
    assert "filed paper.pdf" in out, (
        "the move was not reported — the user is left holding a stale path:\n"
        + out)
    assert str(lib / "paper") in out or "paper/" in out, (
        "the report does not say WHERE it went:\n" + out)


def test_it_is_reported_only_when_it_happened(tmp_path):
    """A note on every command would be noise, and noise is not a report."""
    home = tmp_path / "home"
    (home / ".config" / "pdfdrill").mkdir(parents=True)
    lib = tmp_path / "lib"
    (lib / "paper").mkdir(parents=True)
    (home / ".config" / "pdfdrill" / "config.json").write_text(
        json.dumps({"library_root": str(lib), "download_dir": str(lib)}))
    (lib / "paper" / "paper.pdf").write_bytes(PDF)      # already self-contained
    r = _run(lib, home, "size", "paper/paper.pdf")
    assert "filed" not in (r.stdout + r.stderr), (
        "nothing moved and pdfdrill said it did:\n" + r.stdout + r.stderr)


def test_the_declared_check_is_what_the_guard_asks(tmp_path, monkeypatch):
    """Directly, so the unit cannot drift from the four end-to-end cases."""
    sys.path.insert(0, str(ROOT / "src"))
    from pdfdrill import config as cfg, sources as src
    lib = tmp_path / "lib"
    lib.mkdir()
    pdf = lib / "x.pdf"
    pdf.write_bytes(PDF)
    monkeypatch.setattr(cfg, "library_root_is_declared", lambda: False)
    assert src.adopt_into_doc_folder(pdf, lib) == pdf, (
        "an INFERRED root still gets reorganised")
    monkeypatch.setattr(cfg, "library_root_is_declared", lambda: True)
    out = src.adopt_into_doc_folder(pdf, lib)
    assert out == lib / "x" / "x.pdf", f"a declared root did not adopt: {out}"
    assert src.last_adoption() == (pdf, out), "the move was not recorded"
    assert src.last_adoption() is None, (
        "last_adoption is not read-once, so a later command in the same "
        "process would report a move it did not make")
