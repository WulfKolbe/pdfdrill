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


def test_it_does_not_touch_get_encoding(lines):
    """The Unicode channel every existing caller reads must be left exactly as
    it is — that is what makes the fork safe to adopt globally."""
    added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
    for l in added:
        assert not re.match(r"\s*def get_encoding\b", l), (
            "the fork redefines get_encoding: %r" % l)
