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
