# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Warm-up pass: pdftotext text, one lines.json page per PDF page."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import mathpix


class WarmupError(RuntimeError):
    pass


# A glyph whose font has no usable Unicode map reaches pdftotext as its raw
# character code or a private-use code point. MathPix text never contains
# either, so both become U+FFFD: visibly unknown, for a later pass to resolve.
_UNMAPPED = re.compile("[\x00-\x08\x0b-\x1f\ue000-\uf8ff]")


def clean(text: str) -> str:
    return _UNMAPPED.sub("\ufffd", text)


def split_pages(out: str) -> list[str]:
    parts = out.split("\f")
    if parts and parts[-1].strip() == "":
        parts.pop()
    return parts


# ---- `pdftotext -layout`: a character grid of the page ----------------
#
# -layout keeps each printed row on one output row, so the pieces of a
# formula stay together; the price is that two columns share a row. A
# column is recovered from the grid itself: a band of character positions
# that is empty in most rows, with text on both sides of it.
_GAP = re.compile(" {3,}")
GUTTER_EMPTY = 0.3      # share of rows that may cross a gutter
GUTTER_BOTH = 0.4       # share of rows with text on both sides of it
GUTTER_SPAN = (0.3, 0.7)    # where in the text width a gutter may lie


def _segments(row: str) -> list[tuple[int, int, str]]:
    """(first column, last column + 1, text) of each run of the row."""
    out, pos = [], 0
    for part in _GAP.split(row):
        start = row.index(part, pos) if part else pos
        pos = start + len(part)
        if part.strip():
            lead = len(part) - len(part.lstrip())
            out.append((start + lead, pos, part.strip()))
    return out


def _gutter(rows: list[str]) -> tuple[int, int] | None:
    filled = [r for r in rows if r.strip()]
    if len(filled) < 4:
        return None
    width = max(len(r) for r in filled)
    left = min(len(r) - len(r.lstrip()) for r in filled)
    used = [0] * width
    for r in filled:
        for c, ch in enumerate(r):
            if ch != " ":
                used[c] += 1
    lo = left + int(GUTTER_SPAN[0] * (width - left))
    hi = left + int(GUTTER_SPAN[1] * (width - left))
    limit = GUTTER_EMPTY * len(filled)
    best, c = None, lo
    while c < hi:
        if used[c] <= limit:
            end = c
            while end < hi and used[end] <= limit:
                end += 1
            if end - c >= 2:
                crossing = sum(used[c:end]) / (end - c)
                if best is None or crossing < best[0]:
                    best = (crossing, c, end)
            c = end
        else:
            c += 1
    if best is None:
        return None
    _, a, b = best
    both = sum(1 for r in filled if r[:a].strip() and r[b:].strip())
    return (a, b) if both >= GUTTER_BOTH * len(filled) else None


_TWO_SPACES = re.compile(" {2,}")


def _across(row: str, segs: list[tuple[int, int, str]],
            gutter: tuple[int, int]) -> list[tuple[bool, str]] | None:
    """Each run of the row with its side of the gutter, or None when a run
    crosses it. A long left line may reach the gutter and leave only two
    spaces before the right column: such a run is cut there."""
    a, b = gutter
    out: list[tuple[bool, str]] = []
    for start, end, text in segs:
        if end <= b or start >= a:
            out.append((start >= a, text))
            continue
        cut = next((m for m in _TWO_SPACES.finditer(row, start, end)
                    if m.start() < b and m.end() > a), None)
        if cut is None:
            return None
        out.append((False, row[start:cut.start()].strip()))
        out.append((True, row[cut.end():end].strip()))
    return [(side, t) for side, t in out if t]


def layout_blocks(page_text: str) -> list[list[str]]:
    """Blocks of lines from one page of `pdftotext -layout` output, each
    column read before the next. A blank row ends a block."""
    rows = [clean(r.rstrip()) for r in page_text.split("\n")]
    gutter = _gutter(rows)
    out: list[list[str]] = []
    left: list[list[str]] = [[]]
    right: list[list[str]] = [[]]
    spanning: list[str] | None = None     # the open block of full-width rows

    def flush() -> None:
        for column in (left, right):
            out.extend(b for b in column if b)
        left[:], right[:] = [[]], [[]]

    for row in rows:
        segs = _segments(row)
        if not segs:
            spanning = None
            left.append([])
            right.append([])
        elif gutter is None:
            if spanning is None:
                spanning = []
                out.append(spanning)
            spanning.extend(text for _, _, text in segs)
        else:
            parts = _across(row, segs, gutter)
            if parts is None:                   # a row spanning the columns
                flush()
                if spanning is None:
                    spanning = []
                    out.append(spanning)
                spanning.extend(text for _, _, text in segs)
            else:
                spanning = None
                for is_right, text in parts:
                    (right if is_right else left)[-1].append(text)
    flush()
    return [b for b in out if b]


def page_from_text(doc_id: str, page_no: int, page_text: str) -> dict:
    lines: list[dict] = []
    for block in layout_blocks(page_text):
        for i, text in enumerate(block):
            lines.append(mathpix.text_line(
                doc_id, page_no, len(lines) + 1, mathpix.escape(text),
                starts_paragraph=(i == 0)))
    return mathpix.page(doc_id, page_no, lines)


def command(pdf: Path, first: int, last: int) -> list[str]:
    # -layout, not reading-order mode: a printed row stays one row, which
    # keeps the pieces of a formula together. `layout_blocks` undoes the
    # price, two columns sharing a row. Measured in bench/README.md.
    return ["pdftotext", "-layout", "-f", str(first), "-l", str(last),
            "-enc", "UTF-8", str(pdf), "-"]


def read_pages(pdf: Path, first: int, last: int, doc_id: str) -> list[dict]:
    proc = subprocess.run(command(pdf, first, last), capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise WarmupError(f"pdftotext failed on {Path(pdf).name}: {msg}")
    texts = split_pages(proc.stdout.decode("utf-8", "replace"))
    want = last - first + 1
    if len(texts) != want:
        raise WarmupError(f"pdftotext returned {len(texts)} page(s) for "
                          f"{Path(pdf).name} pages {first}-{last}, "
                          f"expected {want}")
    return [page_from_text(doc_id, first + i, t)
            for i, t in enumerate(texts)]
