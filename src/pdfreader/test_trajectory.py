"""Tests for the current-point trajectory sidecar.

The measurements quoted are from arXiv 1804.10694v5 page 7, a two-column
IEEE-format page carrying a box-and-arrow figure in the right column.
"""
import os

import pytest

import testpaths
import trajectory as T

DOC = os.environ.get("PDF2MMD_TEST_TWOCOL", testpaths.CORPUS_PDF)
HAVE = os.path.exists(DOC)


class TestStreamOrderIsReadingOrder:
    """The producer emitted the glyphs in the order it wanted them read.

    pdfminer's layout analysis discards that ordering and rebuilds its own
    from coordinates, which is what forced three separate geometric
    heuristics -- column edge, baseline window, band gutter -- to guess at
    structure the stream states outright.
    """

    def test_is_pen_up_distinguishes_advance_from_move(self):
        adv = T.Move(index=1, page=1, text="a", x=100.0, y=700.0, adv=5.0,
                     size=10.0, font="X", dx=0.0, dy=0.0)
        assert not adv.is_pen_up

    def test_a_baseline_change_is_a_pen_up(self):
        nl = T.Move(index=1, page=1, text="a", x=48.0, y=688.0, adv=5.0,
                    size=10.0, font="X", dx=-253.0, dy=-12.0)
        assert nl.is_pen_up

    def test_a_wide_gap_is_a_pen_up(self):
        gap = T.Move(index=1, page=1, text="a", x=300.0, y=700.0, adv=5.0,
                     size=10.0, font="X", dx=40.0, dy=0.0)
        assert gap.is_pen_up


class TestSegmentation:
    def _run(self, xs_ys):
        out = []
        prev = None
        for i, (x, y) in enumerate(xs_ys):
            m = T.Move(index=i, page=1, text="a", x=x, y=y, adv=5.0,
                       size=10.0, font="X")
            if prev is not None:
                m.dx = x - (prev.x + prev.adv)
                m.dy = y - prev.y
            out.append(m)
            prev = m
        return out

    def test_carriage_returns_stay_in_one_block(self):
        """Back to the margin, one line down, is how running text advances --
        not a new block. Measured signature: dx=-253, dy=-12."""
        pts = []
        for line in range(4):
            y = 700.0 - line * 12.0
            for k in range(20):
                pts.append((48.0 + k * 6.0, y))
        assert len(T.segment(self._run(pts))) == 1

    def test_a_move_up_starts_a_block(self):
        """The column change is ONE event: measured dx=+136, dy=+406."""
        pts = [(48.0 + k * 6.0, 700.0) for k in range(20)]
        pts += [(320.0 + k * 6.0, 740.0) for k in range(20)]
        assert len(T.segment(self._run(pts))) == 2

    def test_blocks_record_their_stream_range(self):
        pts = [(48.0 + k * 6.0, 700.0) for k in range(10)]
        pts += [(320.0 + k * 6.0, 740.0) for k in range(10)]
        blocks = T.segment(self._run(pts))
        assert blocks[0].start == 0 and blocks[0].end == 10
        assert blocks[1].start == 10 and blocks[1].end == 20


class TestClassify:
    def _block(self, pts):
        moves = []
        prev = None
        for i, (x, y) in enumerate(pts):
            m = T.Move(index=i, page=1, text="a", x=x, y=y, adv=5.0,
                       size=10.0, font="X")
            if prev is not None:
                m.dx = x - (prev.x + prev.adv)
                m.dy = y - prev.y
            moves.append(m)
            prev = m
        return T.Block(page=1, start=0, end=len(moves), moves=moves)

    def test_running_text_is_flow(self):
        """Running text returns to ONE left edge on every line."""
        pts = []
        for line in range(5):
            for k in range(20):
                pts.append((48.0 + k * 6.0, 700.0 - line * 12.0))
        assert T.classify(self._block(pts)) == "flow"

    def test_independently_placed_runs_are_scatter(self):
        """A figure's labels start at a different x on every line."""
        pts = []
        for i, x0 in enumerate((120.0, 260.0, 190.0, 310.0, 150.0)):
            for k in range(6):
                pts.append((x0 + k * 6.0, 700.0 - i * 30.0))
        assert T.classify(self._block(pts)) == "scatter"

    def test_a_single_line_is_single(self):
        pts = [(48.0 + k * 6.0, 700.0) for k in range(10)]
        assert T.classify(self._block(pts)) == "single"


@pytest.mark.skipif(not HAVE, reason="needs a PDF")
class TestOnARealPage:
    def test_the_stream_is_readable_in_order(self):
        moves = T.glyph_stream(DOC, range(0, 1))
        assert moves
        text = "".join(m.text for m in moves[:60])
        assert text.strip(), "no glyphs came back in stream order"

    def test_segmentation_produces_blocks(self):
        blocks = T.segment(T.glyph_stream(DOC, range(0, 1)))
        assert blocks
        assert all(b.end > b.start for b in blocks)
        assert all(b.rows >= 1 for b in blocks)
