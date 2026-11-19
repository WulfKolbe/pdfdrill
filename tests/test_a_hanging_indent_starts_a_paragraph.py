r"""A column's body edge is its MOST FREQUENT edge, not its leftmost or its
rightmost — and the lower layer has to hand that frequency up.

Two paragraph shapes occur in one corpus, and they are mirror images:

    ordinary indent   lib:008d43e5db48   464 with 27 lines, 512 with  9
    hanging indent    0864 p5, left      192 with 15 lines, 224 with 40

In the first the body edge is on the LEFT and the first line is indented
right. In the second — a bibliography — entries BEGIN at the left edge and
continue one em to its right, so the body edge is the RIGHT one. Position
cannot tell them apart. Frequency can, and it is a fact the page states:
running text uses its edge on every line, an indent once per paragraph.

`_body_edges` measures exactly that in `recurring` and used to discard it,
handing callers a bare list of x values. `_is_first_line` then had to guess
which edge was the body, and the guess is where this went wrong twice:

  * `at_or_left[-1]` measured a right-column line at 1097 against the LEFT
    column's 224 and called it an indent of 27 em. 0864 p5's right column was
    split correctly only by that accident, while its left column welded all
    54 entries into one Paragraph (obj_096e747925e7, 2775 characters).
  * taking the column's RIGHTMOST edge fixed the bibliography and inverted
    every ordinary page: on lib:008d43e5db48 the rightmost IS the indent, so
    370 pages of German prose became one paragraph per line — 2,501 objects
    to 7,904, and +56 % over the ten-document inspect set. Pushed as
    9255c818, reverted an hour later as af1e996b.

So the counts travel with the edges, the body edge is the most frequent one
in its column, and columns are kept apart by a gap of more than two em so a
line is never measured against another column.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.modules.paragraph import (_column_body_edge,  # noqa: E402
                                        _is_first_line)

#: 0864 p5 exactly as `_body_edges` returns it, counts included.
HANGING = {5: ([192.0, 224.0, 1136.0], 32.0, [],
               {192.0: 15, 224.0: 40, 1136.0: 18})}

#: lib:008d43e5db48 page 1, the opposite shape.
ORDINARY = {1: ([464.0, 512.0], 32.0, [], {464.0: 27, 512.0: 9})}


def test_the_body_edge_is_the_most_frequent_one():
    assert _column_body_edge(191.0, [192.0, 224.0], 32.0,
                             {192.0: 15, 224.0: 40}) == 224.0
    assert _column_body_edge(465.0, [464.0, 512.0], 32.0,
                             {464.0: 27, 512.0: 9}) == 464.0


def test_a_hanging_indent_starts_a_paragraph():
    """0864 p5: entries begin an em left of where they continue."""
    assert _is_first_line(191.0, 5, HANGING) is True
    assert _is_first_line(1097.0, 5, HANGING) is True


def test_a_continuation_at_its_body_edge_starts_nothing():
    assert _is_first_line(224.0, 5, HANGING) is False
    assert _is_first_line(229.0, 5, HANGING) is False
    assert _is_first_line(1136.0, 5, HANGING) is False
    assert _is_first_line(1133.0, 5, HANGING) is False


def test_an_ordinary_indent_still_starts_a_paragraph():
    """lib:008d43e5db48: the first line is indented RIGHT of the body edge."""
    assert _is_first_line(517.0, 1, ORDINARY) is True


def test_an_ordinary_body_line_starts_nothing():
    """The regression af1e996b reverted: these are 1.5 em left of the
    RIGHTMOST edge, and every one of them started a paragraph."""
    assert _is_first_line(465.0, 1, ORDINARY) is False
    assert _is_first_line(466.0, 1, ORDINARY) is False
    assert _is_first_line(467.0, 1, ORDINARY) is False


def test_a_line_is_never_measured_against_another_column():
    """1097 is 873 px right of the left column's body edge and 39 px left of
    its own. Its own column decides."""
    assert _column_body_edge(1097.0, [192.0, 224.0, 1136.0], 32.0,
                             {192.0: 15, 224.0: 40, 1136.0: 18}) == 1136.0


def test_a_reading_that_states_no_counts_still_answers():
    """A three-tuple from an older caller must not raise; with no evidence
    the leftmost edge of the column is taken, which is the common shape."""
    assert _is_first_line(517.0, 1, {1: ([464.0, 512.0], 32.0, [])}) is True


#: lib:008d43e5db48 p292, a narrative page: three recurring edges and no
#: majority between them.
AMBIGUOUS = {292: ([464.0, 512.0, 544.0], 32.0, [],
                   {464.0: 15, 512.0: 9, 544.0: 13})}


def test_an_undecided_column_gets_no_indent_rule_at_all():
    """15 lines against 13 is not evidence. Choosing 464 anyway made every
    one of the 13 lines at 552 an indent of nearly three em, and a passage of
    narrative came out as one paragraph per line."""
    assert _column_body_edge(465.0, *list(AMBIGUOUS[292])[:1] and
                             [AMBIGUOUS[292][0], 32.0, AMBIGUOUS[292][3]]) is None
    assert _is_first_line(552.0, 292, AMBIGUOUS) is False
    assert _is_first_line(465.0, 292, AMBIGUOUS) is False


def test_a_clear_majority_still_decides():
    """27 to 9 is evidence; 40 to 15 is evidence."""
    assert _column_body_edge(465.0, [464.0, 512.0], 32.0,
                             {464.0: 27, 512.0: 9}) == 464.0
    assert _column_body_edge(191.0, [192.0, 224.0], 32.0,
                             {192.0: 15, 224.0: 40}) == 224.0
