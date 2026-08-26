"""221 — the four dropped code points, and the gate that stops 214 measuring
a report they were dropped from.

out/213 built eleven reports. Six exited 0, produced a PDF, and had silently
discarded characters: U+09E7 (Bengali one), U+53E3, U+5B5B, U+5B80 and
U+5315 (CJK), plus one ASCII 'g' that is a different bug entirely. A residual
measured against such a report compares a render that is MISSING symbols
against a scan that has them, and books the difference as an extraction
defect. The exit code cannot carry that distinction; only the log can.
"""
import pytest

from pdfdrill import report_tex as rt


DROPPED = {
    0x09E7: "BENGALI DIGIT ONE, Geometrodynamics (Mielke), 20 occurrences",
    0x53E3: "CJK 口, Lie Groups and Geometric/Algebraic/Topological Methods",
    0x5B5B: "CJK 孛, An Invitation to Applied Category Theory",
    0x5B80: "CJK 宀, Seven Sketches in Composability",
    0x5315: "CJK 匕, Mielke EQ0857 — the out/219 row",
}


@pytest.mark.parametrize("cp", sorted(DROPPED))
def test_every_dropped_code_point_now_reaches_a_font(cp):
    decl = rt.unicode_decls(chr(cp))
    assert decl, "U+%04X produced no declaration at all — it would drop" % cp
    assert ("\\fbcjk" in decl or "\\fbbeng" in decl), \
        "U+%04X (%s) is not routed to a fallback family: %r" % (
            cp, DROPPED[cp], decl)


def test_the_ranges_are_coverage_not_blocks():
    """A block test routes a character to a font that may not have it, which
    turns a dropped glyph into a dropped glyph with an extra step. U+2E9A is
    an unassigned hole inside the Radicals Supplement block and Noto Sans CJK
    does not carry it, so the measured ranges must skip it."""
    assert not rt.in_ranges(0x2E9A, rt._FB_CJK_RANGES)
    assert rt.in_ranges(0x2E99, rt._FB_CJK_RANGES)
    assert rt.in_ranges(0x2E9B, rt._FB_CJK_RANGES)
    # the Bengali block likewise has holes the font does not fill
    assert not rt.in_ranges(0x0984, rt._FB_BENG_RANGES)
    assert rt.in_ranges(0x09E7, rt._FB_BENG_RANGES)


def test_a_real_glyph_beats_the_marker_when_a_font_exists():
    """U+09A0 and U+09AA sit in _NO_FONT from a measurement taken before Noto
    Sans Bengali was installed. The marker is for code points with no font
    anywhere, not for ones nobody had checked lately."""
    for cp in (0x09A0, 0x09AA):
        decl = rt.unicode_decls(chr(cp))
        assert "\\fbbeng" in decl, decl
        assert "[U+" not in decl, decl


def test_the_marker_survives_for_code_points_that_still_have_no_font():
    decl = rt.unicode_decls("")        # Private Use Area
    assert "[U+F8FF]" in decl


def test_the_bengali_family_is_declared_but_guarded():
    """An unguarded \\newfontfamily for a font this machine lacks ABORTS the
    compile and writes no PDF — strictly worse than the dropped glyph it was
    added to prevent."""
    assert r"\IfFontExistsTF{Noto Sans Bengali}" in rt.PREAMBLE
    assert r"\newfontfamily\fbbeng{Noto Sans Bengali}" in rt.PREAMBLE


# --- the 214 gate ----------------------------------------------------------

_LOST = ("Missing character: There is no ১ (U+09E7) in font "
         "DejaVu Serif/OT:script=latn;\n")


def test_a_glyph_dropping_report_is_not_measurable(tmp_path):
    log = tmp_path / "report.log"
    log.write_text("Output written on report.pdf (494 pages)\n" + _LOST * 20,
                   encoding="utf-8")
    ok, why = rt.ink_measurable(log)
    assert ok is False
    assert "20 dropped character" in why
    assert "U+09E7" in why


def test_a_clean_report_is_measurable(tmp_path):
    log = tmp_path / "report.log"
    log.write_text("Output written on report.pdf (494 pages)\n",
                   encoding="utf-8")
    assert rt.ink_measurable(log) == (True, "")


def test_a_missing_log_does_not_refuse(tmp_path):
    """The first build has no previous log. Refusing there would make the
    very first report unmeasurable for a defect nobody has evidence of."""
    ok, _ = rt.ink_measurable(tmp_path / "nothing.log")
    assert ok is True


def test_the_refusal_note_is_not_the_absence_note():
    """Three states, three sentences. 'No measurement has been run' is false
    when one has been run and refused; 'could not be paired' names the report's
    table when the cause is a missing font."""
    a = rt.unmeasured_note("glyphs_dropped")
    b = rt.unmeasured_note("not_run")
    c = rt.unmeasured_note("unpairable")
    assert a and b and c
    assert a != b != c and a != c
    assert "withheld" in a and "dropped characters" in a
    assert "no residual measurement has been run" in b
    assert "could not be read reliably" in c


def test_no_note_when_nothing_is_wrong():
    assert rt.unmeasured_note("") == ""


# --- 221b: the fix that the first fix needed -------------------------------

def test_a_fallback_family_must_work_in_MATH_mode_too():
    r"""`{{\fbcjk 」}}` is a TEXT font switch and does nothing inside $...$.
    Mielke kept losing U+300D after it already had a \fbcjk declaration —
    once, at its single math-mode occurrence, while the three \ttfamily
    occurrences in the Source column set correctly."""
    for cp in (0x300D, 0x5315, 0x09E7):
        decl = rt.unicode_decls(chr(cp))
        assert r"\ifmmode" in decl, "U+%04X: %r" % (cp, decl)
        assert r"\text{{" in decl, "U+%04X: %r" % (cp, decl)


def test_the_covered_escape_names_the_font_it_measured():
    r"""_COVERED is DejaVu Sans MONO's coverage; \text{} selects the MAIN
    font, which is serif, and serif lacks 917 of those code points. U+0644
    dropped eight times in Mielke's math exactly this way."""
    decl = rt.unicode_decls("ل")
    assert r"\ttfamily" in decl, decl
    assert rt.in_ranges(0x0644, rt._MONO_ONLY_RANGES)


def test_mathematical_operators_are_in_the_mono_only_set():
    """Most of the set is not exotic. U+2244, U+2262 and U+2300 are ordinary
    mathematical operators and every one of them was one math-mode occurrence
    away from vanishing."""
    for cp in (0x2244, 0x2262, 0x2300, 0x27E6):
        assert rt.in_ranges(cp, rt._MONO_ONLY_RANGES), hex(cp)
        assert r"\ttfamily" in rt.unicode_decls(chr(cp))


def test_characters_serif_already_carries_are_left_alone():
    """Changing a glyph that was never in danger is the out/097 regression:
    six 1205.3463v2 rows moved 1-2 units WORSE in the ink compare."""
    for cp in (0x03B1, 0x2211, 0x00E9):        # alpha, n-ary sum, e-acute
        assert not rt.in_ranges(cp, rt._MONO_ONLY_RANGES), hex(cp)
    decl = rt.unicode_decls("∑")
    assert r"\ttfamily" not in decl


def test_the_whole_IDC_block_is_covered_not_five_of_twelve():
    r"""221c, found while the batch ran. _FB_CJK lists 2FF1 2FF4 2FF8 2FFA
    2FFB by hand; Noto Sans CJK carries all twelve Ideographic Description
    Characters, and Lie Groups dropped U+2FF0 — one of the seven nobody had
    typed — in the same rebuild that was fixing four other hand-listed code
    points. The enumeration problem demonstrating itself."""
    for cp in range(0x2FF0, 0x2FFC):
        assert rt.in_ranges(cp, rt._FB_CJK_RANGES), hex(cp)


def test_a_plane_2_ideograph_no_font_carries_gets_the_marker():
    """U+27C28 is CJK Extension B. Noto Sans CJK does not carry it — checked
    against the font file — and neither does anything else installed. The
    marker is the correct outcome, not a failed fallback: the row still
    differs from the scan, but VISIBLY, so its residual is attributable and
    the rest of the document stays measurable."""
    assert rt.unicode_decls(chr(0x27C28)) == r"\newunicodechar{𧰨}{\textbf{[U+27C28]}}"
    assert not rt.in_ranges(0x27C28, rt._FB_CJK_RANGES)


# --- the advice the warning gives (out/219 flagged it as wrong) ------------

def test_advice_for_an_ascii_letter_in_a_tex_alphabet():
    r"""0707.4470: `There is no g ("67) in font rsfs10!` — hex 0x67, ASCII
    lowercase g, dropped because \mathscr's alphabet stops at Z. The old text
    said "add the code point to _MATH_CMD or a fallback font", which is the
    one place the answer cannot be."""
    a = rt.glyph_loss_advice(
        'Missing character: There is no g ("67) in font rsfs10!')
    assert "not a Unicode coverage problem" in a
    assert "rsfs10" in a
    assert "change the command, not the font" in a
    assert "_MATH_CMD" not in a


def test_advice_for_a_genuinely_uncovered_code_point():
    a = rt.glyph_loss_advice(
        "Missing character: There is no 宀 (U+5B80) in font DejaVu Serif/OT")
    assert "U+5B80" in a and "_MATH_CMD" in a and "_NO_FONT" in a


def test_below_u0080_inverts_the_diagnosis_even_with_no_font_named():
    """213 logged the truncated form, with no font name. The code point alone
    is enough: nothing below U+0080 is a coverage gap in a Unicode font."""
    a = rt.glyph_loss_advice('Missing character: There is no g ("67).')
    assert "not a Unicode coverage problem" in a


def test_unparseable_sample_falls_back_to_the_generic_advice():
    a = rt.glyph_loss_advice("something else entirely")
    assert "_MATH_CMD" in a
