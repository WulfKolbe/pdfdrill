"""032 — every multi-document harness must be TOLD how many to take.

out/031.txt found six harnesses in tools/ that could each walk the whole
corpus from a bare invocation, and two of them advertised a `--limit` whose
default disabled it — which is worse than none, because it reads like a bound
and is not one.
"""
import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from harness_limit import add_limit, announce, apply_limit

HARNESSES = ["corpus_pages", "drillbatch", "make_libraryindex",
             "mathgold_floor", "route_matrix", "speak_library"]


def test_limit_is_required_and_zero_means_all():
    ap = argparse.ArgumentParser()
    add_limit(ap)
    a = ap.parse_args(["--limit", "3"])
    assert a.limit == 3
    assert apply_limit(range(10), 3) == [0, 1, 2]
    assert apply_limit(range(10), 0) == list(range(10))   # 0 = all, asked for
    import contextlib, io
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            ap.parse_args([])          # no --limit at all
            raise AssertionError("--limit must be required")
        except SystemExit:
            pass


def test_every_harness_from_031_refuses_to_run_unbounded():
    """The contract that matters: a bare invocation must not start work."""
    argv = {"drillbatch": ["x.pdf"], "mathgold_floor": ["m.json"],
            "route_matrix": ["x.pdf"]}
    for name in HARNESSES:
        p = subprocess.run([sys.executable, str(TOOLS / f"{name}.py")]
                           + argv.get(name, []),
                           capture_output=True, text=True, timeout=120)
        assert p.returncode != 0, f"{name} ran without --limit"
        assert "--limit" in (p.stderr + p.stdout), \
            f"{name} failed without naming --limit"


def test_announce_reports_documents_pages_and_what_it_cannot_know(tmp_path):
    import contextlib, io
    d = tmp_path / "docX"
    d.mkdir()
    (d / "docX.lines.json").write_text('{"pages": [{"page": 1}, {"page": 2}]}')
    unknown = tmp_path / "docY"
    unknown.mkdir()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        docs, pages, unk = announce("t", [d, unknown])
    out = buf.getvalue()
    assert (docs, pages, unk) == (2, 2, 1)
    assert "2 document(s)" in out and "2 page(s)" in out
    # a page count it cannot know is REPORTED, never guessed
    assert "not knowable locally" in out
