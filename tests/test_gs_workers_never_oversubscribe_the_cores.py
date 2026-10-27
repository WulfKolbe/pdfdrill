r"""One `pdfdrill evidence` forked 241 Ghostscript processes and took the load
average to 137 on 16 cores. This pins the arithmetic that let it.

Owner's word, 2026-10-27, relayed by gemma4-ba: "limit pdfdrill's gs workers so
they don't oversubscribe the cores". They had seen more than 16 gs at once.

THE DEFECT, as it stood:

    RENDER_THREADS = max(8, min(os.cpu_count() or 8, 16))   # 16 on this box
    RENDER_WORKERS = max(1, min(os.cpu_count() or 4, 16))   # 16 on this box

`rasterize` shards the pages across `RENDER_WORKERS` gs processes, and EVERY one
of them is handed `-dNumRenderingThreads=RENDER_THREADS`. So a single rasterize
call asks for 16 x 16 = 256 rendering threads on 16 cores, and two pdfdrill runs
at once double that. The two constants were each defensible alone and were never
multiplied together by anyone.

Two further things both constants got wrong:

* `os.cpu_count()` reports the MACHINE, not this process's share. A run pinned
  with `taskset -c 8-15` still started 16 workers of 16 threads. The drillgroup
  core split (cores 4-7 are GLYPHDRILL's) was therefore unenforceable from
  outside: pinning pdfdrill did not make pdfdrill smaller.
* `max(8, ...)` makes 8 threads the FLOOR. On a 2-core container that is 4x
  oversubscription before any sharding at all.

WHAT IS NOT CHANGED, deliberately. The measurement in the module's own comment
says sharding is the 6.3x lever and `-dNumRenderingThreads` pays about 20% on
text pages, so the budget is spent on workers first and threads get what is
left. A one-page render still gets one process with every core's worth of
threads — that is the case the old code was accidentally right about, and it is
pinned below so a future tidy-up cannot quietly lose it.

These tests assert the INVARIANT (workers x threads <= the cores we may use),
not the numbers. A test that pinned `workers == 16` would have passed on the
broken code.
"""
from __future__ import annotations

import os

import pytest

from pdfdrill import pdf_reading as R


def _affinity(monkeypatch, cores: int, machine: int = 16):
    """This process may use `cores`; the machine has `machine`."""
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: set(range(cores)),
                        raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: machine)


def _no_env(monkeypatch):
    monkeypatch.delenv("PDFDRILL_GS_WORKERS", raising=False)
    monkeypatch.delenv("PDFDRILL_GS_THREADS", raising=False)


# ---------------------------------------------------------------- the invariant

@pytest.mark.parametrize("cores", [1, 2, 3, 4, 7, 8, 15, 16, 32])
@pytest.mark.parametrize("pages", [1, 2, 3, 5, 9, 16, 32, 282])
def test_workers_times_threads_never_exceeds_the_cores_we_may_use(
        monkeypatch, cores, pages):
    """THE ONE THAT MATTERS. 16 x 16 on 16 cores is what the owner saw."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, cores)
    workers, threads = R.render_plan(pages)
    assert workers >= 1 and threads >= 1
    assert workers * threads <= cores, (
        "%d workers x %d threads on %d cores" % (workers, threads, cores))


def test_the_old_arithmetic_is_now_impossible(monkeypatch):
    """The exact shape of the defect: 16 cores, a document with many pages."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, 16)
    workers, threads = R.render_plan(282)
    assert workers * threads <= 16
    assert (workers, threads) != (16, 16)


# ------------------------------------------------------------- the taskset pin

def test_a_taskset_pin_is_honoured(monkeypatch):
    """`taskset -c 8-15 pdfdrill ...` on a 16-core box: four cores' worth of
    affinity must produce four cores' worth of gs, not sixteen. This is what
    makes the drillgroup core split enforceable from outside."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, 4, machine=16)
    workers, threads = R.render_plan(282)
    assert workers * threads <= 4
    assert workers <= 4


def test_the_core_count_comes_from_the_affinity_mask_not_the_machine(monkeypatch):
    _no_env(monkeypatch)
    _affinity(monkeypatch, 4, machine=16)
    assert R.render_cores() == 4


def test_the_core_count_falls_back_when_there_is_no_affinity_call(monkeypatch):
    """`os.sched_getaffinity` is Linux-only; the fallback must not be zero."""
    _no_env(monkeypatch)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert R.render_cores() == 8
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert R.render_cores() >= 1


# ------------------------------------------------- where the budget is spent

def test_one_page_gets_one_process_with_every_core(monkeypatch):
    """The case the OLD code was right about, and the module's own measurement
    says why: on a single shard, threads are the only lever there is."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, 16)
    assert R.render_plan(1) == (1, 16)


def test_many_pages_spend_the_budget_on_workers(monkeypatch):
    """Sharding is 6.3x, threads ~20% — so workers get the cores."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, 16)
    workers, threads = R.render_plan(282)
    assert workers == 16 and threads == 1


def test_workers_never_exceed_the_pages_there_are(monkeypatch):
    """Three pages cannot use sixteen gs processes; the spare cores go to
    threads instead of being wasted."""
    _no_env(monkeypatch)
    _affinity(monkeypatch, 16)
    workers, threads = R.render_plan(3)
    assert workers == 3
    assert workers * threads <= 16


def test_a_single_core_still_renders(monkeypatch):
    _no_env(monkeypatch)
    _affinity(monkeypatch, 1)
    assert R.render_plan(282) == (1, 1)


# ------------------------------------------------------------ the env overrides

def test_the_env_overrides_lower_the_budget(monkeypatch):
    _affinity(monkeypatch, 16)
    _no_env(monkeypatch)
    monkeypatch.setenv("PDFDRILL_GS_WORKERS", "4")
    workers, threads = R.render_plan(282)
    assert workers == 4
    assert workers * threads <= 16


def test_an_override_can_never_raise_the_budget(monkeypatch):
    """A cap that can be turned up is not a cap. This is the whole point of the
    change: no environment variable may reintroduce the defect."""
    _affinity(monkeypatch, 4, machine=64)
    _no_env(monkeypatch)
    monkeypatch.setenv("PDFDRILL_GS_WORKERS", "64")
    monkeypatch.setenv("PDFDRILL_GS_THREADS", "64")
    workers, threads = R.render_plan(282)
    assert workers * threads <= 4, (workers, threads)


@pytest.mark.parametrize("bad", ["", "0", "-1", "nonsense", "3.5"])
def test_a_junk_override_is_ignored_rather_than_crashing_the_render(
        monkeypatch, bad):
    """gs sits on the critical path of every raster route; a typo in a shell
    export must not take the render down with it."""
    _affinity(monkeypatch, 16)
    _no_env(monkeypatch)
    monkeypatch.setenv("PDFDRILL_GS_WORKERS", bad)
    workers, threads = R.render_plan(282)
    assert workers >= 1 and threads >= 1
    assert workers * threads <= 16


# ------------------------------------------------------------- the gs flags

def test_the_thread_flag_carries_the_planned_count(monkeypatch):
    _affinity(monkeypatch, 16)
    _no_env(monkeypatch)
    joined = " ".join(R.gs_render_args(threads=2))
    assert "-dNumRenderingThreads=2" in joined


def test_gs_render_args_still_works_with_no_argument(monkeypatch):
    """`eqblobs` calls it bare for a SINGLE gs, and must keep working. Bare
    means "I am the only gs", so it gets the cores — but never more than the
    affinity mask allows, which is more than the old floor of 8 promised."""
    _affinity(monkeypatch, 2, machine=16)
    _no_env(monkeypatch)
    joined = " ".join(R.gs_render_args())
    assert "-dNumRenderingThreads=2" in joined, joined


def test_the_banding_flag_stays_paired_with_the_threads(monkeypatch):
    """The module's measurement: banded alone does nothing, threads alone ~8%,
    the pair 20%. Dropping one silently halves the other."""
    _affinity(monkeypatch, 16)
    _no_env(monkeypatch)
    joined = " ".join(R.gs_render_args())
    assert "-dMaxBitmap=" in joined and "-dNumRenderingThreads=" in joined


def test_eight_is_no_longer_a_floor(monkeypatch):
    """`max(8, ...)` meant a 2-core container asked for 8 threads per process.
    The floor was the defect, not a safety net."""
    _affinity(monkeypatch, 2, machine=2)
    _no_env(monkeypatch)
    workers, threads = R.render_plan(282)
    assert workers * threads <= 2
    assert threads < 8


# ------------------------------------------------- the render actually uses it

def test_rasterize_shards_by_the_planned_worker_count(monkeypatch, tmp_path):
    """The plan is worthless if `rasterize` still reads a module constant.
    This catches the half-done change: new arithmetic, old call site."""
    _affinity(monkeypatch, 4, machine=16)
    _no_env(monkeypatch)
    seen = {}

    def fake_plan(pages, workers):
        seen["workers"] = workers
        return [list(pages)]

    monkeypatch.setattr(R, "plan_shards", fake_plan)
    monkeypatch.setattr(R, "_require_gs", lambda: "/usr/bin/gs")
    monkeypatch.setattr(R, "_render_shard",
                        lambda *a, **k: None)
    R.rasterize(tmp_path / "x.pdf", tmp_path / "out", pages=[1, 2, 3, 4, 5, 6])
    assert seen["workers"] <= 4, seen


def test_the_thread_count_the_shards_are_given_matches_the_plan(
        monkeypatch, tmp_path):
    """Both halves of the product must come from ONE decision. The defect was
    two independent constants, so this asserts they are no longer independent."""
    _affinity(monkeypatch, 4, machine=16)
    _no_env(monkeypatch)
    workers, threads = R.render_plan(6)
    captured = {}

    monkeypatch.setattr(R, "_require_gs", lambda: "/usr/bin/gs")
    monkeypatch.setattr(R, "_render_shard",
                        lambda base, *a, **k: captured.setdefault("base", base))
    R.rasterize(tmp_path / "x.pdf", tmp_path / "out", pages=list(range(1, 7)))
    base = " ".join(str(x) for x in captured.get("base", []))
    assert "-dNumRenderingThreads=%d" % threads in base, base
    assert workers * threads <= 4
