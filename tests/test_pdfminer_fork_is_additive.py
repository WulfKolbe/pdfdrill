"""
833 — the fork is ADDITIVE, and the integration rests on it staying so.

`commands.py` has said since the beginning that pdf2mmd's patched pdfminer
"cannot be imported here and must not be: … pulling it into this environment
would change what every other pdfminer caller in this package sees." That is
the reason the two programs are two programs, and it is measurably wrong:

    pdfminer-glyph-identity.patch:  600 lines,  +461 / -0

The patch adds class-level `std2name` / `mac2name` / `win2name` / `pdf2name`
tables and a `get_encoding_names()` classmethod — its own docstring calls it
"the twin of `get_encoding`" — and threads `cid` and `textstate_render`
through converter -> device -> layout. `get_encoding`, which every existing
caller uses, is untouched. 33 files under `src/` import pdfminer; a patch that
removes nothing cannot change what any of them sees.

This test is the gate on that claim. It is deliberately OFFLINE — it reads the
patch, not a built environment — so it runs on any machine and fails the moment
someone rebases the fork onto a newer pdfminer and the rebase starts deleting
things. Without it, the day the patch stops being additive is the day 33
callers find out one defect at a time.

See docs/superpowers/specs/2026-09-30-pdf2mmd-integration-design.md.
"""
import re
from pathlib import Path

import pytest

PATCH = Path(__file__).resolve().parents[1] / "vendor" / "pdfminer-glyph-identity.patch"


@pytest.fixture(scope="module")
def lines():
    if not PATCH.exists():                                   # pragma: no cover
        pytest.skip(f"vendored patch not present: {PATCH}")
    return PATCH.read_text(encoding="utf-8", errors="replace").splitlines()


def test_the_patch_is_vendored_here():
    """Not read from a sibling checkout. `PDF2MMD_HOME` pointing at a stale
    tree is how ser7 ran 784 for a week while this machine ran 820, and how a
    deleted ~/Downloads/pdf2mmd took ~/pdf2mmd/.pdfmm-venv with it."""
    assert PATCH.exists(), "the fork must live in this repo, not beside it"
    assert PATCH.stat().st_size > 1000


def test_it_removes_nothing(lines):
    """THE FACT THE INTEGRATION RESTS ON. A `-` line that is not a `---` file
    header is a deletion, and a deletion can change what an existing caller
    sees."""
    removed = [l for l in lines if l.startswith("-") and not l.startswith("---")]
    assert removed == [], (
        "the fork has stopped being additive — %d line(s) removed, starting "
        "with %r. Re-read the integration spec before going further: 33 files "
        "under src/ import pdfminer and none of them was reviewed against a "
        "subtractive fork." % (len(removed), removed[:1]))


def test_it_only_touches_the_files_it_claims_to(lines):
    """A fork that grows a sixth file has changed scope and needs re-reading."""
    touched = {m.group(1) for l in lines
               if (m := re.match(r"\+\+\+ b/(\S+)", l))}
    assert touched == {
        "pdfminer/converter.py", "pdfminer/encodingdb.py", "pdfminer/layout.py",
        "pdfminer/pdfdevice.py", "pdfminer/pdffont.py",
        # the fork carries its own test, which is why `install-pdfminer-fork.sh`
        # can verify the patch actually took (`cid 7 -> 'star'`) rather than
        # trusting that `git apply` exited 0.
        "tests/test_glyphname.py",
    }, touched


def test_it_adds_the_glyph_name_channel(lines):
    """The point of the fork: a cid -> POSTSCRIPT NAME map beside the cid ->
    Unicode one, so a `/star` from a TeX maths font stops arriving as
    `(cid:7)`."""
    body = "\n".join(lines)
    assert "get_encoding_names" in body
    for table in ("std2name", "mac2name", "win2name", "pdf2name"):
        assert table in body, table


def test_it_does_not_redefine_get_encoding(lines):
    """The Unicode channel every existing caller reads must keep its meaning.

    NARROWER THAN IT USED TO CLAIM. This test is named "does not touch" no
    longer, because the fork DOES touch `get_encoding`: its body gains
    `self._cid2name[cid] = cast(str, name)`. What this checks is that the
    function is not REDEFINED; that the added line leaves the returned mapping
    alone is checked in `test_fork_touches_no_other_function.py`, which is
    where the real safety argument lives.
    """
    added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
    for l in added:
        assert not re.match(r"\s*def get_encoding\b", l), (
            "the fork redefines get_encoding: %r" % l)


# --------------------------------------------------------------------------
# R1 — ONE patch, ONE installer. The repo carried two byte-identical copies of
# each (`vendor/` and `src/pdfreader/`, md5 2a3d9c15…), and two more sat in
# ~/Downloads. A second copy of a patch is not redundancy: it is a copy that
# will not be rebased when the first one is, and the gate above only reads
# `vendor/`, so a stale duplicate would pass every test while being the one
# some script actually applies.
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def _repo_files(name: str) -> list:
    return [p for p in ROOT.rglob(name)
            if ".git" not in p.parts and ".pdfmm-build" not in p.parts
            and ".pdfmm-venv" not in p.parts]


def test_exactly_one_patch_in_the_repo():
    found = _repo_files("pdfminer-glyph-identity.patch")
    assert len(found) == 1, (
        "the fork must have ONE copy; found %d: %s"
        % (len(found), [str(p.relative_to(ROOT)) for p in found]))
    assert found[0] == PATCH, found[0]


def test_exactly_one_installer_in_the_repo():
    found = _repo_files("install-pdfminer-fork.sh")
    assert len(found) == 1, (
        "one installer; found %d: %s"
        % (len(found), [str(p.relative_to(ROOT)) for p in found]))
    assert found[0].parent.name == "vendor", (
        "the installer resolves the patch by $HERE, so it lives beside it")


def test_the_installer_finds_the_patch_beside_it():
    """`PATCH="$HERE/pdfminer-glyph-identity.patch"` — so moving one without
    the other leaves an installer that exits 2 at a path nobody reads."""
    sh = (ROOT / "vendor" / "install-pdfminer-fork.sh").read_text(
        encoding="utf-8", errors="replace")
    assert 'PATCH="$HERE/pdfminer-glyph-identity.patch"' in sh
    assert (PATCH.parent / "install-pdfminer-fork.sh").exists()


def test_nothing_still_points_at_the_old_location():
    """`pdf2mmd.sh` invoked `$HERE/install-pdfminer-fork.sh` from
    src/pdfreader/. After R1 that path does not exist, and a launcher that
    silently fails to build the fork is how a machine ends up running stock
    pdfminer and reporting `(cid:7)`."""
    for rel in ("src/pdfreader/pdf2mmd.sh",):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "install-pdfminer-fork.sh" in line and not line.strip().startswith("#"):
                assert "vendor/" in line, (rel, line)
