r"""A break stated before the FIRST line of a block has no line to break.

T-0156, requirement 1, third step.

`text_display` states the break that PRECEDES its line, so a reading writes

    text        : 'sreyasi@mpi-inf.mpg.de'
    text_display: ' \\ sreyasi@mpi-inf.mpg.de'

for a line that follows another. `paragraph.py` composes a block's text from
`text_display` verbatim — correctly, because that field is also where the
reader states a block boundary — and at the HEAD of a block that leading
`\\` becomes a paragraph-leading line break. LaTeX answers "There's no line
here to end".

MEASURED on the eight e-prints: 15 of the 146 errors, 13 of them in
1909.00741's author and affiliation block, where every line carries one.

AND THE CENSUS HAD THIS CLASS AT THE WRONG LEVEL. I filed all 146 errors
under the projector. This one is the MODEL: the reading's own `text` field
is clean, the leading break lives only in `text_display`, and the projector
emits faithfully what the model hands it. Depth was wrong by one level.

The break is meaningful BETWEEN lines and says nothing at the start of one,
so it is dropped only there — restoring exactly what the reading's `text`
field already said.

11 OF THE 15. Four remain in 1909.00741, in Paragraph objects whose
`props[text]` still carries a leading `\\`; they are built somewhere other
than this composer and are left for their own measurement.
"""
from docmodel.modules.paragraph import _LEADING_BREAK as pat


def _strip(t: str) -> str:
    return pat.sub("", t, count=1)


def test_the_measured_line_is_restored_to_its_text_field():
    assert _strip(" \\\\ sreyasi@mpi-inf.mpg.de") == "sreyasi@mpi-inf.mpg.de"


def test_a_break_with_no_leading_space():
    assert _strip("\\\\ Hakan Ferhatosmanoglu") == "Hakan Ferhatosmanoglu"


def test_a_break_between_lines_is_untouched():
    """Only the HEAD of a block loses it; inside, it is a real line break."""
    assert _strip("a \\\\ b") == "a \\\\ b"


def test_plain_text_is_untouched():
    assert _strip("plain text") == "plain text"


def test_a_command_is_not_a_break():
    r"""`\alpha` begins with a backslash and is not a line break."""
    assert _strip("\\alpha x") == "\\alpha x"
    assert _strip("\\\\alpha") == "\\\\alpha"


def test_only_the_first_break_goes():
    """`count=1`: a second break is a real one between two lines."""
    assert _strip("\\\\ a \\\\ b") == "a \\\\ b"
