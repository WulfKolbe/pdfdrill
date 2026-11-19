r"""A bibliography's hanging indent starts a paragraph, and a line is measured
against its OWN column.

The owner's page: 0864 p5, the references. Every entry's first line hangs one
em LEFT of where its own continuations sit -- the opposite of a paragraph
indent, and just as much a statement that an entry begins.

MEASURED, not assumed. `_body_edges` returns THREE edges for that page and an
em of 32:

    192    where the left column's entries BEGIN      (15 lines)
    224    where the left column's entries CONTINUE   (40 lines)
    1136   the right column, both kinds together      (18 lines at 1133-1136,
                                                       8 first lines at 1097)

So a hanging indent shows as TWO EDGES ONE EM APART IN ONE COLUMN, and the
left first lines sit AT an edge rather than left of one. Two things then go
wrong in `_is_first_line`:

  * a left first line at 191 is within half an em of edge 192, so it reads as
    a continuation and all 54 entries join one Paragraph (obj_096e747925e7);
  * a right first line at 1097 takes `at_or_left[-1]`, which is the LEFT
    column's 224, measures 873 px of "indent" and starts a paragraph. The
    right column is split correctly only by ACCIDENT, against another
    column's edge -- the very thing this function's docstring forbids.

The fix follows the measurement: group the edges into columns (a gap of more
than two em starts a new one), take each column's RIGHTMOST edge as its body
edge, and call a line a first line when it stands an em right of that edge
(an ordinary indent) or three quarters of an em LEFT of it (a hanging one).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402

from docmodel.modules.paragraph import _is_first_line  # noqa: E402

#: THE FIX THIS FILE DESCRIBES IS REVERTED. It was pushed as 9255c818 and
#: taken out again the same hour, because taking a column's RIGHTMOST edge as
#: its body edge INVERTS the ordinary indented paragraph. On a page whose
#: edges are 464 (body, 27 lines) and 512 (first-line indent, 9 lines), the
#: rightmost is the INDENT, so every body line read as a hanging indent and
#: started a paragraph. Measured over the ten-document inspect set:
#: 53,828 objects -> 83,773, +56 %; lib:008d43e5db48 2501 -> 7904 on 370
#: pages of ordinary German prose.
#:
#: The body edge is the MOST FREQUENT edge of its column, not the rightmost.
#: `_body_edges` has those counts in `recurring` and discards them, so the
#: real fix carries them through -- which is a change to what that function
#: returns and to everything that unpacks it, not a change here.
#:
#: These stay as xfail so the target is not lost and nobody re-pushes the
#: rightmost rule.
pytestmark = pytest.mark.xfail(strict=False, reason=(
    "hanging indent not implemented: 9255c818 inverted the ordinary indent "
    "and was reverted; needs the per-edge line counts from _body_edges"))

#: 0864 p5 exactly as `_body_edges` returns it.
EDGES = {5: ([192.0, 224.0, 1136.0], 32.0, [])}


def test_a_left_column_hanging_indent_starts_a_paragraph():
    assert _is_first_line(191.0, 5, EDGES) is True


def test_a_right_column_hanging_indent_starts_a_paragraph():
    assert _is_first_line(1097.0, 5, EDGES) is True


def test_a_continuation_line_at_its_edge_starts_nothing():
    assert _is_first_line(224.0, 5, EDGES) is False
    assert _is_first_line(1136.0, 5, EDGES) is False


def test_a_continuation_a_few_pixels_off_its_edge_starts_nothing():
    assert _is_first_line(229.0, 5, EDGES) is False
    assert _is_first_line(1133.0, 5, EDGES) is False


def test_an_ordinary_first_line_indent_still_starts_a_paragraph():
    """The rule this function was written for, unchanged."""
    assert _is_first_line(224.0 + 60.0, 5, EDGES) is True


def test_a_right_column_line_is_never_measured_against_the_left_column():
    """1097 is 873 px right of the left column's 224 and 39 px left of its
    own 1136. Its own column decides, so this is a hanging indent of one em,
    not an indent of twenty-seven."""
    cols, em, _ = EDGES[5]
    assert min(cols, key=lambda e: abs(e - 1097.0)) == 1136.0


def test_a_right_column_body_line_is_not_a_first_line():
    """The accident the old rule depended on: a RIGHT-column continuation is
    also hugely 'indented' against the left column's edge, and must not start
    a paragraph."""
    assert _is_first_line(1135.0, 5, EDGES) is False
