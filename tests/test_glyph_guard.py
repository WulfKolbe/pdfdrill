"""091 — a compile that drops characters must not pass as a success."""
from pdfdrill.report_tex import GlyphsDropped, glyphs_dropped


def test_both_log_formats_are_matched(tmp_path):
    """fontspec fonts say (U+XXXX); TFM fonts say ("XXXX). out/089 matched only
    the first and therefore never saw the cmmi10 losses, which were the
    majority — a check that passes because it cannot see the failure."""
    p = tmp_path / "a.log"
    p.write_text('Missing character: There is no s ("3C3) in font cmmi10!\n'
                 'Missing character: There is no x (U+21D2) in font [lm]\n')
    n, first = glyphs_dropped(p)
    assert n == 2


def test_inputenc_form_is_matched_too(tmp_path):
    p = tmp_path / "b.log"
    p.write_text("Unicode character not set up for use with LaTeX.")
    assert glyphs_dropped(p)[0] == 1


def test_a_clean_log_is_None_not_zero(tmp_path):
    """None and 0 must not be confused: callers branch on truthiness, and a
    count of 0 would read as 'checked and clean' identically to 'no log'."""
    p = tmp_path / "c.log"
    p.write_text("Output written on report.pdf (3 pages).")
    assert glyphs_dropped(p) is None


def test_missing_log_does_not_raise(tmp_path):
    assert glyphs_dropped(tmp_path / "nope.log") is None


def test_exception_names_the_count_and_the_remedy():
    e = GlyphsDropped("/x/report.log", 94, 'no s ("3C3)')
    assert "94" in str(e) and "_MATH_CMD" in str(e) and "report.log" in str(e)
