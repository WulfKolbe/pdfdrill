"""`columns(page)` was cached under `id(page)`, and CPython reuses addresses.

Found while classifying ONE "order-dependent" failure in a base-install run
(`test_mmd.py::TestDisplayContinuation::test_the_head_is_claimed_by_its
_continuation`: `assert 0 == 1` in the full suite, passing when run alone, and
never failing on the development machine). Test pollution was the obvious
reading and it was wrong — nothing in the suite mutates any shared state here.

`column_of` memoised the page's column bounds in a MODULE-LEVEL dict keyed by
`id(page)`. A freed PageNode's address is handed straight to the next one, so
the cache answered a NEW page with an OLD page's columns. Measured before the
fix:

  * 400 freshly built PageNodes occupied **14 distinct addresses** — 386 of
    them were answered from another page's entry.
  * alternating two geometries whose displays sit 300pt apart, the same
    geometry got `mark_display_continuations` = 1 or 0 by turns: **258 flips in
    400 calls.**

The test failure is the cheapest symptom this defect has. In a long-lived
process (drillui, a corpus pass) it silently mis-columns pages instead, and the
column decides `is_display`, which decides whether an equation is a display or
a run of inline prose.

The cache now lives ON the page, so it cannot outlive it or be handed to a
stranger. These tests are about the KEY, not about the columns: they must fail
for any cache that a new object can inherit.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import docmodel_six as D, project_mmd as M, texmap   # noqa: E402


def _mathline(lid, x0, baseline, chars, size=12.0):
    glyphs, x = [], x0
    for ch in chars:
        glyphs.append(D.GlyphNode(
            id=f"{lid}g{x}", page=1,
            rect=(x, baseline, x + 6.0, baseline + size),
            text=ch, cid=0, glyphname=None, fontname="ABC+CMMI12",
            family="math-italic", size=size,
            tex=texmap.TexToken(ch, "atom", None, "corpus"),
            matrix=(size, 0, 0, size, x, baseline)))
        x += 8.0
    return D.LineNode(id=lid, page=1,
                      rect=(x0, baseline, x, baseline + size),
                      type="formula", glyphs=glyphs)


def _page(dx: float):
    """One display over two rows, shifted `dx` to the right as a whole."""
    return D.PageNode(page=1, rect=(0.0, 0.0, 612.0, 792.0),
                      lines=[_mathline("l1", 104.0 + dx, 600.0, list("y=a")),
                             _mathline("l2", 140.0 + dx, 580.0, list("-b"))])


def test_one_geometry_always_gets_one_answer():
    """THE CASE BUILT TO FAIL. Two geometries in turn, each page dropped at the
    end of its iteration so its address is free for the next one."""
    answers: dict[float, set] = {0.0: set(), 300.0: set()}
    for _ in range(200):
        for dx in (0.0, 300.0):
            page = _page(dx)
            answers[dx].add(M.mark_display_continuations(page))
            del page
    for dx, got in answers.items():
        assert got == {1}, (
            f"the display shifted by {dx}pt was read {len(got)} different ways "
            f"in 200 identical calls ({sorted(got)}) — the column cache is "
            f"answering one page from another page's entry")


def test_the_columns_a_page_is_given_are_its_own():
    """Directly: a fresh page must never be handed a cached answer."""
    first = _page(0.0)
    cols_first = M.column_of(first, first.lines[0])
    del first
    seen = set()
    for _ in range(300):
        page = _page(300.0)
        seen.add(M.column_of(page, page.lines[0]))
        del page
    assert len(seen) == 1, (
        f"the same page geometry got {len(seen)} different columns: {seen}")
    assert seen != {cols_first}, (
        "the shifted page was given the UNSHIFTED page's columns — the cache "
        "survived the object it belonged to")


def test_the_cache_dies_with_the_page():
    """No module-level growth, and nothing left to inherit."""
    before = len(M._COLS_CACHE)
    for _ in range(50):
        page = _page(0.0)
        M.column_of(page, page.lines[0])
        del page
    assert len(M._COLS_CACHE) == before, (
        "a module-level cache is still accumulating page entries, so an "
        "address handed on by the allocator still carries an answer with it")


def test_the_memo_still_memoises():
    """The cache is not merely removed: `columns()` is the expensive part and
    is called once per page, not once per line."""
    page = _page(0.0)
    calls = []
    real = M.columns
    try:
        M.columns = lambda p: calls.append(p) or real(p)
        for ln in page.lines:
            M.column_of(page, ln)
        M.column_of(page, page.lines[0])
    finally:
        M.columns = real
    assert len(calls) == 1, f"columns() ran {len(calls)}x for one page"
