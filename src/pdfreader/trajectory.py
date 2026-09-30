"""trajectory - the PostScript current point as a signal.

A PDF content stream is not a bag of glyphs. It is a sequence of pen moves and
shows, and the producer emitted them in the order it wanted them read. Every
`Td`, `TD`, `T*` and `Tm` is the producer saying "a new run starts HERE".

This module extracts that trajectory into a sidecar and segments it, without
any geometric heuristics: no column edges, no baseline clustering, no
left-edge modes. Those were inferred from where glyphs LANDED; this reads what
the producer actually did.

Measured on one two-column page (arXiv 1804.10694v5 p7, 4231 glyphs):

    line break within a column      dx = -253, dy = -12   (carriage return)
    left column -> right column     dx = +136, dy = +406   one jump, once
    figure labels                   8 up-jumps in a row, at the stream's end

The column change is a single event in the stream. Geometrically it is
invisible -- both columns carry the same number of lines, their baselines are
1 to 3pt apart, and full-width tables cross the gutter -- which is why three
separate heuristics were needed to guess at it.

CONTRACT
    glyph_stream(path, pages) -> list[Move]
        Glyphs in CONTENT STREAM order, each with the jump from its
        predecessor. Never reordered.

    segment(moves, ...) -> list[Block]
        Consecutive moves split at pen-ups. A Block records its stream range,
        bounding box, and the jump that opened it.

    classify(block) -> str
        "flow"    running text: regular line advances, one dominant left edge
        "scatter" independently placed runs: a figure's labels, a table's cells
        "single"  one run, no internal structure

Nothing here interprets glyphs. It reports what the pen did.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar


@dataclass
class Move:
    """One glyph and the pen move that preceded it."""
    index: int                  # position in the content stream
    page: int
    text: str
    x: float                    # current point, from the text matrix
    y: float
    adv: float                  # advance width
    size: float
    font: str
    dx: float = 0.0             # gap from the previous glyph's pen-up point
    dy: float = 0.0             # baseline change from the previous glyph

    @property
    def is_pen_up(self) -> bool:
        """Did the producer MOVE rather than simply advance?

        A pure advance leaves dx at roughly zero and dy exactly zero. Anything
        else is an explicit repositioning.
        """
        return abs(self.dy) > 0.01 or abs(self.dx) > 0.5 * max(self.size, 1.0)


@dataclass
class Block:
    """A run of glyphs the producer emitted without repositioning far."""
    page: int
    start: int
    end: int                    # exclusive
    moves: list[Move] = field(default_factory=list)
    opened_by: tuple[float, float] = (0.0, 0.0)   # the jump that started it

    @property
    def text(self) -> str:
        return "".join(m.text for m in self.moves)

    @property
    def rect(self) -> tuple[float, float, float, float]:
        xs0 = min(m.x for m in self.moves)
        xs1 = max(m.x + m.adv for m in self.moves)
        ys = [m.y for m in self.moves]
        size = max(m.size for m in self.moves)
        return (xs0, min(ys), xs1, max(ys) + size)

    @property
    def rows(self) -> int:
        """Distinct baselines in this block."""
        return len({round(m.y, 1) for m in self.moves})


def glyph_stream(path: str, pages=None) -> list[Move]:
    """Glyphs in content-stream order, with the pen move before each.

    `laparams=None` disables pdfminer's layout analysis, which otherwise
    reorders glyphs into its own idea of lines and boxes -- discarding the one
    ordering the producer actually asserted.
    """
    out: list[Move] = []
    for idx, layout in enumerate(extract_pages(path, page_numbers=pages,
                                               laparams=None)):
        pno = (list(pages)[idx] + 1) if pages is not None else idx + 1
        chars: list[LTChar] = []

        def walk(obj):
            if isinstance(obj, LTChar):
                chars.append(obj)
            elif hasattr(obj, "__iter__"):
                for child in obj:
                    walk(child)

        for element in layout:
            walk(element)

        prev = None
        for i, c in enumerate(chars):
            m = Move(index=i, page=pno, text=c.get_text(),
                     x=c.matrix[4], y=c.matrix[5], adv=c.adv, size=c.size,
                     font=c.fontname.split("+")[-1])
            if prev is not None:
                m.dx = m.x - (prev.x + prev.adv)
                m.dy = m.y - prev.y
            out.append(m)
            prev = m
    return out


def segment(moves: list[Move], line_tol: float = 1.5) -> list[Block]:
    """Split the stream where the producer moved somewhere new.

    A carriage return -- back to the margin, one line down -- continues a
    block; it is how running text advances. A move UP the page, or a large
    move that is not a carriage return, starts a new block.
    """
    blocks: list[Block] = []
    current: list[Move] = []
    opened = (0.0, 0.0)

    def close():
        if current:
            blocks.append(Block(page=current[0].page,
                                start=current[0].index,
                                end=current[-1].index + 1,
                                moves=list(current),
                                opened_by=opened))
            current.clear()

    for m in moves:
        if not current:
            current.append(m)
            continue
        size = max(m.size, 1.0)
        carriage_return = m.dy < -line_tol and m.dx < -4.0 * size
        moved_up = m.dy > line_tol
        jumped = m.dy <= -line_tol and not carriage_return
        far = abs(m.dx) > 12.0 * size and abs(m.dy) <= line_tol
        if moved_up or jumped or far:
            close()
            opened = (m.dx, m.dy)
        current.append(m)
    close()
    return blocks


def classify(block: Block) -> str:
    """What kind of block this is, from the pen's behaviour alone."""
    if len(block.moves) < 2:
        return "single"
    if block.rows <= 1:
        return "single"
    # Running text returns to the SAME left edge on every line.
    starts: dict[float, int] = {}
    prev_y = None
    for m in block.moves:
        if prev_y is None or abs(m.y - prev_y) > 0.5:
            key = round(m.x / 6.0) * 6.0
            starts[key] = starts.get(key, 0) + 1
        prev_y = m.y
    if not starts:
        return "single"
    dominant = max(starts.values())
    return "flow" if dominant >= 0.6 * sum(starts.values()) else "scatter"


def label_regions(blocks: list[Block], min_blocks: int = 3
                  ) -> list[tuple[float, float, float, float]]:
    """Rectangles covering runs of independently-placed text.

    A figure's labels are emitted as a cluster of short runs, each positioned
    on its own -- the producer repositions the pen for every box. Running text
    never does that: it returns to one margin line after line.

    So a figure's extent is readable from the stream without measuring
    strokes, counting marks, or comparing glyph density. Consecutive non-flow
    blocks are merged; `min_blocks` keeps a stray displaced word from becoming
    a region.
    """
    out: list[tuple[float, float, float, float]] = []
    run: list[Block] = []

    def close():
        if len(run) >= min_blocks:
            out.append((min(b.rect[0] for b in run),
                        min(b.rect[1] for b in run),
                        max(b.rect[2] for b in run),
                        max(b.rect[3] for b in run)))
        run.clear()

    for b in blocks:
        if classify(b) == "flow" and len(b.moves) > 12:
            close()
        else:
            run.append(b)
    close()
    return out
