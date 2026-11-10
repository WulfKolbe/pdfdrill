"""An unguarded \\newfontfamily for an absent font aborts the whole compile.

THE PREAMBLE ALREADY KNEW THIS AND GUARDED THE WRONG LINE. Two declarations
sat next to each other in `report_tex`:

    \\newfontfamily\\fbcjk{Noto Sans CJK JP}                      <- unguarded
    %% 221: Bengali has no other home here. Guarded, because an unguarded
    %% \\newfontfamily for a font this machine lacks aborts the compile and
    %% produces NO pdf -- worse than the dropped glyph it exists to prevent.
    \\IfFontExistsTF{Noto Sans Bengali}{...}{...}                 <- guarded

Bengali carries the reason in its own comment; the CJK line above it was
left bare, and `Noto Sans CJK JP` is exactly the font nopi, ser7 and peladn
do not have (fc-match resolves it to plain "Noto Sans" on all three; beelink
has the real face).

WHAT IT COST, measured 2026-11-04. On nopi the measure-phase compile died at
the fontspec error with "No pages of output", leaving report.pdf truncated
at 99,097 bytes with no xref, no startxref and no %%EOF. Four layers later
the run reported

    STOPPED at step 3 (measure): RegionInkRefused: ghostscript wrote no
    raster for page 1 of report.pdf at 300 dpi: Catalog dictionary not
    located in file, unable to proceed

-- a ghostscript message about a PDF, for a missing font. Seven documents on
nopi, 1,375 rows in one of them, and the same documents measure cleanly on
beelink. Four hypotheses were tested and refuted on the way to it
(concurrency, the ghostscript version, the missing font as a *requested*
font, and CJK glyphs in the document) before the measure-phase .tex was
captured and compiled by hand.

The fix is the guard the next line already uses. A machine without the font
then drops the character and `glyphs_dropped()` says so, which is a failure
that can be seen, instead of one that surfaces as a corrupt PDF.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from pdfdrill import report_tex as rt


#: Fonts the project may legitimately demand outright: a machine without
#: these cannot typeset a report at all, so failing loudly is correct.
REQUIRED = ("DejaVu Serif", "DejaVu Sans Mono")


def _newfontfamily_lines(tex: str) -> list:
    return [ln for ln in tex.splitlines()
            if "\\newfontfamily" in ln and not ln.lstrip().startswith("%")]


def _preamble() -> str:
    """The report preamble as the template defines it, markers and all."""
    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    m = re.search(r"\\usepackage\[no-math\]\{fontspec\}.*?\\setlength\{\\parindent\}",
                  src, re.S)
    assert m, "the fontspec block moved; this test must follow it"
    return m.group(0)


def test_every_optional_fallback_font_is_guarded_in_the_report_preamble():
    for ln in _newfontfamily_lines(_preamble()):
        font = re.search(r"\\newfontfamily\\\w+\{([^}]*)\}", ln)
        assert font, ln
        if font.group(1) in REQUIRED:
            continue
        assert "\\IfFontExistsTF" in ln, (
            "unguarded \\newfontfamily for the optional font %r: on a machine "
            "without it xelatex writes No pages of output and the truncated "
            "report.pdf surfaces as a ghostscript error four layers later"
            % font.group(1))


def test_every_optional_fallback_font_is_guarded_in_the_unicode_preamble():
    from pdfdrill import commands
    tex = commands._unicode_preamble(r"\text{日本語}") \
        if hasattr(commands, "_unicode_preamble") else None
    if not tex:
        pytest.skip("the unicode preamble helper is not exposed under that name")
    for ln in _newfontfamily_lines(tex):
        font = re.search(r"\\newfontfamily\\\w+\{([^}]*)\}", ln)
        assert font, ln
        if font.group(1) in REQUIRED:
            continue
        assert "\\IfFontExistsTF" in ln, (
            "unguarded \\newfontfamily for %r in the unicode preamble"
            % font.group(1))


def test_a_guarded_font_still_defines_its_command_when_absent():
    """The else-branch must define the macro, or every use is an undefined
    control sequence -- which aborts the compile just as surely."""
    for ln in _newfontfamily_lines(_preamble()):
        if "\\IfFontExistsTF" not in ln:
            continue
        cmd = re.search(r"\\newfontfamily(\\\w+)\{", ln)
        assert cmd, ln
        name = cmd.group(1)
        tail = ln.split("}{", 1)[1] if "}{" in ln else ""
        assert name in tail, (
            "%s is defined only when the font exists; the absent branch must "
            "define it too" % name)
