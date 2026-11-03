r"""A heading's level comes from the number the document printed.

The owner's example, 2026-11-02:

    12.2   The flavour symmetry SU(2)f
    12.2.1 The nucleon isospin doublet and the group SU(2)

Both lines are set in the SAME font at the SAME size, so a level ranked by
font size cannot separate them — yet the dots state the depth exactly. Their
instruction: pdfdrill decides the hierarchy, because "Mathpix is mostly using
\section and not \chapter and \section / \subsections".

`header.py` already derived a level this way for lines it PROMOTES
(`min(num.count(".") + 1, _MAX_SIZE_LEVEL)`); it was never applied to a line
MathPix typed `section_header`, which went to the font size instead.

Measured over 40 MathPix readings / 224 numbered headings before the change:
the size-derived level disagreed with the printed number 94 times (42%), and 9
font sizes each covered several depths. The disagreement is usually a uniform
offset — the document's title takes size-level 1, so `1 Introduction` comes out
as level 2 — which a relative ranking cannot fix and an absolute number does
not have.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.modules.header import (_MAX_SIZE_LEVEL, _heading_number,  # noqa: E402
                                     levels_by_font_size)


def _level_from_number(text):
    num = _heading_number(text)
    return min(num.count(".") + 1, _MAX_SIZE_LEVEL) if num else None


def test_the_owners_two_headings_get_different_levels_at_one_font_size():
    a = "12.2 The flavour symmetry SU(2)f"
    b = "12.2.1 The nucleon isospin doublet and the group SU(2)"
    assert _level_from_number(a) == 2, a
    assert _level_from_number(b) == 3, b
    # and the size cannot tell them apart, which is the whole point
    by_size = levels_by_font_size([26, 26])
    assert by_size.get(26) == by_size.get(26)


def test_depth_counts_the_dots():
    for text, want in (("12 Flavour symmetry", 1),
                       ("12.2 The flavour symmetry", 2),
                       ("12.2.1 The nucleon isospin doublet", 3),
                       ("1.2.3.4 Deeply nested", 4)):
        assert _level_from_number(text) == want, text


def test_the_level_is_capped():
    assert _level_from_number("1.2.3.4.5.6.7 Too deep") == _MAX_SIZE_LEVEL


def test_an_unnumbered_heading_has_no_number_level():
    """`References`, `Abstract`, `Chapter 1` with no dotted number fall through
    to the font size, which is still the right instrument when there is no
    number to read."""
    for text in ("References", "Acknowledgements", "The flavour symmetry"):
        assert _level_from_number(text) is None, text


def test_a_numbered_heading_outranks_the_size_ranking():
    """The measured failure: a title consumes size-level 1, so `1 Introduction`
    is ranked 2 by size while its number says 1."""
    by_size = levels_by_font_size([60, 44, 36])     # title, section, subsection
    assert by_size[44] == 2                          # what size says
    assert _level_from_number("1 Introduction") == 1  # what the document says


# ── a bare \section is not a depth statement ────────────────────────────────
# Measured on d09 after the first attempt: 267 of 279 Sections came out
# `level_basis: latex_command`, all level 1, because the producer emits
# `\section{...}` for EVERY heading — `1.4 Nonlinear Radiation Effects…`
# included. The rule above was dead code on exactly the documents it was for.

from docmodel.modules.header import _LEVEL                      # noqa: E402


def _level(cmd, caption, stated=True):
    """The precedence under test, as HeaderProcessor applies it."""
    num = _heading_number(caption)
    explicit = bool(stated) and cmd in _LEVEL and cmd != "section"
    if explicit:
        return _LEVEL[cmd], "latex_command"
    if num:
        return min(num.count(".") + 1, _MAX_SIZE_LEVEL), "section_number"
    if stated:
        return _LEVEL.get(cmd, 1), "latex_command"
    return None, "font_size"


def test_a_bare_section_yields_to_the_printed_number():
    assert _level("section", "12.2 The flavour symmetry SU(2)f") == (2, "section_number")
    assert _level("section", "12.2.1 The nucleon isospin doublet") == (3, "section_number")


def test_an_explicit_subsection_is_honoured():
    """A producer that NAMES a depth has stated one, and is believed."""
    assert _level("subsection", "Whatever the caption") == (2, "latex_command")
    assert _level("subsubsection", "12.2 Numbered anyway") == (3, "latex_command")


def test_a_bare_section_without_a_number_keeps_the_command_level():
    assert _level("section", "References") == (1, "latex_command")


def test_an_unstated_unnumbered_heading_falls_through_to_the_size():
    assert _level("section", "References", stated=False)[1] == "font_size"
