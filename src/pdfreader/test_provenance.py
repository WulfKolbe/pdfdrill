"""785 — an artefact must say which pdf2mmd produced it.

`report.txt` recorded everything about the document and nothing about the
reader. When two installs existed on one machine — a checkout at 784 and a
standalone copy frozen days earlier — their results could be told apart only
by file mtime, and 347 GB of output had to be dated rather than identified.

The property that matters is not "there is a version string". It is that the
identity survives the thing that actually happens to code: being copied.
"""
import os
import shutil
from pathlib import Path

import provenance

HERE = Path(__file__).resolve().parent


def _copy_sources(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(HERE.glob("*.py")):
        shutil.copy2(f, dest / f.name)
    return dest


def test_a_checkout_is_named_by_its_commit():
    i = provenance.identity(HERE)
    assert i["kind"] == "git"
    assert i["rev"] and len(i["rev"]) >= 7
    assert provenance.stamp(HERE).startswith("pdf2mmd " + i["rev"])


def test_a_dirty_tree_says_so():
    i = provenance.identity(HERE)
    s = provenance.stamp(HERE)
    assert ("+local changes" in s) == bool(i["dirty"])


def test_a_copy_that_is_not_a_checkout_still_has_an_identity(tmp_path):
    """The pdf2mmdx case: sources copied out of the repo, no .git. It must not
    report "unknown" — an artefact whose producer is unknown is exactly the
    artefact nobody can decide about later."""
    d = _copy_sources(tmp_path / "copy")
    i = provenance.identity(d)
    assert i["kind"] == "tree"
    assert len(i["rev"]) == 12
    assert "not a checkout" in provenance.stamp(d)


def test_the_identity_of_a_copy_survives_its_mtimes_being_rewritten(tmp_path):
    """753 fell back to the newest source mtime, and its own docstring says why
    that is wrong: copying a tree rewrites every mtime, so the copy and the
    original report different revisions while being byte-identical. A digest
    of the sources is the same number wherever the tree sits."""
    d = _copy_sources(tmp_path / "copy")
    before = provenance.identity(d)["rev"]
    for f in d.glob("*.py"):
        os.utime(f, (0, 0))
    assert provenance.identity(d)["rev"] == before


def test_two_copies_of_the_same_sources_agree(tmp_path):
    a = _copy_sources(tmp_path / "a")
    b = _copy_sources(tmp_path / "b")
    assert provenance.identity(a)["rev"] == provenance.identity(b)["rev"]


def test_changing_a_source_changes_the_identity(tmp_path):
    d = _copy_sources(tmp_path / "copy")
    before = provenance.identity(d)["rev"]
    (d / "provenance.py").write_text(
        (d / "provenance.py").read_text() + "\n# edited\n", encoding="utf-8")
    assert provenance.identity(d)["rev"] != before


def test_the_report_line_carries_both_the_code_and_the_run(tmp_path):
    line = provenance.built_line(HERE)
    assert line.startswith("pdf2mmd ")
    assert " — run " in line
