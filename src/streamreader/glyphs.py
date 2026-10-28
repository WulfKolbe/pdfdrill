# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Glyphs of one page from the patched pdfminer, as flat parallel arrays.

The patch (pdfdrill, vendor/pdfminer-glyph-identity.patch) keeps what stock
pdfminer discards: the glyph name, the character code and the text
rendering mode. `scripts/install-pdfminer.sh` installs it.

One record per glyph across parallel columns rather than one object per
glyph: this is the layout a C++ or Zig reader would hand over, and nothing
downstream may depend on pdfminer's own classes.
"""
from __future__ import annotations

import logging
from array import array
from pathlib import Path
from typing import Iterator, NamedTuple

from . import texenc
from .bboxlayout import PX_PER_PT


class Glyphs:
    """Columns of equal length `n`, in the order the page set the glyphs.

    Geometry is in page pixels (250 dpi), top-left origin. `x0 y0 x1 y1` is
    the font's box for the glyph (advance wide, descent to ascent high: the
    same for every glyph of a font, not its ink); `base` is the baseline it
    was set on, text rise included. `size` is the effective font size in
    points; `font` indexes `fonts`; `name` is the PostScript glyph name or
    "".

    The stream trace (ported from psred's featjudge `trace.py`): `adv` is
    the glyph's advance on the page, character and word spacing included;
    `move` is what the stream put before the glyph beyond that, i.e. its
    origin minus the previous glyph's origin plus advance (0 for the page's
    first glyph); `cause` says where the move came from (CAUSE_*); `op`
    numbers the show operator the glyph belongs to. So for consecutive
    glyphs a, b: x0[b] == x0[a] + adv[a] + move[b].

    The ink box `ix0 iy0 ix1 iy1` is where the glyph's outline is, from the
    embedded font program (ported from pdfdrill's inkboxes); all four are
    NaN where it is not known: a font that is not embedded, Type 3,
    TrueType, or no fontTools."""

    __slots__ = ("x0", "y0", "x1", "y1", "base", "size", "font", "cid",
                 "mode", "text", "name", "adv", "move", "cause", "op",
                 "ix0", "iy0", "ix1", "iy1", "fonts", "_font_index")

    def __init__(self) -> None:
        self.x0, self.y0 = array("f"), array("f")
        self.x1, self.y1 = array("f"), array("f")
        self.base = array("f")
        self.size = array("f")
        self.font = array("H")
        self.cid = array("i")
        self.mode = array("b")
        self.text: list[str] = []
        self.name: list[str] = []
        self.adv, self.move = array("f"), array("f")
        self.cause, self.op = array("b"), array("i")
        self.ix0, self.iy0 = array("f"), array("f")
        self.ix1, self.iy1 = array("f"), array("f")
        self.fonts: list[str] = []
        self._font_index: dict[str, int] = {}

    @property
    def n(self) -> int:
        return len(self.text)

    def add(self, x0: float, y0: float, x1: float, y1: float, *, size: float,
            font: str, cid: int, mode: int, text: str, name: str,
            base: float | None = None, adv: float | None = None,
            cause: int = 0, op: int = 0,
            ink: tuple[float, float, float, float] | None = None) -> None:
        for column, value in zip((self.ix0, self.iy0, self.ix1, self.iy1),
                                 ink or (_NAN,) * 4):
            column.append(value)
        # without a trace the advance is the box width and nothing moved
        adv = x1 - x0 if adv is None else adv
        self.move.append(x0 - (self.x0[-1] + self.adv[-1]) if self.text
                         else 0.0)
        self.adv.append(adv)
        self.cause.append(cause)
        self.op.append(op)
        index = self._font_index.get(font)
        if index is None:
            index = self._font_index[font] = len(self.fonts)
            self.fonts.append(font)
        self.x0.append(x0)
        self.y0.append(y0)
        self.x1.append(x1)
        self.y1.append(y1)
        self.base.append(y1 if base is None else base)
        self.size.append(size)
        self.font.append(index)
        self.cid.append(cid)
        self.mode.append(mode)
        self.text.append(text)
        self.name.append(name)


_NAN = float("nan")

ASCENT = 0.5            # em: a glyph's box reaches at least this far up
DESCENT = 0.35          # ... and no further down: cmsy10's font box hangs
                        # a whole em below the baseline


def band(g: Glyphs, i: int) -> tuple[float, float]:
    """Top and bottom of the glyph for the layout: its font box, held to a
    sane band around its baseline."""
    em = (g.size[i] or 10.0) * PX_PER_PT
    return (min(g.y0[i], g.base[i] - ASCENT * em),
            min(max(g.y1[i], g.base[i]), g.base[i] + DESCENT * em))

#: Where the move before a glyph came from.
CAUSE_NONE = 0          # the next glyph of the same string
CAUSE_TJ = 1            # a number in the string array of a TJ
CAUSE_POSITION = 2      # a new show: Td/TD/T*/Tm or a new BT set the point


def tj_to_page(n: float, size: float, hscale: float, ctm_scale: float) -> float:
    """Page distance of a TJ number (thousandths of text space; a positive
    number moves left)."""
    return -n / 1000.0 * size * hscale * ctm_scale


class Rules:
    """The page's thin horizontal strokes, as columns of equal length `n`:
    fraction bars, overlines, radical bars, and the long rules of tables
    and footnotes. `y` is the stroke's centre line; all in page pixels."""

    __slots__ = ("x0", "x1", "y", "thickness")

    def __init__(self) -> None:
        self.x0, self.x1 = array("f"), array("f")
        self.y, self.thickness = array("f"), array("f")

    @property
    def n(self) -> int:
        return len(self.y)

    def add(self, x0: float, x1: float, y: float, thickness: float) -> None:
        self.x0.append(x0)
        self.x1.append(x1)
        self.y.append(y)
        self.thickness.append(thickness)


class Posts:
    """The page's thin vertical strokes, as columns of equal length `n`: the
    column lines of ruled tables. `x` is the stroke's centre line; all in
    page pixels."""

    __slots__ = ("x", "y0", "y1", "thickness")

    def __init__(self) -> None:
        self.x, self.thickness = array("f"), array("f")
        self.y0, self.y1 = array("f"), array("f")

    @property
    def n(self) -> int:
        return len(self.x)

    def add(self, x: float, y0: float, y1: float, thickness: float) -> None:
        self.x.append(x)
        self.y0.append(y0)
        self.y1.append(y1)
        self.thickness.append(thickness)


RULE_THICKNESS = 1.5        # points: thicker is a box or a bar chart
RULE_LENGTH = 2.0           # points: shorter is a dot


class PageGlyphs(NamedTuple):
    page: int
    width: int
    height: int
    glyphs: Glyphs
    error: str | None
    rules: Rules
    #: the page's exact size in PDF points (width, height); `width` and
    #: `height` above are rounded pixels
    points: tuple[float, float] = (0.0, 0.0)
    #: thin vertical strokes; None where the reader did not collect them
    posts: Posts | None = None


def missing_features() -> list[str]:
    """What the installed pdfminer lacks; empty when it is the patched one."""
    try:
        import inspect

        from pdfminer.layout import LTChar
    except ImportError:
        return ["pdfminer is not installed"]
    source = inspect.getsource(LTChar.__init__)
    return [f"LTChar.{a}" for a in ("cid", "glyphname", "render_mode")
            if a not in source]


def _walk(obj, chars: list, strokes: list) -> None:
    from pdfminer.layout import LTChar, LTContainer, LTCurve, LTImage
    for o in obj:
        if isinstance(o, LTChar):
            chars.append(o)
        elif isinstance(o, (LTCurve, LTImage)):
            # LTCurve covers lines and boxes. An image is here because
            # dvips draws every rule as a one-pixel image mask scaled to
            # the rule: on such a page there is no path at all.
            strokes.append(o)
        elif isinstance(o, LTContainer):
            _walk(o, chars, strokes)


def _rule(o) -> tuple[float, float, float, float] | None:
    """(x0, x1, y, thickness) in points if the object is a thin horizontal
    stroke: a line, a filled box used as one, or an image scaled to one."""
    x0, y0, x1, y1 = o.bbox
    height = y1 - y0
    stroked = getattr(o, "stroke", False)
    thickness = max(height, (getattr(o, "linewidth", 0.0) or 0.0)
                    if stroked else 0.0)
    if x1 - x0 <= RULE_LENGTH or not 0 < thickness <= RULE_THICKNESS:
        return None
    if height > RULE_THICKNESS:
        return None
    return x0, x1, (y0 + y1) / 2, thickness


def _post(o) -> tuple[float, float, float, float] | None:
    """(x, y0, y1, thickness) in points if the object is a thin vertical
    stroke."""
    x0, y0, x1, y1 = o.bbox
    width = x1 - x0
    stroked = getattr(o, "stroke", False)
    thickness = max(width, (getattr(o, "linewidth", 0.0) or 0.0)
                    if stroked else 0.0)
    if y1 - y0 <= RULE_LENGTH or not 0 < thickness <= RULE_THICKNESS:
        return None
    if width > RULE_THICKNESS:
        return None
    return (x0 + x1) / 2, y0, y1, thickness


def _tracing_device(manager, ink: bool = False):
    """A page aggregator that also notes, on each LTChar it makes, the
    cause of the move before it, its show number and its page advance."""
    from pdfminer import utils
    from pdfminer.converter import PDFPageAggregator

    from .ported import inkboxes

    class Tracer(PDFPageAggregator):
        show_no = 0

        def render_char(self, matrix, font, fontsize, scaling, rise, cid,
                        ncs, graphicstate):
            adv = super().render_char(matrix, font, fontsize, scaling, rise,
                                      cid, ncs, graphicstate)
            if not ink:
                return adv
            made = self.cur_item._objs[-1]
            try:
                made.inkname, made.ink, _why = inkboxes.box(
                    font, getattr(made, "glyphname", None),
                    getattr(made, "fontname", ""), cid, matrix, fontsize,
                    scaling, rise)
            except Exception:                            # noqa: BLE001
                made.inkname, made.ink = None, None
            return adv

        def render_string_horizontal(self, seq, matrix, pos, font, fontsize,
                                     scaling, charspace, wordspace, rise,
                                     dxscale, ncs, graphicstate):
            # pdfminer's own loop, with the three notes added
            x, y = pos
            needcharspace = False
            cause = CAUSE_POSITION
            for obj in seq:
                if isinstance(obj, (int, float)):
                    x -= obj * dxscale
                    needcharspace = True
                    cause = CAUSE_TJ
                elif isinstance(obj, bytes):
                    for cid in font.decode(obj):
                        if needcharspace:
                            x += charspace
                        adv = self.render_char(
                            utils.translate_matrix(matrix, (x, y)), font,
                            fontsize, scaling, rise, cid, ncs, graphicstate)
                        x += adv
                        space = wordspace if cid == 32 and wordspace else 0
                        x += space
                        made = self.cur_item._objs[-1]
                        made.trace = (cause, self.show_no,
                                      (adv + charspace + space) * matrix[0])
                        needcharspace = True
                        cause = CAUSE_NONE
            self.show_no += 1
            return (x, y)

        def begin_page(self, page, ctm):
            self.show_no = 0
            super().begin_page(page, ctm)

    return Tracer(manager, laparams=None)


def read_pages(pdf: Path, first: int, last: int,
               ink: bool = False,
               only: "set[int] | None" = None) -> Iterator[PageGlyphs]:
    """One record per page. `ink=True` also traces each glyph's outline in
    its embedded font program for the ink box; it costs about 30 ms a page
    and nothing in the page pipeline reads it yet, so it is off there.
    `only`: page numbers to read; the other pages of `first`..`last` are
    skipped without being interpreted and yield no record."""
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser

    # pdfminer logs every content-stream operator at DEBUG
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    k = PX_PER_PT
    with open(pdf, "rb") as fh:
        doc = PDFDocument(PDFParser(fh))
        manager = PDFResourceManager()
        device = _tracing_device(manager, ink)
        interpreter = PDFPageInterpreter(manager, device)
        for number, page in enumerate(PDFPage.create_pages(doc), start=1):
            if number < first:
                continue
            if number > last:
                break
            if only is not None and number not in only:
                continue
            # pdfminer moves the page to its media box's corner; pdftotext
            # measures from the crop box, which is what a reader is shown
            bx0, by0, bx1, by1 = page.mediabox
            cx0, cy0, cx1, cy1 = getattr(page, "cropbox", None) or page.mediabox
            mx0, my0 = cx0 - bx0, cy0 - by0
            mx1, my1 = cx1 - bx0, cy1 - by0
            glyphs, rules, error = Glyphs(), Rules(), None
            posts = Posts()
            chars: list = []
            strokes: list = []
            # One bad page must not cost the document: pdfminer raises on a
            # corrupt stream or an unimplemented font table.
            try:
                interpreter.process_page(page)
                _walk(device.get_result(), chars, strokes)
            except Exception as e:                       # noqa: BLE001
                error = f"{type(e).__name__}: {e}"
            for c in chars:
                x0, y0, x1, y1 = c.bbox
                ink = getattr(c, "ink", None)
                if ink is not None:         # points, y up -> pixels, y down
                    ink = ((ink[0] - mx0) * k, (my1 - ink[3]) * k,
                           (ink[2] - mx0) * k, (my1 - ink[1]) * k)
                glyphs.add(
                    (x0 - mx0) * k, (my1 - y1) * k,
                    (x1 - mx0) * k, (my1 - y0) * k,
                    # The effective size: `fontsize` is the Tf operand,
                    # which is 1 when the producer scales by the text matrix.
                    size=c.size,
                    font=c.fontname, cid=c.cid if c.cid is not None else -1,
                    mode=c.render_mode or 0, text=c.get_text(),
                    name=(c.glyphname or getattr(c, "inkname", None)
                          or texenc.name_of(c.fontname, c.cid
                                            if c.cid is not None else -1)),
                    ink=ink,
                    # the glyph origin, moved by the text rise
                    base=(my1 - c.matrix[5]
                          - (getattr(c, "rise", 0.0) or 0.0) * c.matrix[3])
                    * k,
                    adv=c.trace[2] * k if hasattr(c, "trace") else None,
                    cause=c.trace[0] if hasattr(c, "trace") else CAUSE_NONE,
                    op=c.trace[1] if hasattr(c, "trace") else 0)
            for o in strokes:
                found = _rule(o)
                if found is not None:
                    x0, x1, y, thickness = found
                    rules.add((x0 - mx0) * k, (x1 - mx0) * k, (my1 - y) * k,
                              thickness * k)
                    continue
                found = _post(o)
                if found is not None:
                    x, y0, y1, thickness = found
                    posts.add((x - mx0) * k, (my1 - y1) * k, (my1 - y0) * k,
                              thickness * k)
            yield PageGlyphs(number, round((mx1 - mx0) * k),
                             round((my1 - my0) * k), glyphs, error, rules,
                             (mx1 - mx0, my1 - my0), posts)
