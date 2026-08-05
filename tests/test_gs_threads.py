"""Ghostscript must render multi-threaded — and banded, or the threads idle.

`-dNumRenderingThreads` only takes effect when gs renders the page in BANDS.
By default the whole page fits a single band, so the threads have nothing to
divide. Measured on a 6-page render at 400 DPI:

    default (one band, no threads)        3.44s
    -dNumRenderingThreads=8 alone         3.17s   (~8%, near noise)
    banded (-dMaxBitmap=8M) + threads=8   2.76s   (20%)
    banded alone                          3.45s   (nothing)

So the two flags are a PAIR; either alone is close to pointless. gs is on the
critical path of every raster route (inspect, OCR, vision, eqblobs), and the
invocation was duplicated across three call sites with none of them threaded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.pdf_reading import gs_render_args, RENDER_THREADS


def test_threads_and_banding_are_both_present():
    args = gs_render_args()
    joined = " ".join(args)
    assert f"-dNumRenderingThreads={RENDER_THREADS}" in joined
    assert any(a.startswith("-dMaxBitmap=") for a in args), \
        "threads without banding leaves them idle — the pair is the point"


def test_at_least_eight_threads():
    assert RENDER_THREADS >= 8, RENDER_THREADS


def test_args_are_render_only_no_device_or_output():
    """The helper must compose with each call site's own device/resolution/output,
    so it cannot silently override them."""
    joined = " ".join(gs_render_args())
    for owned in ("-sDEVICE", "-sOutputFile", "-r", "-dFirstPage", "-dLastPage"):
        assert owned not in joined, f"{owned} belongs to the caller: {joined}"


# ---------------------------------------------------------------------------
# Page-range PARALLELISM — the lever that actually matters on a scan.
#
# Ghostscript is single-threaded per render job, so extra cores only help by
# running several gs processes over DISJOINT page ranges. Measured on a
# 282-page scanned book, 32 pages at 400 DPI:
#
#     1 process, no threads      8.7s
#     1 process, threads=16      8.4s   (3% — nothing)
#      4 processes               2.5s   3.5x
#      8 processes               1.6s   5.3x
#     16 processes               1.4s   6.3x
#
# The trap: gs restarts its `%d` output counter at 1 for EVERY invocation, so
# parallel ranges sharing one `-sOutputFile=out/%03d.png` template overwrite
# each other. Verified: 2 jobs x 4 pages = 8 renders left 4 files on disk.
# Each shard therefore renders into its own directory and the files are moved
# to their true page numbers afterwards.
# ---------------------------------------------------------------------------
from pdfdrill.pdf_reading import plan_shards


def test_shards_cover_every_page_exactly_once():
    for n_pages, workers in ((32, 8), (500, 16), (7, 4), (1, 8), (100, 1)):
        pages = list(range(1, n_pages + 1))
        shards = plan_shards(pages, workers)
        flat = [p for s in shards for p in s]
        assert sorted(flat) == pages, (n_pages, workers, shards)
        assert len(flat) == len(set(flat)), "a page rendered twice is wasted work"


def test_shards_are_contiguous_ranges():
    """One gs call per shard means one PDF parse per shard; scattered pages
    would force a parse per page."""
    shards = plan_shards(list(range(1, 33)), 4)
    for s in shards:
        assert s == list(range(s[0], s[-1] + 1)), s


def test_no_more_shards_than_pages():
    assert len(plan_shards([1, 2, 3], 16)) == 3


def test_shards_are_balanced():
    shards = plan_shards(list(range(1, 101)), 8)
    sizes = [len(s) for s in shards]
    assert max(sizes) - min(sizes) <= 1, sizes


def test_a_shard_never_spans_a_gap():
    """A shard becomes ONE `-dFirstPage..-dLastPage` range, so a shard covering
    [3, 7] renders 3,4,5,6,7 — three pages nobody asked for. Measured before the
    fix: pages [3,7,11] with 2 workers produced 6 files.

    The page NUMBERS stayed correct, which is what made it easy to miss: the
    output looks right, there is just more of it than was requested.
    """
    for pages, workers in (([3, 7, 11], 2), ([1, 2, 9, 10], 2), ([5, 50], 1)):
        for shard in plan_shards(pages, workers):
            assert shard == list(range(shard[0], shard[-1] + 1)), (pages, shard)
            assert set(shard) <= set(pages), (pages, shard)


def test_contiguous_pages_still_shard_into_wide_ranges():
    """The gap rule must not fragment a normal request into per-page calls —
    one gs call per shard means one PDF parse per shard."""
    shards = plan_shards(list(range(1, 33)), 4)
    assert len(shards) == 4 and all(len(s) == 8 for s in shards), shards
