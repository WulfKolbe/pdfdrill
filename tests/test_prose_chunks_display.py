r"""
847 — a display equation does not end a paragraph.

`_prose_chunks` blanks every structural block to SPACES with the newlines
preserved, so a display on its own line became a whitespace-only line and the
blank-line rule `\n[ \t]*\n` read it as a paragraph separator. In LaTeX it is
not one: `text \begin{equation}…\end{equation} text` is ONE paragraph, the
continuation is set unindented, and only a blank line or `\par` ends it.

This matters more than a count, because the number was being quoted as the GOLD
a reader is scored against. Measured on arXiv 1102.1889: 408 prose chunks
against LaTeX's 382 (7%), and 332 Paragraph objects against 325 after the fix.

inkdrill found the same shape in their own paragraph gold — 461 -> 382 over
three documents, 17% — and said so before I had looked at mine. Their tell is
worth keeping: the median indent at a claimed boundary came out at 0.02 line
heights, and a gold that says paragraphs are not indented is not reporting on
LaTeX.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.latex_source import _prose_chunks                # noqa: E402

DISPLAY = r"\begin{equation} x^2 + y^2 = z^2 \end{equation}"


def chunks(src):
    return [c for _, c in _prose_chunks(src)]


def test_a_display_on_its_own_line_does_not_break_the_paragraph():
    """THE DEFECT. The commonest layout in every paper there is."""
    got = chunks(f"We first observe that the measure is finite.\n{DISPLAY}\n"
                 f"and therefore the bound follows immediately.")
    assert len(got) == 1, got
    assert "We first observe" in got[0] and "and therefore" in got[0]


def test_a_display_inside_the_sentence_does_not_break_it_either():
    got = chunks(f"We observe {DISPLAY} and therefore it follows.")
    assert len(got) == 1, got


def test_a_blank_line_still_breaks_the_paragraph():
    """The rule that must survive: a real `\\par` is a real boundary."""
    got = chunks("We first observe that the measure is finite.\n\n"
                 "and therefore the bound follows immediately.")
    assert len(got) == 2, got


def test_blank_lines_around_a_display_still_break():
    got = chunks(f"We first observe that the measure is finite.\n\n{DISPLAY}\n\n"
                 f"and therefore the bound follows immediately.")
    assert len(got) == 2, got


def test_the_position_points_at_prose_not_at_the_blanked_block():
    """`pos` is used to locate the chunk in the ORIGINAL source. A chunk that
    started at the sentinel would point into the equation instead of the
    sentence — which is why the scan skips the sentinel at a chunk's start."""
    src = f"{DISPLAY}\nWe then observe that the measure is finite."
    got = list(_prose_chunks(src))
    assert len(got) == 1, got
    pos, text = got[0]
    assert src[pos:pos + 7] == "We then", src[pos:pos + 20]


def test_the_yielded_text_keeps_its_offsets():
    """The sentinel is mapped back to spaces before yielding, so a caller doing
    `pos + text.index(...)` is unaffected: only the SPLIT sees it."""
    src = f"We observe {DISPLAY} and therefore it follows."
    pos, text = next(iter(_prose_chunks(src)))
    assert len(text) == len(src) - pos
    i = text.index("therefore")
    assert src[pos + i:pos + i + 9] == "therefore"


def test_no_sentinel_leaks_into_the_prose():
    got = chunks(f"We observe {DISPLAY} and therefore it follows.")
    assert "\x01" not in got[0]


# ---------------------------------------------------------------- 850

CRLF = ("We first observe that the measure is finite.\r\n"
        "\r\n"
        "and therefore the bound follows immediately.\r\n")


def test_a_crlf_file_still_splits_into_paragraphs():
    r"""850 — THE WHOLE DOCUMENT CAME BACK AS ONE PARAGRAPH.

    A blank line in a CRLF file is `\r\n\r\n`, and the separator was
    `\n[ \t]*\n`, which does not allow the `\r` between the two newlines. So the
    split never fired and every CRLF source yielded exactly one chunk.

    Found by the cross-check against inkdrill's independent gold over 20 sigma26
    papers: five returned 1 chunk where the gold had 170, 168, 314, 32 and 73 —
    and those five files are pure CRLF (1,495 / 1,709 / 2,599 / 1,041 / 966 CRLF
    and ZERO bare LF), while all fifteen that agreed are pure LF. Perfect
    correlation. Agreement on the whole corpus went 77.5% -> 96.5%.

    The defect predates 847: only this site used the narrow class, and every
    other blank-line pattern in src/ uses `\s`, which already contains `\r`.
    """
    got = [c for _, c in _prose_chunks(CRLF)]
    assert len(got) == 2, got
    assert "We first observe" in got[0]
    assert "and therefore" in got[1]


def test_crlf_and_lf_agree_on_the_same_document():
    """The two line endings must not give different paragraph counts."""
    lf = CRLF.replace("\r\n", "\n")
    assert len([c for _, c in _prose_chunks(CRLF)]) == \
           len([c for _, c in _prose_chunks(lf)])


def test_a_crlf_display_still_does_not_break_the_paragraph():
    """847 and 850 together: the display is spanned AND the file is CRLF."""
    src = ("We first observe that the measure is finite.\r\n"
           + DISPLAY + "\r\n"
           "and therefore the bound follows immediately.\r\n")
    got = [c for _, c in _prose_chunks(src)]
    assert len(got) == 1, got


def test_crlf_positions_still_point_at_prose():
    pos, text = next(iter(_prose_chunks(CRLF)))
    assert CRLF[pos:pos + 8] == "We first", CRLF[pos:pos + 20]
