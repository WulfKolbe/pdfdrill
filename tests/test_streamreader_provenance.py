"""Every moved module names its pdf2mmd2 source commit, and differs ONLY by that.

T-0045's interface contract: "The moved files name their pdf2mmd2 source commit.
From this move on, pdfdrill holds the reader; pdf2mmd2 does not follow pdfdrill's
later changes."

The stamp claims the file is otherwise byte-identical to pdf2mmd2 at 5190249.
A claim in a comment that nothing checks is the kind of provenance that quietly
stops being true, so this test strips the stamp and compares the bytes against
the source checkout when it is present, and otherwise still enforces that every
module carries a stamp naming the same commit.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "streamreader"
SRC_COMMIT = "5190249"
SOURCE_CHECKOUT = Path.home() / "pdf2mmd2" / "src" / "pdf2mmd2"
STAMP_LINES = 4


def _modules():
    return sorted(PKG.glob("**/*.py"))


#: 213, not pdf2mmd2's 214: `drillcheck.py` is not here. Step 2b dropped it,
#: and `INVENTORY.md` had already decided "drop" for it in step 1 — it asked
#: "does pdfdrill accept what pdf2mmd2 writes?", a question that stops existing
#: once the reader IS pdfdrill's. It also made the suite red, by
#: defaulting twice into the owner's own checkout where T-0078 forbids it. The
#: path is not spelled here, for the reason the rule exists: this file is inside
#: its own scope, and writing it out once made the suite red a second time —
#: measured. That could not be fixed in place: the file is byte-locked to
#: pdf2mmd2@5190249 by the tests below, and T-0078's own allowlist "may only
#: shrink", so there was no edit and no exemption to reach for. The two
#: contracts only collide on a file that should never have been ported.
MOVED_MODULES = 213


def test_the_package_is_here_and_whole():
    mods = _modules()
    assert len(mods) == MOVED_MODULES, (
        f"expected {MOVED_MODULES} moved modules, found {len(mods)}")


def test_the_development_tools_that_were_dropped_are_gone():
    """A dropped module must not come back with the next sync from pdf2mmd2.

    `drillcheck` is the one dropped so far, and it is named here rather than in
    a comment because a decision no test holds is a decision that gets undone
    by a future `cp -r`.
    """
    assert not (PKG / "drillcheck.py").is_file(), (
        "src/streamreader/drillcheck.py is back; it was dropped in T-0045 step 2b")
    namers = [p.relative_to(ROOT) for p in _modules()
              if "drillcheck" in p.read_text(encoding="utf-8")]
    assert not namers, f"the reader still reaches for drillcheck: {namers}"


def test_every_module_names_its_source_commit():
    bad = [p.relative_to(ROOT) for p in _modules()
           if not p.read_text(encoding="utf-8").startswith("# Moved into pdfdrill")]
    assert not bad, f"{len(bad)} module(s) carry no provenance stamp: {bad[:5]}"


def test_every_stamp_names_the_same_commit():
    for p in _modules():
        head = p.read_text(encoding="utf-8").split("\n", 1)[0]
        assert SRC_COMMIT in head, f"{p.name}: stamp does not name {SRC_COMMIT}: {head!r}"


def test_stripping_the_stamp_reproduces_the_source_bytes():
    """The stamp's own claim, checked. Skipped where the source checkout is not
    on this machine — then the two tests above are what hold."""
    if not SOURCE_CHECKOUT.is_dir():
        pytest.skip(f"no pdf2mmd2 checkout at {SOURCE_CHECKOUT}")
    import subprocess
    at = subprocess.run(["git", "-C", str(SOURCE_CHECKOUT.parents[1]), "rev-parse", "--short=7", "HEAD"],
                        capture_output=True, text=True)
    if at.returncode != 0 or at.stdout.strip() != SRC_COMMIT:
        pytest.skip(f"pdf2mmd2 checkout is at {at.stdout.strip()!r}, not {SRC_COMMIT}")
    differing = []
    for p in _modules():
        rel = p.relative_to(PKG)
        src = SOURCE_CHECKOUT / rel
        if not src.is_file():
            differing.append(f"{rel}: no source counterpart")
            continue
        moved = p.read_text(encoding="utf-8").split("\n", STAMP_LINES)[STAMP_LINES]
        if moved != src.read_text(encoding="utf-8"):
            differing.append(str(rel))
    assert not differing, (
        f"{len(differing)} moved module(s) differ from pdf2mmd2@{SRC_COMMIT} by more "
        f"than the stamp — the provenance line is no longer true: {differing[:5]}")


def test_the_generated_font_tables_came_with_their_generator():
    """T-0038, the owner's constraint: no TeX Live at run time for the fonts
    covered. A generated table without its generator cannot be re-derived."""
    fm = PKG / "ported" / "fontmetrics"
    tables = list(fm.glob("f_*.py"))
    assert len(tables) == 155, f"expected 155 generated font tables, found {len(tables)}"
    assert (fm / "gen.py").is_file(), "the font tables arrived without gen.py"
    assert (PKG / "ported" / "appg" / "tfm.py").is_file(), "gen.py's TFM reader did not come"


def test_the_symbol_table_came_with_its_generator():
    assert (PKG / "ported" / "latexsyms_table.py").is_file()
    assert (PKG / "ported" / "latexsyms.py").is_file(), (
        "the symbol table arrived without the generator that derives it from LaTeX")
