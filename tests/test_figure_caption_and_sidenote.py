r"""A figure's caption belongs inside its float; a text column is not a sidenote.

Both reported from the inspector, and both had the same root: a `column`
container line and a `figure_label` line being read as something they are not.

THE FIGURE. A Picture/Diagram with no `latex_code` used to project as a COMMENT
— `% figure p12: Delta life span over time…` — which is legible and useless: the
caption is not in a float, so it cannot be `\ref`ed, hyperref has nothing to
link to, and a reader following an internal link gets no hover text. The
requirement is that the caption sit INSIDE `\begin{figure}`, because a link that
carries a caption can show it.

THE SIDENOTE. `SidenoteProcessor` claims any `column` with text children. On a
two-column paper that makes the body prose a margin note: 18 on 1909.00741, the
first reading "advances in deep-learning-based object detection have lifted this
approach to a higher level", and 28 on 1-s2.0-S2590118425000565-main whose text
is the bibliography. After the width test: 0 and 1, the survivor being page 1's
`ARTICLE INFO` box at 362pt against a 1240pt column.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stream:
    """The minimum `find_items` reads: ordered anchors and their payloads."""
    def __init__(self, rows):
        self.anchors = [r["id"] for r in rows]
        self.payload = {r["id"]: r for r in rows}


def _col(i, page, width, children=("t1",)):
    return {"id": i, "type": "column", "_page": page, "column": 0,
            "region": {"top_left_x": 0, "top_left_y": 0,
                       "width": width, "height": 100},
            "text": "", "children_ids": list(children)}


class TestTheSidenoteWidthTest:
    def test_a_body_column_is_not_a_sidenote(self):
        """Two equal columns are a two-column body, not a note and its page."""
        from docmodel.modules.sidenote import SidenoteProcessor as S
        st = _Stream([_col("a", 1, 881), _col("b", 1, 881)])
        assert not S._is_narrow_for_its_page(st, st.payload["a"])

    def test_a_narrow_column_beside_a_wide_one_is(self):
        from docmodel.modules.sidenote import SidenoteProcessor as S
        st = _Stream([_col("a", 1, 362), _col("b", 1, 1240)])
        assert S._is_narrow_for_its_page(st, st.payload["a"])
        assert not S._is_narrow_for_its_page(st, st.payload["b"])

    def test_a_lone_column_is_not_a_sidenote(self):
        """With nothing wider on the page there is no evidence of a margin."""
        from docmodel.modules.sidenote import SidenoteProcessor as S
        st = _Stream([_col("a", 1, 881)])
        assert not S._is_narrow_for_its_page(st, st.payload["a"])

    def test_width_is_compared_within_a_page(self):
        """A wide column on ANOTHER page says nothing about this one's margin."""
        from docmodel.modules.sidenote import SidenoteProcessor as S
        st = _Stream([_col("a", 1, 881), _col("b", 2, 1400)])
        assert not S._is_narrow_for_its_page(st, st.payload["a"])


class TestTheSiblingCaption:
    def _stream(self, label_text, page=12):
        return _Stream([
            {"id": "d", "type": "diagram", "_page": page, "text": "",
             "text_display": "", "children_ids": []},
            {"id": "f", "type": "figure_label", "_page": page,
             "text": label_text, "text_display": label_text},
        ])

    def test_a_sibling_that_parses_as_a_caption_is_one(self):
        """253 established that a figure_label CHILD is the figure's own text,
        and that stands. This is the case it did not cover: on page 12 the label
        is a SIBLING under the same `column`, so the child loop never saw it and
        the line was claimed by nothing."""
        from docmodel.modules.diagram import DiagramProcessor as D
        st = self._stream("Fig. 8. Delta life span over time for considered topologies.")
        assert "Delta life span" in D._adjacent_label_caption(st, "d")

    def test_an_axis_label_is_not_a_caption(self):
        """The parse is the discriminator 253 lacked: an axis label carries no
        kind and no number."""
        from docmodel.modules.diagram import DiagramProcessor as D
        st = self._stream("time (s)")
        assert D._adjacent_label_caption(st, "d") == ""

    def test_a_label_on_another_page_is_not_taken(self):
        from docmodel.modules.diagram import DiagramProcessor as D
        st = _Stream([
            {"id": "d", "type": "diagram", "_page": 12, "text": "",
             "text_display": "", "children_ids": []},
            {"id": "f", "type": "figure_label", "_page": 13,
             "text": "Fig. 9. Something else.", "text_display": "Fig. 9. Something else."},
        ])
        assert D._adjacent_label_caption(st, "d") == ""

    def test_only_the_immediate_neighbour_counts(self):
        """A caption that has to be searched for is a guess."""
        from docmodel.modules.diagram import DiagramProcessor as D
        st = _Stream([
            {"id": "d", "type": "diagram", "_page": 12, "text": "",
             "text_display": "", "children_ids": []},
            {"id": "x", "type": "text", "_page": 12, "text": "prose between"},
            {"id": "f", "type": "figure_label", "_page": 12,
             "text": "Fig. 8. Too far away.", "text_display": "Fig. 8. Too far away."},
        ])
        assert D._adjacent_label_caption(st, "d") == ""
