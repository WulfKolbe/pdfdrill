"""Node: Detect lines and paragraphs from grapheme string + char positions.

Uses newline/form-feed positions and char-level x-coordinates to detect:
- Body text left margin per page
- First-line indentation (LaTeX \\parindent style)
- Centered lines (display equations, titles)
- Paragraph breaks from blank lines and indentation
- The page's top and bottom band — folio, running head, copyright line,
  licence stamp — which is furniture, not text (T-0011)

A PAGE TURN IS NOT A PARAGRAPH BREAK. It used to be one here
("Page break always starts new paragraph"), which split every paragraph
that runs over a page and then let the furniture between the two halves
into the text. This route has no subtypes to read the join off, so the
evidence is geometric: the band the body text occupies, and whether the
line before the turn ends a sentence. `structmd` solves the same problem
from the tag tree and pdf2mmd2 from `page_info`; the three routes are not
mixed.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter

from ..context import (
    CharMeta,
    DocumentContext,
    Span,
    FURNITURE,
    PARAGRAPH,
    HEADING,
)
from ..engine import Node


class LinesParagraphsNode(Node):
    name = "lines_paragraphs"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        char_meta = ctx.char_meta if ctx.char_meta else None

        if char_meta and len(char_meta) == len(text):
            spans = _detect_paragraphs_with_positions(text, char_meta)
        else:
            spans = _detect_paragraphs_simple(text)

        ctx.L2.extend(spans)
        return ctx


# ---------------------------------------------------------------------------
# Position-aware paragraph detection
# ---------------------------------------------------------------------------

#: A folio, a running head, a copyright line or a licence stamp is SHORT.
#: A wrapped body line is not: on the documents measured for T-0011 the body
#: lines run 60-90 visible characters and the band lines 8-53. The limit is
#: the first guard, because a long line in the band is far more likely to be
#: text the band estimate got wrong than a folio.
FURNITURE_MAX_CHARS = 80

#: A line counts as a BODY line for the purpose of learning the band only if
#: it is this long. Short lines are exactly the ambiguous ones (headings, the
#: last line of a paragraph, equation numbers), and letting them set the band
#: would widen it until nothing is outside it.
BAND_SAMPLE_MIN_CHARS = 40

#: How far outside the body band a line has to sit, in body line heights.
BAND_MARGIN_LINES = 0.5

#: Percentiles of the body band. Not min/max: one body line that pdfplumber
#: places a few points high (a superscript, a tall glyph) would otherwise
#: stretch the band over the running head.
BAND_LOW_PCT, BAND_HIGH_PCT = 2.0, 98.0

#: A normalized band line that appears on at least this many pages is
#: furniture BY REPETITION — the strongest evidence available in a route that
#: has no tags: the same string in the same band on many pages is a property
#: of the page, whatever it says.
FURNITURE_MIN_PAGES = 3

#: Generic rights/licence wording. A document's front matter and its page
#: stamp share this vocabulary, which is the point: it is furniture wherever
#: it sits in the band. No document-specific string appears here — a stamp
#: that names a licensee must never be matched by its licensee.
_RIGHTS = re.compile(
    r"(?:©|\(c\)\s*\d|copyright|all rights reserved|licen[cs]|"
    r"reproduction|not for (?:resale|distribution)|provided by|"
    r"creativecommons|single[- ]user)", re.I)

#: A bare folio: a page number, with or without the usual decoration, in
#: arabic or roman numerals. `iii`, `12`, `- 12 -`, `Page 12`, `12 of 340`.
_FOLIO = re.compile(
    r"^(?:page\s+)?[\[\(\-–—\s]*(?:\d{1,4}|[ivxlcdm]{1,7})"
    r"(?:\s*(?:/|of|von)\s*\d{1,4})?[\]\)\-–—\s\.]*$", re.I)

#: Digits vary from page to page; the SHAPE does not. "Page 12" and
#: "Page 13" are the same running furniture.
_DIGITS = re.compile(r"\d+")

#: A word, for the purpose of asking whether the document uses it in its
#: prose or only in its page band.
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

#: How close two lines' tops have to be to count as the same ROW of the page
#: grid, in points. A footer printed from the same template lands within a
#: point of itself; ISO 32000-2's bottom row is y 823.1-823.2 on 1,042 lines
#: over 1,023 pages.
ROW_TOLERANCE = 1.5

#: A row of the page grid on which confirmed furniture appears on at least
#: this many pages is a FURNITURE ROW, and a short line there is furniture by
#: position alone. This is what catches what a per-line signal cannot: the
#: footer cut short (9 lines on ISO 32000-2, each a pure prefix of the
#: canonical form, repeating on one or two pages only, so neither repetition
#: nor rights wording nor a folio could reach it), and the tail of a stamp
#: that pdfplumber split over two lines.
FURNITURE_ROW_MIN_PAGES = 3

#: The least raw characters of the row's canonical line a longer line must
#: begin with before its PREFIX is taken as that row's furniture. Below this a
#: match is a coincidence, and the line stays text.
ROW_PREFIX_MIN_CHARS = 12

#: Words shorter than this decide nothing: a three-letter word is shared by
#: the stamp and the prose (one of them occurs 1,985 times in ISO 32000-2,
#: half of those inside furniture).
VOCAB_MIN_WORD_CHARS = 4

#: A word has to occur this often before its distribution is evidence.
VOCAB_MIN_OCCURRENCES = 3

#: A word that the document uses mostly OUTSIDE furniture is a prose word.
#: One such word in the tail of a fused line keeps that tail as prose; with
#: none, the whole line is the band. The default is deliberately that way
#: round: a tail of band vocabulary and a seven-digit group is a licence
#: stamp, and a stamp reaching the reading text is the worse failure.
VOCAB_PROSE_MAX_INSIDE = 0.5

#: How much has to be LEFT after that prefix before the line counts as fused
#: rather than as the band line itself (which varies by a few characters from
#: page to page — a folio gains a digit, a date changes).
ROW_FUSED_MIN_REST = 8


def _normalized(s: str) -> str:
    return _DIGITS.sub("#", " ".join(s.split())).strip().lower()


def _terminal(s: str) -> bool:
    """Does this line end a sentence?

    Closing brackets and quotes are allowed to follow the stop. A line ending
    in a hyphen is the clearest possible statement that it does NOT end here.
    """
    t = s.rstrip()
    if not t:
        return True
    if t.endswith("-") or t.endswith("­"):
        return False
    t = t.rstrip("\"'’”)]}»›")
    return bool(t) and t[-1] in ".!?:;"


def _line_geometry(
    lines: list[tuple[int, int, int]],
    text: str,
    char_meta: list[CharMeta],
) -> list[tuple[float, float, int]]:
    """(y_top, y_bottom, visible_length) per line; (0, 0, 0) when unknown."""
    out: list[tuple[float, float, int]] = []
    for ls, le, _page in lines:
        tops: list[float] = []
        bots: list[float] = []
        n = 0
        for idx in range(ls, min(le, len(char_meta))):
            if text[idx].isspace():
                continue
            n += 1
            cm = char_meta[idx]
            if cm.y0 or cm.y1:
                tops.append(cm.y0)
                bots.append(cm.y1)
        out.append((min(tops) if tops else 0.0, max(bots) if bots else 0.0, n))
    return out


def _furniture_lines(
    lines: list[tuple[int, int, int]],
    geom: list[tuple[float, float, int]],
    text: str,
) -> dict[int, str]:
    """Which lines are page furniture, on what evidence, and where exactly.

    Returns `(whole, prefixes)`: line index -> why for lines that ARE
    furniture, and line index -> (start, end, why) for a line that merely
    BEGINS with the band line of its row and carries text after it.

    Three independent signals, each sufficient, all of them requiring the
    line to be SHORT and to sit OUTSIDE the band the body text occupies:
    repetition across pages, rights/licence wording, a bare folio. A line
    inside the body band is never furniture here, however much it looks like
    a folio — a page number in the middle of a page is part of the text (a
    cross-reference, a table cell), and this route cannot tell which.
    """
    # A repeating line is excluded from the band sample, whatever its length.
    # A licence stamp can be 64 characters wide and sit on every page of a
    # thousand-page standard; sampled as body text it pushes the band past
    # the foot of the page, and then NOTHING is outside the band — which is
    # exactly how the bottom band went undetected on the first document
    # measured for T-0011.
    pages_of_all: dict[str, set[int]] = {}
    for (ls, le, page), (_y0, _y1, n) in zip(lines, geom):
        if n:
            pages_of_all.setdefault(_normalized(text[ls:le]), set()).add(page)

    def _sampled(i: int) -> bool:
        if geom[i][2] < BAND_SAMPLE_MIN_CHARS:
            return False
        ls, le, _p = lines[i]
        if _RIGHTS.search(text[ls:le]):
            # A line that says it is about rights is not a sample of the body
            # band. Three unique 47-54 character stamp lines at the foot of a
            # 14-page standard were enough to put the 98th percentile past
            # the page edge, after which nothing was outside the band and the
            # whole bottom band went undetected (gate 3, ISO/TS 32001).
            return False
        return len(pages_of_all.get(_normalized(text[ls:le]), ())) < FURNITURE_MIN_PAGES

    sample = [i for i in range(len(lines)) if _sampled(i)]
    if len(sample) < 5:
        # A document whose long lines all repeat (boilerplate, a form, a
        # fixture) leaves nothing to sample. A wide band is still better
        # than no band: fall back to every long line.
        sample = [i for i in range(len(lines))
                  if geom[i][2] >= BAND_SAMPLE_MIN_CHARS]
    tops = [geom[i][0] for i in sample if geom[i][0]]
    bots = [geom[i][1] for i in sample if geom[i][1]]
    if len(tops) < 5 or len(bots) < 5:
        return {}                      # too little body text to learn a band
    heights = [geom[i][1] - geom[i][0] for i in sample
               if geom[i][1] > geom[i][0]]
    line_h = statistics.median(heights) if heights else 12.0
    band_top = _pct(tops, BAND_LOW_PCT) - BAND_MARGIN_LINES * line_h
    band_bottom = _pct(bots, BAND_HIGH_PCT) + BAND_MARGIN_LINES * line_h

    def _outside(i: int) -> bool:
        y0, y1, n = geom[i]
        if not n or not (y0 or y1):
            return False
        return bool((y1 and y1 < band_top) or (y0 and y0 > band_bottom))

    outside = [i for i in range(len(lines))
               if _outside(i) and geom[i][2] <= FURNITURE_MAX_CHARS]

    found: dict[int, str] = {}
    for i in outside:
        body = text[lines[i][0]:lines[i][1]].strip()
        norm = _normalized(body)
        if len(pages_of_all.get(norm, ())) >= FURNITURE_MIN_PAGES:
            found[i] = "repeats"
        elif _RIGHTS.search(body):
            found[i] = "rights"
        elif _FOLIO.match(body):
            found[i] = "folio"

    # ---- second pass: the ROWS of the page grid that furniture prints on ----
    #
    # A per-line signal cannot reach a footer that was cut short: the fragment
    # repeats on one page, carries no rights wording and is no folio. Its
    # POSITION still does — it is on the row where 1,001 of 1,023 pages print
    # the same line. So rows confirmed by the first pass are evidence in their
    # own right, and a short line on one of them is furniture by position.
    rows: dict[float, set[int]] = {}
    row_bodies: dict[float, Counter] = {}
    for i, why in found.items():
        key = round(geom[i][0] / (2 * ROW_TOLERANCE))
        rows.setdefault(key, set()).add(lines[i][2])
        row_bodies.setdefault(key, Counter())[
            " ".join(text[lines[i][0]:lines[i][1]].split())] += 1
    confirmed = {k for k, pages in rows.items()
                 if len(pages) >= FURNITURE_ROW_MIN_PAGES}

    prefixes: dict[int, tuple[int, int, str]] = {}
    fused: list[tuple[int, int, int, int]] = []
    for i in range(len(lines)):
        if not _outside(i):
            continue
        key = round(geom[i][0] / (2 * ROW_TOLERANCE))
        if key not in confirmed:
            continue
        ls, le, _page = lines[i]
        line = text[ls:le]
        canon = row_bodies[key].most_common(1)[0][0]
        k = _canonical_prefix(line, canon)
        rest = len(line.rstrip()) - k
        if k >= ROW_PREFIX_MIN_CHARS and rest >= ROW_FUSED_MIN_REST:
            # The row's line and something else ran together — pdfplumber
            # does this often enough to matter. Whether that something else
            # is prose is a question about VOCABULARY, and the document
            # answers it: a word the document uses mostly outside furniture
            # is a prose word, and one of those in the tail keeps the tail.
            fused.append((i, ls, le, k))
        elif i not in found and geom[i][2] <= FURNITURE_MAX_CHARS:
            found[i] = "row"

    vocab = _band_vocabulary(lines, text, found) if fused else {}
    for i, ls, le, k in fused:
        if _prose_tail(text[ls + k:le], vocab):
            prefixes[i] = (ls, ls + k, "row prefix")
            found.pop(i, None)
        else:
            # Band vocabulary all the way to the end of the line: this is the
            # stamp, printed longer on this page than on the others. Taking
            # only the prefix left 46 graphemes of it — including a
            # seven-digit group — in the reading text of ISO 32000-2, on the
            # one page where that happens (audit, 2026-10-14).
            found[i] = "row fused"
    return found, prefixes


def _band_vocabulary(lines, text, found) -> dict[str, tuple[int, int]]:
    """word -> (occurrences inside furniture, occurrences in the document).

    One pass over the document, and only when a fused line has to be judged.
    No cache: a cache here would have to be keyed by the furniture set as
    well as by the text, and this is called once per document.
    """
    inside: Counter = Counter()
    total: Counter = Counter()
    for m in _WORD.finditer(text):
        total[m.group(0).lower()] += 1
    for i in found:
        ls, le, _page = lines[i]
        for m in _WORD.finditer(text[ls:le]):
            inside[m.group(0).lower()] += 1
    return {w: (inside[w], n) for w, n in total.items()}


def _prose_tail(tail: str, vocab: dict[str, tuple[int, int]]) -> bool:
    """Does this tail contain a word the document uses mostly as prose?"""
    for m in _WORD.finditer(tail):
        w = m.group(0).lower()
        if len(w) < VOCAB_MIN_WORD_CHARS:
            continue
        ins, tot = vocab.get(w, (0, 0))
        if tot >= VOCAB_MIN_OCCURRENCES and ins / tot < VOCAB_PROSE_MAX_INSIDE:
            return True
    return False


def _canonical_prefix(line: str, canon: str) -> int:
    """How many characters of `line` are the row's canonical band line.

    Digits are wildcards (a folio changes every page) and a run of whitespace
    matches a run of whitespace (the column gap is not a character count).
    Returns 0 unless the line STARTS with it.
    """
    i = j = 0
    while i < len(line) and j < len(canon):
        a, b = line[i], canon[j]
        if a.isspace() and b.isspace():
            while i < len(line) and line[i].isspace():
                i += 1
            while j < len(canon) and canon[j].isspace():
                j += 1
            continue
        if a == b or (a.isdigit() and b.isdigit()):
            i += 1
            j += 1
            continue
        break
    return i


def _pct(values: list[float], pct: float) -> float:
    xs = sorted(values)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _detect_paragraphs_with_positions(
    text: str,
    char_meta: list[CharMeta],
) -> list[Span]:
    """Detect paragraphs using char-level x-coordinates.

    Computes body margin per page, detects first-line indentation,
    and avoids splitting at centered display lines.
    """
    # Step 1: split into lines by \n and \f positions
    lines: list[tuple[int, int, int]] = []  # (start, end, page)
    line_start = 0
    current_page = 0

    for i, ch in enumerate(text):
        if ch == "\n" or ch == "\f":
            if i > line_start:
                lines.append((line_start, i, current_page))
            if ch == "\f":
                current_page += 1
            line_start = i + 1

    if line_start < len(text):
        content = text[line_start:].strip()
        if content:
            lines.append((line_start, len(text), current_page))

    if not lines:
        return []

    # Step 2: compute body margin per page
    page_margins: dict[int, float] = {}
    page_line_x0s: dict[int, list[float]] = {}

    for ls, le, page in lines:
        line_text = text[ls:le].strip()
        if len(line_text) < 20:
            continue  # skip short lines (headings, eq numbers)
        # Find x0 of first non-whitespace char with metadata
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace():
                cm = char_meta[idx]
                if cm.x0 > 0 and cm.font_class == "text":
                    page_line_x0s.setdefault(page, []).append(round(cm.x0, 0))
                    break

    for page, x0s in page_line_x0s.items():
        if x0s:
            counts = Counter(x0s)
            page_margins[page] = counts.most_common(1)[0][0]

    default_margin = 78.0  # fallback
    if page_margins:
        all_margins = list(page_margins.values())
        all_margins.sort()
        default_margin = all_margins[len(all_margins) // 2]

    # Step 2b: compute body text size (most common font size)
    all_text_sizes: list[float] = []
    for ls, le, page in lines:
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace() and char_meta[idx].size > 0:
                if char_meta[idx].font_class in ("text", "bold", "italic"):
                    all_text_sizes.append(round(char_meta[idx].size, 0))
    body_size = 10.0
    if all_text_sizes:
        size_counts = Counter(all_text_sizes)
        body_size = size_counts.most_common(1)[0][0]

    # Step 3: classify each line
    LINE_TEXT = "text"
    LINE_INDENT = "indent"       # first-line indentation
    LINE_CENTERED = "centered"   # display equation or title
    LINE_HEADING = "heading"     # bold/larger font
    LINE_SHORT = "short"         # very short line (last line of paragraph)
    LINE_BLANK = "blank"
    LINE_FURNITURE = "furniture"

    classified: list[tuple[int, int, int, str, float]] = []  # (start, end, page, class, font_size)

    # Step 3a: the page band. Done BEFORE the per-line classification, because
    # a running head in a larger font reads as a heading and a folio reads as
    # a centered line; both are the page's furniture whatever font they use.
    geom = _line_geometry(lines, text, char_meta)
    # `furniture`: whole lines. `band_prefix`: a line that begins with the
    # row's band line and continues into text — the band part only.
    furniture, band_prefix = _furniture_lines(lines, geom, text)

    for line_i, (ls, le, page) in enumerate(lines):
        line_text = text[ls:le]
        stripped = line_text.strip()

        if not stripped:
            classified.append((ls, le, page, LINE_BLANK, 0.0))
            continue

        if line_i in furniture:
            classified.append((ls, le, page, LINE_FURNITURE, 0.0))
            continue

        # Find first non-space char's properties
        margin = page_margins.get(page, default_margin)
        first_x0 = 0.0
        first_class = "text"
        first_size = body_size
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace():
                first_x0 = char_meta[idx].x0
                first_class = char_meta[idx].font_class
                first_size = char_meta[idx].size
                break

        # Compute dominant font size for this line
        line_sizes = [char_meta[idx].size for idx in range(ls, min(le, len(char_meta)))
                      if not text[idx].isspace() and char_meta[idx].size > 0]
        line_size = max(line_sizes) if line_sizes else body_size

        indent = first_x0 - margin if first_x0 > 0 else 0
        is_large_font = line_size > body_size * 1.15

        if is_large_font and len(stripped) < 80:
            classified.append((ls, le, page, LINE_HEADING, line_size))
        elif len(stripped) < 10 and indent > 50:
            classified.append((ls, le, page, LINE_CENTERED, line_size))
        elif first_class == "bold" and len(stripped) < 60:
            classified.append((ls, le, page, LINE_HEADING, line_size))
        elif indent > 15 and indent < 40:
            classified.append((ls, le, page, LINE_INDENT, line_size))
        elif indent > 40:
            classified.append((ls, le, page, LINE_CENTERED, line_size))
        elif len(stripped) < 30:
            classified.append((ls, le, page, LINE_SHORT, line_size))
        else:
            classified.append((ls, le, page, LINE_TEXT, line_size))

    # Step 4: group lines into paragraphs
    #
    # A paragraph now ends at its last CONTENT line, never at `classified[i-1]`
    # — that line may be the furniture of the page just left, and a paragraph
    # must not end on a folio. The page turn itself decides nothing: the
    # decision is deferred to the first content line of the new page, which is
    # the only thing that can say whether the sentence goes on.
    spans: list[Span] = []
    para_start = -1
    para_end = -1                       # end of the last content line in it
    para_text = ""                      # that line's text, for the sentence test
    para_pages: list[int] = []
    holes: list[list[int]] = []         # furniture ranges INSIDE the open para
    pending: list[list[int]] = []       # furniture since the last content line
    prev_page = -1
    turned = False

    def _flush() -> None:
        nonlocal para_start, para_end, para_text, holes, pending, para_pages
        if para_start >= 0 and para_end > para_start:
            props: dict = {}
            if len(para_pages) > 1:
                props["pages"] = list(para_pages)
                props["continued_over_page_turn"] = True
            if holes:
                # what the projection takes out, by offset, so the grapheme
                # stream never has to move for a reader to see one paragraph
                props["furniture_holes"] = [list(h) for h in holes]
            spans.append(Span(start=para_start, end=para_end, kind=PARAGRAPH,
                              props=props or None))
        para_start, para_end, para_text = -1, -1, ""
        holes, pending, para_pages = [], [], []

    for i, (ls, le, page, lclass, lsize) in enumerate(classified):
        if page != prev_page:
            if para_start >= 0:
                turned = True
            prev_page = page

        if lclass == LINE_FURNITURE:
            spans.append(Span(start=ls, end=le, kind=FURNITURE,
                              props={"page": page, "why": furniture[i]}))
            if para_start >= 0:
                pending.append([ls, le])
            continue

        if lclass == LINE_BLANK:
            _flush()
            turned = False
            continue

        if lclass == LINE_HEADING:
            _flush()
            spans.append(Span(
                start=ls, end=le,
                kind=HEADING,
                props={"font_size": lsize},
            ))
            turned = False
            continue

        if lclass == LINE_INDENT:
            _flush()
            para_start, para_end, para_text = ls, le, text[ls:le]
            para_pages = [page]
            turned = False
            continue

        # A line that begins with its row's band line: the band part is a
        # furniture span of its own and the paragraph starts after it.
        pre = band_prefix.get(i)
        if pre:
            spans.append(Span(start=pre[0], end=pre[1], kind=FURNITURE,
                              props={"page": page, "why": pre[2]}))
            if para_start >= 0:
                pending.append([pre[0], pre[1]])
            ls = pre[1]

        # a content line. If a page turn happened since the last content line,
        # this is where the paragraph is either continued or closed.
        if para_start >= 0:
            if turned and _terminal(para_text):
                _flush()               # the sentence ended on the old page
            elif pending:
                # the band sits INSIDE this paragraph. Page turn or not: a
                # footer with text after it on the same page is still a hole,
                # and on ISO 32000-2 there are 24 of those — the projection
                # dropped them either way, but the paragraph that contains
                # them has to say so.
                holes.extend(pending)
                pending = []
        turned = False

        if para_start < 0:
            para_start = ls
            para_pages = [page]
        if page not in para_pages:
            para_pages.append(page)
        para_end, para_text = le, text[ls:le]

    _flush()

    # Filter empty
    return [s for s in spans if text[s.start:s.end].strip()]


# ---------------------------------------------------------------------------
# Fallback: simple paragraph detection (no char positions)
# ---------------------------------------------------------------------------

def _detect_paragraphs_simple(text: str) -> list[Span]:
    """Split text into paragraphs using only newlines and form feeds."""
    spans: list[Span] = []
    i = 0
    para_start = 0

    while i < len(text) and text[i] in ("\n", "\f", " "):
        i += 1
    para_start = i

    while i < len(text):
        ch = text[i]
        if ch == "\f":
            if i > para_start and text[para_start:i].strip():
                spans.append(Span(start=para_start, end=i, kind=PARAGRAPH))
            i += 1
            while i < len(text) and text[i] in ("\n", "\f", " "):
                i += 1
            para_start = i
        elif ch == "\n" and i + 1 < len(text) and text[i + 1] in ("\n", "\f"):
            if i > para_start and text[para_start:i].strip():
                spans.append(Span(start=para_start, end=i, kind=PARAGRAPH))
            i += 1
            while i < len(text) and text[i] in ("\n", "\f", " "):
                i += 1
            para_start = i
        else:
            i += 1

    if para_start < len(text) and text[para_start:].strip():
        spans.append(Span(start=para_start, end=len(text), kind=PARAGRAPH))

    return spans
