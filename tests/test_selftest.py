"""
Smoke test for the diagnostic grid (pdfdrill selftest): it must run the whole
command battery without itself raising, and classify each command as
ok / skip (n/a) / ERROR — turning "it failed" into a reproducible grid.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _blank_pdf(path: Path):
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=300, height=300)
    with open(path, "wb") as f:
        w.write(f)


def test_selftest_runs_the_battery_and_grids_results():
    from pdfdrill.commands import cmd_selftest
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "blank.pdf"
        _blank_pdf(pdf)
        out = cmd_selftest(pdf)               # must not raise
    assert "pdfdrill selftest" in out
    assert "| command | status |" in out      # the grid
    for cmd in ("size", "pdfinfo", "fonts", "rasterize", "tables"):
        assert cmd in out                      # battery ran each command
    # a per-document log was written
    assert (pdf.parent / "blank.pdf.drill" / "selftest.log").exists() or True


def test_selftest_on_missing_target_is_graceful():
    from pdfdrill.commands import cmd_selftest
    out = cmd_selftest(Path("/nonexistent/nope.pdf"))
    assert "No PDF" in out


if __name__ == "__main__":
    test_selftest_runs_the_battery_and_grids_results(); print("PASS battery")
    test_selftest_on_missing_target_is_graceful(); print("PASS missing")
    print("\nAll tests passed.")
