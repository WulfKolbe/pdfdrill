# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Which text lines continue the line before them, said as MathPix says it.

MathPix puts a `subtype` on the line that continues and lets `text_display`
open accordingly (bench/README.md, "Lines that continue"):

    continues_line_space      " "   joined to the line before by a space
    continues_line_no_hyphen  ""    the line before loses its break hyphen
    continues_line_no_space   ""    joined as it is, the hyphen stays
    continues_line_newline    "\\n"  same block, new line: after a display
    (none)                    a start

Everything here reads one page: the boxes, types and text of its lines.
"""
from __future__ import annotations

SPACE = "continues_line_space"
NO_HYPHEN = "continues_line_no_hyphen"
NO_SPACE = "continues_line_no_space"
NEWLINE = "continues_line_newline"

EDGE = 0.01             # x page width: two edges this close are one edge
EDGE_LINES = 3          # lines ending at one x make that x a right margin
LEADING = 1.0           # x line height: more white than this ends a block
FULL = 0.01             # x page width: a full line ends this near a margin
HANGING = True          # an indented line continues when the next stays in
WIDE = 8.0              # x its height: a narrower line is a cell, not prose
SKIP = 0.0              # x line height of extra white that makes a start: off, measured
AFTER_DISPLAY = True    # a text line after a display continues by newline

_HYPHENS = "-‐­"
_LEAD = {SPACE: " ", NO_HYPHEN: "", NO_SPACE: "", NEWLINE: "\n", None: "\n\n"}
_DISPLAY = ("math", "equation_number")


def _box(ln: dict) -> tuple[int, int, int, int]:
    r = ln["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


def _margins(rights: list[int], tolerance: float) -> list[int]:
    """Right edges that at least EDGE_LINES lines end at."""
    edges = sorted(rights)
    out, i = [], 0
    while i < len(edges):
        j = i
        while j + 1 < len(edges) and edges[j + 1] - edges[i] <= tolerance:
            j += 1
        if j - i + 1 >= EDGE_LINES:
            out.append(edges[j])
        i = j + 1
    return out


def _white(lines: list[dict], body: set[int]) -> float:
    """The usual white between a text line and the one under it."""
    gaps = sorted(
        b[1] - a[3] for a, b in (
            (_box(lines[i - 1]), _box(lines[i]))
            for i in body if i - 1 in body)
        if a[3] <= b[1] + (b[3] - b[1]) and b[1] > a[1])
    return gaps[len(gaps) // 2] if gaps else 0.0


def _joint(before: str, text: str) -> str:
    """How a line joins the full line before it, from where that one ends."""
    end = before.rstrip()
    if not end or end[-1] not in _HYPHENS:
        return SPACE
    if len(end) > 1 and end[-2].isalpha() and text[:1].islower():
        return NO_HYPHEN
    return NO_SPACE


def subtypes(lines: list[dict], page_width: int) -> list[str | None]:
    """One entry per line: its continuation subtype, or None."""
    out: list[str | None] = [None] * len(lines)
    body = {i for i, ln in enumerate(lines)
            if ln["type"] == "text" and "children_ids" not in ln
            and "parent_id" not in ln and ln["region"]["width"] > 0}
    tolerance = EDGE * page_width
    margins = _margins([_box(lines[i])[2] for i in body], tolerance)
    white = _white(lines, body)
    for i in sorted(body):
        if i == 0:
            continue
        before, ln = lines[i - 1], lines[i]
        ax0, ay0, ax1, ay1 = _box(before)
        x0, y0, x1, y1 = _box(ln)
        height = min(ay1 - ay0, y1 - y0)
        under = (y0 + y1 > ay0 + ay1 and y0 - ay1 <= LEADING * height
                 and x0 < ax1 and ax0 < x1)
        if SKIP and y0 - ay1 > white + SKIP * height:
            under = False
        if before["type"] in _DISPLAY:
            j = i - 1
            while j > 0 and lines[j]["type"] in _DISPLAY:
                j -= 1
            first = _box(lines[j])
            if (AFTER_DISPLAY and y0 > ay0
                    and lines[j]["type"] == "text" and x0 <= first[0] + tolerance):
                out[i] = NEWLINE
        elif before["type"] == "text" and i - 1 in body and under:
            full = ax1 - ax0 >= WIDE * (ay1 - ay0) and any(
                -tolerance <= m - ax1 <= FULL * page_width for m in margins)
            flush = x0 <= ax0 + tolerance
            if full and not flush and HANGING and i + 1 < len(lines) \
                    and i + 1 in body:
                nx0, ny0, _, _ = _box(lines[i + 1])
                flush = ny0 > y0 and nx0 >= x0 - tolerance
            if full and flush:
                out[i] = _joint(before["text"], ln["text"])
    return out


def mark(page: dict) -> dict:
    """Set `subtype` and the opening of `text_display` on the page's text
    lines, in place. Running it again gives the same page."""
    lines = page["lines"]
    found = subtypes(lines, page.get("page_width") or 0)
    for i, (ln, sub) in enumerate(zip(lines, found)):
        if (ln["type"] != "text" or "children_ids" in ln
                or "parent_id" in ln or not ln["region"]["width"]):
            continue
        ln.pop("subtype", None)
        display = ln["text_display"].lstrip(" \n")
        if sub is not None:
            _set(ln, sub)
        ln["text_display"] = _LEAD[sub] + display
        if sub == NO_HYPHEN:
            before = lines[i - 1]
            shown = before["text_display"].rstrip()
            if shown and shown[-1] in _HYPHENS:
                before["text_display"] = shown[:-1]
    return page


def _set(ln: dict, sub: str) -> None:
    """`subtype` where MathPix has it: after `text_display`."""
    tail = {k: ln.pop(k) for k in ("confidence", "confidence_rate")
            if k in ln}
    ln["subtype"] = sub
    ln.update(tail)
