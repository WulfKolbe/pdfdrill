# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Line types that one page establishes by measurement.

Everything here reads a single page: its line boxes, type sizes and text.
A type is assigned only when its property holds on the page; anything else
stays `text`. Thresholds were tuned against the MathPix exports of the
bench corpus (bench/README.md, Step 5).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import NamedTuple


class Raw(NamedTuple):
    text: str
    box: tuple[int, int, int, int]      # x0, y0, x1, y1 in page pixels
    font_size: int
    block: int
    first_in_block: bool
    bold: bool = False                  # every letter set in a bold face


MARGIN_BAND = 0.15        # folios and running heads live in these shares
MARGIN_WIDTH = 0.75       # ... are narrower than this x body width
MARGIN_GAP = 1.0          # ... and stand this many line heights off the body
MARGIN_LARGER = 1.3       # ... in type no larger than this x the body's
LARGER = 1.15             # a heading's type size over the body's
TITLE_LARGER = 1.25
HEADER_WIDTH = 0.8        # a heading is narrower than this x body width

_EQUATION_NUMBER = re.compile(r"\((?:[A-Z]\.)?\d+(?:\.\d+)*[a-z]?\)")
_SUBNUMBER = re.compile(r"\d+\.\d")
_NUMBERED = re.compile(r"\d+(?:\.\d+)+\.?\s+[A-Z]")
_CHAPTER = re.compile(r"(?:[A-Z]|\d+)(?:\.\d+)*\.?\s+\S")   # 2 Axioms
_CONTENTS_TAIL = re.compile(r"[\s.]\d+$")
_WORD = re.compile(r"[^\W\d_]{3,}")


def _wordy(text: str) -> bool:
    """Prose rather than formula fragments: mostly letters, a real word."""
    solid = text.replace(" ", "")
    letters = sum(c.isalpha() for c in solid)
    return bool(_WORD.search(text)) and letters >= 0.6 * len(solid)


def _margin_rows(raws: list["Raw"], page_height: int, body_size: int,
                 body_width: int, page_no: int = 2) -> set[int]:
    """Indices of the lines in the page's top row and bottom row, when that
    row is a folio or running head: inside the margin share, set little
    larger than the body (words on page 1: no larger), short, and clear of the text by a line height."""
    def larger(r: "Raw") -> float:
        # words in larger type at the top of page 1 are the title
        return 1.05 if page_no == 1 and _wordy(r.text) else MARGIN_LARGER

    found: set[int] = set()
    mids = [(r.box[1] + r.box[3]) / 2 for r in raws]
    for edge in (min, max):
        extreme = edge(mids)
        row = [i for i, m in enumerate(mids)
               if abs(m - extreme) <= 0.5 * (raws[i].box[3] - raws[i].box[1])]
        rest = [i for i in range(len(raws)) if i not in row]
        if not rest:
            continue
        height = max(raws[i].box[3] - raws[i].box[1] for i in row)
        if edge is min:
            inside = extreme < MARGIN_BAND * page_height
            gap = (min(raws[i].box[1] for i in rest)
                   - max(raws[i].box[3] for i in row))
        else:
            inside = extreme > (1 - MARGIN_BAND) * page_height
            gap = (min(raws[i].box[1] for i in row)
                   - max(raws[i].box[3] for i in rest))
        if (inside and gap >= MARGIN_GAP * height
                and all(raws[i].font_size <= larger(raws[i]) * body_size
                        and raws[i].box[2] - raws[i].box[0]
                        < MARGIN_WIDTH * body_width for i in row)):
            found.update(row)
    return found


def is_equation_number(text: str) -> bool:
    return bool(_EQUATION_NUMBER.fullmatch(text.strip()))


def header_command(text: str) -> str:
    return "\\subsection*" if _SUBNUMBER.match(text) else "\\section*"


def classify(raws: list[Raw], page_width: int, page_height: int,
             page_no: int) -> list[str]:
    if not raws:
        return []
    weight: Counter = Counter()
    for r in raws:
        weight[r.font_size] += len(r.text)
    body_size = weight.most_common(1)[0][0]
    body = [r for r in raws if r.font_size == body_size]
    body_width = max(r.box[2] - r.box[0] for r in body)
    margin = _margin_rows(raws, page_height, body_size, body_width,
                          page_no)
    block_lines = Counter(r.block for r in raws)
    largest = max(r.font_size for r in raws)

    out = []
    for i, r in enumerate(raws):
        x0, y0, x1, y1 = r.box
        width, height = x1 - x0, y1 - y0
        text = r.text.strip()
        heading = (r.bold and r.first_in_block and block_lines[r.block] <= 2
                   and width < HEADER_WIDTH * body_width and _wordy(text)
                   and not _CONTENTS_TAIL.search(text)
                   and not text.endswith((".", ",", ":", ";")))
        if height > 3 * width and x1 < 0.12 * page_width:
            kind = "page_info"                      # stamp up the margin
        elif (heading and _CHAPTER.match(text)
              and (y0 + y1) / 2 < (1 - MARGIN_BAND) * page_height):
            kind = "section_header"                 # 2 Axioms, in bold
        elif i in margin:
            kind = "page_info"                      # folio, running head
        elif _EQUATION_NUMBER.fullmatch(text):          # alone on its line
            kind = "equation_number"
        elif not _wordy(text):
            kind = "text"
        elif (page_no == 1 and r.font_size == largest
              and r.font_size >= TITLE_LARGER * body_size
              and (y0 + y1) / 2 < 0.45 * page_height):
            kind = "title"
        elif (r.font_size >= LARGER * body_size
              and width < HEADER_WIDTH * body_width
              and block_lines[r.block] <= 3):
            kind = "section_header"
        elif (_NUMBERED.match(text) and not _CONTENTS_TAIL.search(text)
              and r.first_in_block and block_lines[r.block] <= 2
              and width < HEADER_WIDTH * body_width):
            kind = "section_header"                 # 1.2. Like this
        else:
            kind = "text"
        out.append(kind)
    return out
