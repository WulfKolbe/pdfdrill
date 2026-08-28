r"""A TeX math alphabet is an alphabet, not a font with gaps.

rsfs10 (\mathscr) carries A-Z and nothing else. Asking it for a lowercase
letter drops the letter SILENTLY — a PDF that looks finished and is missing
characters, which is the failure GlyphsDropped exists to refuse.

2103.01507 is the measured case. Its author wrote

    \DeclareMathOperator{\cMap}{\mathstscr{M\mkern-4mu a\mkern-3.5mu p}}

and MathPix read the script "Map" off the page as `\mathscr{M a p}` — a
faithful transcription of what is printed. 11 of that report's 12 dropped
glyphs were the `a` and `p` of five such rows.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pdfdrill.report_tex import alphabet_safe, renderable, glyph_loss_advice


@pytest.mark.parametrize("raw,want", [
    (r"\mathscr{M a p}", r"\mathscr{M}\mathit{a}\mathit{p}"),
    (r"\mathscr{M a}", r"\mathscr{M}\mathit{a}"),
    (r"\mathscr{Map}", r"\mathscr{M}\mathit{a}\mathit{p}"),
    # uppercase-only arguments are left exactly alone
    (r"\mathscr{F}", r"\mathscr{F}"),
    (r"\mathscr{ABC}", r"\mathscr{ABC}"),
    ("", ""),
])
def test_only_the_letters_the_alphabet_lacks_are_moved(raw, want):
    assert alphabet_safe(raw) == want


@pytest.mark.parametrize("raw", [
    r"\mathfrak{m}", r"\mathfrak{S}_n", r"\mathfrak{map}",
])
def test_mathfrak_is_untouched_because_eufm10_has_lowercase(raw):
    """The note on _TEX_MATH_FONTS said "rsfs10 and eufm10 have no lowercase".
    eufm10 does: `$\mathfrak{m}\mathfrak{a}\mathfrak{p}$` compiles with zero
    missing characters, and 2103.01507's own \mathfrak{m} drew no warning in a
    log that names every other drop. Rewriting it would break correct fraktur
    to fix a defect it does not have."""
    assert alphabet_safe(raw) == raw


def test_the_rest_of_the_expression_survives():
    assert alphabet_safe(r"\mathscr{F} + \mathscr{M a p}(X,Y)") == \
        r"\mathscr{F} + \mathscr{M}\mathit{a}\mathit{p}(X,Y)"


def test_it_runs_inside_renderable():
    assert r"\mathit{a}" in renderable(r"\mathscr{M a p}(X,Y)")


def test_the_source_column_is_not_what_this_touches():
    """alphabet_safe feeds the RENDERED cell only. The Source column shows
    MathPix's characters verbatim, so the page still says what MathPix
    produced — the rewrite is a rendering decision, not a transcription edit."""
    import inspect
    from pdfdrill import report_tex
    src = inspect.getsource(report_tex.row)
    assert "esc_text(latex)" in src          # source cell: raw
    assert "renderable(latex)" in src        # rendered cell: rewritten


def test_the_advice_no_longer_claims_eufm10_lacks_lowercase():
    a = glyph_loss_advice('Missing character: There is no g ("67) in font rsfs10')
    assert "rsfs10 has no lowercase" in a
    assert "change the command, not the font" in a
