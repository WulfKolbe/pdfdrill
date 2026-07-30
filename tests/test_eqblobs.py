"""Geometry pass: synthetic pages, so the assertions are exact and keyless."""
from pathlib import Path

from pdfdrill import eqblobs as eb


def _pgm(path: Path, w: int, h: int, bands) -> Path:
    """White page with black bars: bands = [(y0, y1, x0, x1), ...]."""
    px = bytearray(b"\xff" * (w * h))
    for y0, y1, x0, x1 in bands:
        for y in range(y0, y1):
            px[y * w + x0:y * w + x1] = b"\x00" * (x1 - x0)
    path.write_bytes(b"P5\n%d %d\n255\n" % (w, h) + bytes(px))
    return path


def test_projection_profile_keeps_a_tall_band_separate(tmp_path):
    """The pairwise-overlap grouping merged a tall equation into the prose line
    above it, so no line was ever short-and-centred and nothing was detected."""
    bands = [(10, 20, 20, 380),      # full-width prose
             (24, 60, 150, 250),     # tall + centred: the equation
             (64, 74, 20, 380)]      # full-width prose
    p = _pgm(tmp_path / "a.pgm", 400, 100, bands)
    geo = eb.analyse_page(str(p), page=1, dpi=72)
    assert geo.line_count == 3, geo.line_count
    assert len(geo.equations) == 1, [e.as_dict() for e in geo.equations]
    eq = geo.equations[0]
    assert eq.height_ratio > 1.5 and "centred" in eq.reason


def test_plain_prose_yields_no_equation():
    """Uniform full-width lines must produce nothing -- a false positive costs a
    spurious region, so the bar stays high."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        bands = [(10 + 14 * i, 20 + 14 * i, 20, 380) for i in range(6)]
        p = _pgm(Path(d) / "b.pgm", 400, 120, bands)
        geo = eb.analyse_page(str(p), page=2, dpi=72)
        assert geo.line_count == 6
        assert geo.equations == []


def test_regions_are_reported_in_pdf_points():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _pgm(Path(d) / "c.pgm", 300, 300, [(0, 10, 0, 300)])
        geo = eb.analyse_page(str(p), page=1, dpi=300)
        # 300 px at 300 DPI is exactly 72 pt
        assert abs(geo.width_pt - 72.0) < 0.01
        assert abs(geo.height_pt - 72.0) < 0.01


def test_missing_page_is_skipped_not_fatal(tmp_path):
    """A page past the end makes gs write nothing; the run must continue."""
    out = eb.analyse_pdf(Path("/nonexistent.pdf"), [1], tmp_path, dpi=72)
    assert out == []
