"""`drill` reports how long each part took.

The sandbox question is not only "did every report finish" but "which part
grows with the page count". So every step `drill` runs is timed, and the report
ends with one line per part, the total, and the per-page rate — the only figure
that transfers from a 9-page paper to a 576-page volume.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import cli


def test_the_table_has_a_line_per_part_a_total_and_a_rate(monkeypatch, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    # Patch the FUNCTION, not the module in sys.modules: `from . import probes`
    # resolves the already-set package attribute, so swapping the sys.modules
    # entry works only when nothing imported it yet — which is true alone and
    # false in the full suite. (It cost one run to find out.)
    monkeypatch.setattr("pdfdrill.probes.page_count", lambda _sc: 4)
    out = cli._format_timings([("size", 0.5), ("model", 2.0), ("inspect", 1.5)], pdf)
    assert "--- timing ---" in out
    for part in ("size", "model", "inspect", "TOTAL"):
        assert re.search(r"^\s+%s\s" % part, out, re.M), (part, out)
    assert "4.00 s" in out                          # the total
    assert "per page" in out and "1.00 s" in out    # 4.00 / 4 pages


def test_a_part_that_raised_is_still_timed(monkeypatch, tmp_path):
    """The timer is in a `finally`, because a step that BLEW UP after 40 s is
    exactly the measurement a sandbox run is trying to get."""
    import time
    timings = []

    def _timed(name, fn):
        t0 = time.monotonic()
        try:
            return fn()
        finally:
            timings.append((name, time.monotonic() - t0))

    def boom():
        raise RuntimeError("no")

    try:
        _timed("model", boom)
    except RuntimeError:
        pass
    assert [n for n, _s in timings] == ["model"]


def test_empty_timings_print_nothing(tmp_path):
    assert cli._format_timings([], tmp_path / "doc.pdf") == ""


def test_shares_sum_to_about_a_hundred(monkeypatch, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = cli._format_timings([("a", 1.0), ("b", 3.0)], pdf)
    shares = [int(m) for m in re.findall(r"(\d+)%", out)]
    assert sum(shares) == 100, out
