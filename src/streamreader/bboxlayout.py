# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Warm-up pass with geometry: `pdftotext -bbox-layout`.

One call gives page size, blocks, lines and word boxes in points with a
top-left origin. Constants were measured against MathPix readings of four
~/pdfdrill-library papers (bench/README.md, Step 2).
"""
from __future__ import annotations

import html
import re
import statistics
import subprocess
from pathlib import Path
from typing import NamedTuple

from . import linetypes, mathpix
from .linetypes import Raw
from .warmup import WarmupError, clean

PX_PER_PT = 250 / 72
# -bbox-layout starts a new word at every font change, so `A` and its
# subscript `n` arrive as two words that touch. Words closer than this
# fraction of their height are one word.
WORD_GAP = 0.05
# MathPix `font_size` over the height of a pdftotext word box.
FONT_SIZE_PER_HEIGHT = 0.94

Word = tuple[float, float, float, float, str]


class Line(NamedTuple):
    box: tuple[float, float, float, float]
    words: list[Word]


class Page(NamedTuple):
    width: float
    height: float
    blocks: list[list[Line]]


_N = r'"(-?[\d.]+)"'
_TOKEN = re.compile(
    rf'<page width={_N} height={_N}>'
    rf'|<(block)[ >]'
    rf'|<line xMin={_N} yMin={_N} xMax={_N} yMax={_N}>'
    rf'|<word xMin={_N} yMin={_N} xMax={_N} yMax={_N}>(.*?)</word>', re.S)


def parse(xhtml: str) -> list[Page]:
    pages: list[Page] = []
    for m in _TOKEN.finditer(xhtml):
        g = m.groups()
        if g[0] is not None:
            pages.append(Page(float(g[0]), float(g[1]), []))
        elif g[2] is not None:
            pages[-1].blocks.append([])
        elif g[3] is not None:
            pages[-1].blocks[-1].append(
                Line(tuple(float(v) for v in g[3:7]), []))
        else:
            pages[-1].blocks[-1][-1].words.append(
                (float(g[7]), float(g[8]), float(g[9]), float(g[10]),
                 html.unescape(g[11])))
    return pages


def parse_tsv(tsv: str) -> list[Page]:
    """The same pages from `pdftotext -tsv`: one row per page (level 1),
    block (3), line (4) and word (5), tab separated, half the bytes of the
    XHTML. Word boxes come with two decimals where the XHTML has six."""
    pages: list[Page] = []
    for row in tsv.split("\n")[1:]:
        if not row:
            continue
        f = row.split("\t", 11)
        level = f[0]
        if level == "5":
            x, y = float(f[6]), float(f[7])
            pages[-1].blocks[-1][-1].words.append(
                (x, y, x + float(f[8]), y + float(f[9]), f[11]))
        elif level == "4":
            x, y = float(f[6]), float(f[7])
            pages[-1].blocks[-1].append(
                Line((x, y, x + float(f[8]), y + float(f[9])), []))
        elif level == "3":
            pages[-1].blocks.append([])
        elif level == "1":
            pages.append(Page(float(f[8]), float(f[9]), []))
    return pages


def line_text(words: list[Word]) -> str:
    out = ""
    for i, w in enumerate(words):
        if i:
            p = words[i - 1]
            height = max(p[3] - p[1], w[3] - w[1])
            if w[0] - p[2] >= WORD_GAP * height:
                out += " "
        out += w[4]
    return clean(out)


_WRAP = {"title": ("\\title{\n", "\n}")}
_SILENT = ("page_info", "equation_number")


def emit(doc_id: str, page_no: int, raws: list[Raw], types: list[str],
         width: int, height: int) -> dict:
    """Typed raw lines -> a lines.json page, in MathPix's shapes: a heading
    or title of one line is a leaf carrying its command, one over several
    lines is a container whose text children open and close the command."""
    lines: list[dict] = []
    after_heading = False
    i = 0
    while i < len(raws):
        r, kind = raws[i], types[i]
        number = len(lines) + 1
        if kind in ("section_header", "title"):
            j = i + 1
            while (j < len(raws) and types[j] == kind
                   and raws[j].block == r.block):
                j += 1
            group = raws[i:j]
            opener, closer = _WRAP.get(kind) or (
                "\n\n" + linetypes.header_command(r.text.strip()) + "{", "}")
            texts = [mathpix.escape(g.text) for g in group]
            if len(group) == 1:
                lines.append(mathpix.line(
                    doc_id, page_no, number, kind, texts[0],
                    opener + texts[0] + closer, r.box, r.font_size))
            else:
                box = (min(g.box[0] for g in group),
                       min(g.box[1] for g in group),
                       max(g.box[2] for g in group),
                       max(g.box[3] for g in group))
                parent = mathpix.line_id(doc_id, page_no, number)
                kids = []
                for k, (g, text) in enumerate(zip(group, texts)):
                    display = ((opener if k == 0 else " ") + text
                               + (closer if k == len(group) - 1 else ""))
                    kids.append(mathpix.line(
                        doc_id, page_no, number + 1 + k, "text", text,
                        display, g.box, g.font_size, parent_id=parent))
                lines.append(mathpix.container(
                    doc_id, page_no, number, kind, box, r.font_size,
                    [kid["id"] for kid in kids]))
                lines += kids
            after_heading = True
            i = j
            continue
        text = mathpix.escape(r.text)
        if kind in _SILENT:
            lines.append(mathpix.line(doc_id, page_no, number, kind, text, "",
                                      r.box, r.font_size,
                                      conversion_output=False))
        else:
            starts = r.first_in_block or after_heading
            lines.append(mathpix.line(
                doc_id, page_no, number, "text", text,
                ("\n\n" if starts else " ") + text, r.box, r.font_size))
            after_heading = False
        i += 1
    return mathpix.page(doc_id, page_no, lines, width=width, height=height)


NUMBER_GAP = 2.0        # x its height: how far a number stands off its display
MARGIN_LINES = 3        # lines ending at one x make that x a right margin
_GLUED = re.compile(r"^(.*[.,;:])(\((?:[A-Z]\.)?\d+(?:\.\d+)*[a-z]?\))$")


def _box_of(words: list[Word]) -> tuple[float, float, float, float]:
    return (min(w[0] for w in words), min(w[1] for w in words),
            max(w[2] for w in words), max(w[3] for w in words))


def _split_number(ln: Line, at_margin: bool = False) -> list[Line]:
    """The line, or the line and the equation number that ends it.

    An equation number is text LaTeX generates, not part of the formula:
    MathPix writes it as a line of its own with no output. pdftotext puts it
    on the display's line when the two share a baseline, so it is cut off
    here, where lines are made, and typed like any other. Two forms:

    - a bracketed number standing well off the end of the line;
    - in a display that fills its column, a number set tight against the
      formula's closing punctuation, `R.(12)`, in one word that ends at the
      right margin. pdftotext gives no boxes inside a word, so the number
      takes its share of the word's width by character count.
    """
    words = ln.words
    last = words[-1]
    if (len(words) >= 2 and linetypes.is_equation_number(last[4])
            and last[0] - words[-2][2] >= NUMBER_GAP * (last[3] - last[1])):
        head = words[:-1]
        return [Line(_box_of(head), head), Line(last[:4], [last])]
    glued = _GLUED.match(last[4]) if at_margin else None
    if glued:
        keep, number = glued.groups()
        cut = last[0] + (last[2] - last[0]) * len(keep) / len(last[4])
        head = words[:-1] + [(last[0], last[1], cut, last[3], keep)]
        tail = (cut, last[1], last[2], last[3], number)
        return [Line(_box_of(head), head), Line(tail[:4], [tail])]
    return [ln]


def _margins(page: Page) -> list[float]:
    """Right edges that at least MARGIN_LINES lines of the page end at."""
    edges = sorted(ln.box[2] for block in page.blocks for ln in block)
    tolerance = 0.01 * page.width
    out, i = [], 0
    while i < len(edges):
        j = i
        while j + 1 < len(edges) and edges[j + 1] - edges[i] <= tolerance:
            j += 1
        if j - i + 1 >= MARGIN_LINES:
            out.append(edges[j])
        i = j + 1
    return out


def page_from_boxes(doc_id: str, page_no: int, page: Page) -> dict:
    k = PX_PER_PT
    raws: list[Raw] = []
    margins = _margins(page)
    tolerance = 0.01 * page.width
    for b, block in enumerate(page.blocks):
        first = True
        for ln in (part for whole in block for part in _split_number(
                whole, any(abs(whole.box[2] - m) <= tolerance
                           for m in margins))):
            x0, y0, x1, y1 = (round(v * k) for v in ln.box)
            if y1 - y0 > 3 * (x1 - x0) and len(ln.words) > 1:
                # set up the page: word gaps run along y, not x
                text = clean(" ".join(w[4] for w in ln.words))
            else:
                text = line_text(ln.words)
            if not text.strip():
                continue
            size = statistics.median(w[3] - w[1] for w in ln.words)
            # the glyph warm-up says which words are bold (a sixth field;
            # None for a word without letters)
            said = [w[5] for w in ln.words if len(w) > 5 and w[5] is not None]
            bold = bool(said) and all(said)
            raws.append(Raw(text, (x0, y0, x1, y1),
                            round(size * k * FONT_SIZE_PER_HEIGHT), b, first,
                            bold))
            first = False
    width, height = round(page.width * k), round(page.height * k)
    return emit(doc_id, page_no, raws,
                linetypes.classify(raws, width, height, page_no),
                width, height)


def command(pdf: Path, first: int, last: int) -> list[str]:
    return ["pdftotext", "-bbox-layout", "-f", str(first), "-l", str(last),
            "-enc", "UTF-8", str(pdf), "-"]


def command_tsv(pdf: Path, first: int, last: int) -> list[str]:
    return ["pdftotext", "-tsv", "-f", str(first), "-l", str(last),
            "-enc", "UTF-8", str(pdf), "-"]


def _read(pdf: Path, first: int, last: int, doc_id: str, cmd, parser
          ) -> list[dict]:
    proc = subprocess.run(cmd(pdf, first, last), capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise WarmupError(f"pdftotext failed on {Path(pdf).name}: {msg}")
    boxes = parser(proc.stdout.decode("utf-8", "replace"))
    want = last - first + 1
    if len(boxes) != want:
        raise WarmupError(f"pdftotext returned {len(boxes)} page(s) for "
                          f"{Path(pdf).name} pages {first}-{last}, "
                          f"expected {want}")
    return [page_from_boxes(doc_id, first + i, b)
            for i, b in enumerate(boxes)]


def read_pages(pdf: Path, first: int, last: int, doc_id: str) -> list[dict]:
    return _read(pdf, first, last, doc_id, command, parse)


def read_pages_tsv(pdf: Path, first: int, last: int, doc_id: str
                   ) -> list[dict]:
    return _read(pdf, first, last, doc_id, command_tsv, parse_tsv)
