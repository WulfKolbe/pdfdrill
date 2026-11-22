"""
chars_to_lines — convert a pdfplumber CHARACTER dump to a MathPix-shape
lines.json, so a born-digital PDF (one that already has a text layer) becomes
drillable OFFLINE with no MathPix spend.

Input shape (pdfplumber chars, PDF bottom-left origin):
    {"source", "total_pages", "pages":[{"page_number","width","height",
                                         "chars":[{"x0","y0","x1","y1","text",...}]}]}

We flip each char to the MathPix top-left origin (y down), group chars into
visual lines by baseline, split lines into words on x-gaps, and hand the word
records to `ocr_lines.lines_json_from_words` (the proven offline assembler —
line grouping + region + out-of-column tagging), tagged source
"pdfplumber-chars". Pure + unit-testable.

**Two-column reading order.** A naive y-baseline clustering MERGES the left and
right columns of a two-column paper (arXiv/IEEE/ACM): left-column and right-column
text at the same height land on one visual line and interleave ("left words RIGHT
WORDS"). We detect a vertical GUTTER (a low-density x-band in the page middle) and
group + order lines PER COLUMN — left column top-to-bottom, then right column — so
the prose reads correctly. A line that truly spans the gutter (title, wide caption)
is kept whole. Single-column pages are detected as such and unaffected.
"""
from __future__ import annotations

import statistics
from typing import Any

from . import ocr_lines
from .font_image_layers import _classify_font_family
from .text_normalize import normalize_pua


def font_flags(fontname: str) -> tuple[bool, bool]:
    """(is_math, is_italic) for one font name — the two glyph classes an
    equation is built from. `_classify_font_family` never reports both, so the
    counts never double-count a glyph."""
    _b, m, _bd, it = _classify_font_family(fontname or "")
    return m, it


def font_run_key(fontname: str, size: float) -> tuple:
    """(family, size, bold, italic) — what a RUN of glyphs shares.

    T-0156, the owner's rule of 2026-11-22: fix at the lowest level. The
    weight was already here and was being thrown away. `_classify_font_family`
    returns `(base_name, is_math, is_bold, is_italic)` and `font_flags`
    unpacked `is_bold` into `_bd` and dropped it, per character, on the route
    that reads the PDF's own TEXT LAYER — so every typer downstream worked
    without it.

    What that cost, each measured before this existed: a description-list rule
    that could not tell a bold label from a heading and failed at precision
    0.50; `refnum` holding mathematics, guarded at two display sites instead
    of typed at the source; paragraphs merged 2.6 to one for want of a block.

    RUNS, NOT ONE FONT PER LINE. A description label is a bold run at the
    START of a body line, so the line's dominant font is the body's and a
    per-line field would drop exactly the label it is wanted for.
    """
    base, _m, bold, italic = _classify_font_family(fontname or "")
    return (base, round(float(size or 0.0), 1), bool(bold), bool(italic))


def is_math_font(fontname: str) -> bool:
    """True if `fontname` is a MATH font (CM*/AMS/OpenSymbol/MT Extra/…).

    Shares the single classifier used by the font layer, so the math-font list
    is defined in exactly one place — a second copy here would drift, and a font
    recognised by `pdfdrill fonts` but not by the chars route (or the reverse)
    is precisely how math goes missing without anyone noticing.
    """
    return _classify_font_family(fontname or "")[1]


def _norm_pua(s: str) -> str:
    """Map the VERIFIED private-use glyphs to plain text; unknown PUA is kept
    verbatim (never guessed) — `pdfdrill model` reports what was left."""
    return normalize_pua(s)[0]


def _column_split(items: list[dict], page_width: float) -> "float | None":
    """The x of a two-column GUTTER, or None for a single column. Found as a
    low-density valley in the middle of the char-x-center histogram, requiring
    both sides to carry a real share of the text (so a single column, or a page
    with a stray centred element, is not mis-split)."""
    if page_width <= 0 or len(items) < 60:
        return None
    centers = [(i["x0"] + i["x1"]) / 2 for i in items]
    nb = 48
    binw = page_width / nb
    hist = [0] * nb
    for c in centers:
        b = int(c / binw)
        if 0 <= b < nb:
            hist[b] += 1
    lo, hi = int(nb * 0.38), int(nb * 0.62)
    band = range(lo, hi + 1)
    mid = min(band, key=lambda b: hist[b])
    nonzero = [h for h in hist if h]
    median = statistics.median(nonzero) if nonzero else 0
    if median == 0 or hist[mid] > 0.12 * median:      # no clear valley → 1 column
        return None
    split_x = (mid + 0.5) * binw
    left = sum(1 for c in centers if c < split_x)
    right = len(centers) - left
    if min(left, right) < 0.25 * len(centers):         # unbalanced → not 2 columns
        return None
    return split_x


def _spans_gutter(line: list[dict], page_width: float) -> bool:
    """True when this y-line is ONE continuous run of text across the page
    middle -- a full-width title, abstract, caption or footer -- rather than a
    two-column line.

    EXTENT ALONE CANNOT TELL THE TWO APART: a two-column line runs from the
    left column's first glyph to the right column's last and is just as wide as
    a full-width one. The internal GAP is what separates them, which is the
    same test `_line_columns` applies further down.
    """
    xs = sorted(line, key=lambda i: i["x0"])
    if len(xs) < 2:
        return False
    if xs[-1]["x1"] - xs[0]["x0"] < 0.5 * page_width:
        return False                       # too narrow to hide a gutter
    gutter_min = max(6.0, 0.015 * page_width)
    lo, hi = 0.30 * page_width, 0.70 * page_width
    reach = xs[0]["x1"]
    for it in xs[1:]:
        if it["x0"] - reach > gutter_min and lo <= (reach + it["x0"]) / 2 <= hi:
            return False                   # a real gutter gap -> two columns
        reach = max(reach, it["x1"])
    return True


def _gutter_by_gap(items: list[dict], page_width: float,
                   y_from: "float | None" = None) -> "float | None":
    """The gutter as the EMPTY VERTICAL BAND the ink actually shows.

    `_column_split` looks for a density valley in a 48-bin histogram of glyph
    centres and rejects it unless the emptiest bin holds under 12% of the
    median bin. THAT CANNOT WORK WHEN THE GUTTER IS NARROWER THAN A BIN, and on
    a normal paper it is. Measured on the owner's arxiv.2209.02970
    (2026-11-16), an ACL two-column paper, 595.3 pt wide:

        bin width                                    12.40 pt
        the real gutter, by zero ink coverage (p2)    x 292..304, 12 pt
        emptiest bin in the gutter band (bin 24)      34 chars
        median non-empty bin                          98
        threshold, 0.12 * median                      11.8

    The gutter straddles bins 23 and 24 — bin 23 holds the left column's last
    glyphs, bin 24 the right column's first — so NO BIN CAN EVER BE EMPTY: the
    deepest achievable valley is about 65% where the test demands 88%. All 21
    pages read as one column, and the line clusterer then welded a left-column
    line to a right-column line as one: "1 Introduction tions, benchmarks, and
    datase", "L Computing and Natural Language (CCNL). dat". The owner reported
    it as "2 column design not recognized".

    A band of x at which NO glyph paints is not a proxy for a gutter, it is the
    gutter. Both sides must still carry a real share of the glyphs, so a page
    with one narrow stray column is not split.

    `y_from` restricts the measurement to the glyphs below that y, which is how
    a page whose header block spans the full width is handled — see
    `_column_split_for_lines`.
    """
    if page_width <= 0:
        return None
    rows = [i for i in items
            if y_from is None or (i.get("top") is not None and i["top"] >= y_from)]
    if len(rows) < 60:
        return None
    width = int(page_width) + 2
    painted = bytearray(width)
    for i in rows:
        a = max(0, int(i["x0"]))
        b = min(width - 1, int(i["x1"]))
        for x in range(a, b + 1):
            painted[x] = 1
    lo, hi = int(0.30 * page_width), int(0.70 * page_width)
    best = None
    run = None
    for x in range(lo, hi + 1):
        if not painted[x]:
            run = x if run is None else run
            continue
        if run is not None and (best is None or x - run > best[1] - best[0]):
            best = (run, x)
        run = None
    if run is not None and (best is None or hi - run > best[1] - best[0]):
        best = (run, hi)
    if best is None or best[1] - best[0] < max(6.0, 0.012 * page_width):
        return None
    split_x = (best[0] + best[1]) / 2.0
    left = sum(1 for i in rows if (i["x0"] + i["x1"]) / 2 < split_x)
    if min(left, len(rows) - left) < 0.25 * len(rows):
        return None
    return split_x


def _header_block_cuts(items: list[dict], page_width: float) -> list[float]:
    """The y values below which a page's spanning header block has ended.

    A title, an author list or a wide figure above the body paints right across
    the middle at its own y, so the gutter is empty BELOW it and not over the
    whole page. Excluding full-width ROWS is not enough and that was measured:
    on arxiv.2209.02970 p1 the author block carries internal spaces wide enough
    that `_spans_gutter` calls it two columns and keeps its glyphs, which fill
    the gutter again. Cutting by y removes them whichever way they classify.

    The cuts are the row bottoms in the page's top half, nearest first, so the
    caller stops at the first cut where a gutter appears. No constant fraction
    of the page is assumed: where the body starts is what the cut finds.
    """
    tops = sorted({float(i["top"]) for i in items
                   if i.get("top") is not None}, )
    if not tops:
        return []
    page_mid = tops[0] + 0.5 * (tops[-1] - tops[0])
    return [t for t in tops if t <= page_mid]


def _column_split_for_lines(items: list[dict], page_width: float) -> "float | None":
    """`_column_split`, but blind to full-width lines.

    A full-width line puts glyphs right across the page middle and so FILLS the
    density valley the gutter is found by. On a page that is full-width at the
    top and two-column below -- a paper's first page, an abstract or a spanning
    figure above the body -- that defeated detection for the WHOLE page: the
    columns below were then read y-major, which interleaves them, and the line
    clusterer welded a left-column line to a right-column line as one line.

    Measured on the owner's arxiv.2602.06992 (2026-11-10). Pages 3 and 7, two
    columns throughout, were detected at split_x 303.9 and 291.5. Pages 1 and 2,
    which carry a full-width abstract above the body, returned None -- and
    restricting the histogram to the y-band BELOW the abstract found page 2's
    gutter at the same 303.9. That is what named the cause.

    So the valley is measured over the non-full-width lines only. The full-width
    lines are not discarded: `_line_columns` still keeps each of them whole,
    because it finds no gutter gap inside them.
    """
    if page_width <= 0 or not items:
        return None
    heights = [i["bottom"] - i["top"] for i in items
               if i.get("bottom") is not None and i["bottom"] > i["top"]]
    tol = (statistics.median(heights) * 0.6) if heights else 3.0
    rows: dict[int, list[dict]] = {}
    for i in items:
        rows.setdefault(round(i["top"] / max(tol, 0.1)), []).append(i)
    # THE GAP FIRST, because it is evidence and the histogram is a proxy. A
    # band of x where no glyph paints IS the gutter; a density valley only
    # stands in for one, and cannot be found at all when the gutter is
    # narrower than a histogram bin (`_gutter_by_gap` carries the numbers).
    split = _gutter_by_gap(items, page_width)
    if split is not None:
        return split
    # No clean band over the whole page: a spanning header block paints across
    # the middle. Try again below it, nearest cut first.
    for cut in _header_block_cuts(items, page_width):
        split = _gutter_by_gap(items, page_width, y_from=cut)
        if split is not None:
            return split
    narrow = [i for ln in rows.values()
              if not _spans_gutter(ln, page_width) for i in ln]
    split = _column_split(narrow, page_width)
    if split is not None:
        return split
    # Not enough non-full-width text to measure: answer exactly as the
    # whole-page detector did before this function existed.
    return _column_split(items, page_width)

def _line_columns(line: list[dict], split_x: float, gutter_min: float):
    """Split one y-line into per-column fragments. Yields (col, items): col 0/1
    for a genuine two-column line (a real gap at the gutter), or col 0 for a line
    that spans the gutter (continuous text — a full-width title/caption), kept
    whole so it isn't torn in two."""
    left = [c for c in line if (c["x0"] + c["x1"]) / 2 < split_x]
    right = [c for c in line if (c["x0"] + c["x1"]) / 2 >= split_x]
    if not left or not right:
        return [(0 if left else 1, line)]
    lmax = max(c["x1"] for c in left)
    rmin = min(c["x0"] for c in right)
    if rmin - lmax > gutter_min:                       # real gutter gap → two columns
        return [(0, left), (1, right)]
    return [(0, line)]                                 # spans the gutter → keep whole


def _runs_of(chars: list[dict]) -> list[dict]:
    """Consecutive glyphs sharing (family, size, bold, italic), as records.

    `start` is the offset INSIDE this word's text; the line assembler shifts
    it to the line's own offsets when it joins the words.
    """
    out: list[dict] = []
    off = 0
    for c in chars:
        key = c.get("fr")
        if out and out[-1]["_k"] == key:
            off += len(c["t"])
            continue
        fam, size, bold, italic = key if key else ("", 0.0, False, False)
        out.append({"start": off, "family": fam, "size": size,
                    "bold": bold, "italic": italic, "_k": key})
        off += len(c["t"])
    for r in out:
        r.pop("_k", None)
    return out


def _emit_words(line: list[dict], pg, li: int, out: list[dict]) -> None:
    """Group one (column-)line's chars into words on x-gaps; append to `out`."""
    line = sorted(line, key=lambda i: i["x0"])
    widths = [i["x1"] - i["x0"] for i in line if i["x1"] > i["x0"]]
    gap = (statistics.median(widths) * 0.4) if widths else 1.5
    cur: list[dict] = []

    def flush() -> None:
        if not cur:
            return
        out.append({
            "page": pg, "block": 0, "line": li,
            "x0": min(c["x0"] for c in cur), "x1": max(c["x1"] for c in cur),
            "y0": min(c["top"] for c in cur), "y1": max(c["bottom"] for c in cur),
            # A PDF's own text layer can map glyphs into the Unicode PRIVATE USE
            # AREA via /ToUnicode (OpenOffice's OpenSymbol does this for stretchy
            # math delimiters). Those codepoints extract "correctly" but are
            # font-private noise downstream — normalise the verified ones HERE,
            # the single seam where born-digital text becomes a line.
            "text": _norm_pua("".join(c["t"] for c in cur).strip()),
            # Carry the math-font share through to the line assembler. pdfminer
            # knows the font of every glyph, so it CAN see mathematics — dropping
            # that here was why the born-digital route reported zero formulas on
            # papers full of them.
            "math_chars": sum(1 for c in cur if c["mi"][0]),
            "italic_chars": sum(1 for c in cur if c["mi"][1]),
            "n_chars": len(cur),
            "runs": _runs_of(cur),
        })

    prev_x1 = None
    for c in line:
        if c["t"].isspace():
            flush(); cur.clear(); prev_x1 = c["x1"]; continue
        if prev_x1 is not None and (c["x0"] - prev_x1) > gap and cur:
            flush(); cur.clear()
        cur.append(c); prev_x1 = c["x1"]
    flush()


def _turned_lines(turned: list[dict]) -> list[list[dict]]:
    """Group the page's TURNED glyphs into their own lines, by column of x.

    A GLYPH THAT IS NOT UPRIGHT IS NOT ON THE LINE THAT SHARES ITS y. pdfplumber
    and pdfminer both state this per glyph -- `upright`, from the text matrix --
    and this module read the flag nowhere, so a rotated glyph was clustered by
    its `top` like any other.

    Measured on the owner's arxiv.2209.02970 p1 (2026-11-16). The arXiv e-print
    stamp `arXiv:2209.02970v3 [cs.CL] 30 Mar 2023` is printed up the left
    margin, rotated 90 degrees: 40 glyphs, every one `upright: False`, matrix
    (0, 1, -1, 0, 32, 232), and the only ink left of x=40 on the page. Every
    body glyph on the same page is `upright: True`. Because each stamp glyph
    sits at its own y, each one joined a DIFFERENT body line, and 31 of the
    page's 58 reader lines began with a stray character:

        '3 ligence, paving ways to the general intell'
        '2 gence. However, the reality presents two u'
        '0 gent challenges: existing foundation model'

    The owner reported it as "left sidenote with bar code not separated". It is
    worse than unseparated: it corrupts the first word of half the page's
    prose, and no later pass can tell the stray character from the text.

    A turned run reads along y, so its glyphs are grouped by x -- a new line
    whenever x jumps by more than the run's own median glyph width -- and
    ordered by y within the run. The text is not rotated back or reinterpreted:
    it is kept as its own record, in reading order after the upright lines, for
    whatever reads the model to label (a margin stamp here, a rotated table
    header elsewhere). Nothing is discarded.
    """
    if not turned:
        return []
    widths = [i["x1"] - i["x0"] for i in turned if i["x1"] > i["x0"]]
    tol = max((statistics.median(widths) if widths else 3.0) * 1.5, 2.0)
    turned.sort(key=lambda i: (i["x0"], i["top"]))
    out: list[list[dict]] = []
    for it in turned:
        if out and abs(it["x0"] - out[-1][-1]["x0"]) <= tol:
            out[-1].append(it)
        else:
            out.append([it])
    for run in out:
        # A +90 turn advances UP the page, so the run reads from the largest
        # `top` to the smallest. Getting this backwards reads the arXiv stamp
        # as '3202 raM 03 ]LC.sc[ 3v07920.9022:viXra', which is how the
        # direction came to be carried at all.
        up_the_page = sum(i.get("turn", 0) for i in run) >= 0
        run.sort(key=lambda i: -i["top"] if up_the_page else i["top"])
    return out


def _image_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per raster the page paints, typed `figure`.

    This route reported no image of any kind. Measured on the owner's
    arxiv.2209.02970 (2026-11-16): the reading held 1,555 `text` records, 1
    `math`, and NO image record on any of its 21 pages, while the page paints
    three 6x6 pt images on p1 and a 454 x 114 pt raster on p9. `pdfdrill` even
    writes `probe-pdfimages-list.txt` beside the document naming them. The
    owner reported it as "images not separated".

    `figure` is the type `PictureProcessor` claims (`diagram` is
    `DiagramProcessor`'s and is for vector art). The record carries the BOX and
    no pixels: a crop is taken from the page at the resolution the caller
    wants, and inventing text for a raster would be a reading nobody made.
    """
    out: list[dict[str, Any]] = []
    ph = float(page.get("height") or 0)
    for i, im in enumerate(page.get("images") or []):
        try:
            x0, x1 = float(im["x0"]), float(im["x1"])
            y0, y1 = float(im["y0"]), float(im["y1"])
        except (KeyError, TypeError, ValueError):
            continue
        top, bottom = ph - y1, ph - y0
        if x1 <= x0 or bottom <= top:
            continue
        out.append({
            "id": "%s-img%d" % (page.get("page_number"), i),
            "type": "figure",
            "text": "",
            "text_display": "",
            "region": {"top_left_x": round(x0, 2), "top_left_y": round(top, 2),
                       "width": round(x1 - x0, 2), "height": round(bottom - top, 2)},
        })
    return out


def _page_words(page: dict[str, Any]) -> list[dict[str, Any]]:
    pg = page.get("page_number")
    ph = float(page.get("height") or 0)
    pw = float(page.get("width") or 0)
    chars = [c for c in (page.get("chars") or []) if (c.get("text") or "") != ""]
    if not chars:
        return []
    # to top-left origin (y down): top = ph - y1, bottom = ph - y0
    items = [{"x0": float(c["x0"]), "x1": float(c["x1"]),
              "top": ph - float(c["y1"]), "bottom": ph - float(c["y0"]),
              "t": c["text"], "mi": font_flags(c.get("fontname") or ""),
              # the run this glyph belongs to: (family, size, bold, italic)
              "fr": font_run_key(c.get("fontname") or "", c.get("size") or 0.0),
              # A TURNED GLYPH IS NOT ON THIS LINE. `upright` is in the input
              # and was being dropped here; see `_turned_lines`.
              "up": bool(c.get("upright", True)),
              "turn": int(c.get("turn", 0) or 0)}
             for c in chars]
    # The turned glyphs come out BEFORE the page is measured or clustered, so
    # they cannot join an upright line, cannot fill a column gutter, and cannot
    # shift the median line height every threshold here is expressed in.
    turned = [i for i in items if not i["up"]]
    items = [i for i in items if i["up"]]
    # NO FALLBACK INTO THE UPRIGHT PATH. Pushing the turned glyphs through it
    # when a page has no upright ones read a sideways page BACKWARDS and one
    # glyph per line -- 'e l t i t e g a p s y a w e d i s'. A page of only
    # turned glyphs (a rotated plate, a landscape table) goes through
    # `_turned_lines` like any other turned run, which is what orders it.
    heights = [i["bottom"] - i["top"] for i in items if i["bottom"] > i["top"]]
    tol = (statistics.median(heights) * 0.6) if heights else 3.0
    items.sort(key=lambda i: (round(i["top"] / max(tol, 0.1)), i["x0"]))

    # cluster into visual lines by baseline proximity
    lines: list[list[dict]] = []
    for it in items:
        if lines and abs(it["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(it)
        else:
            lines.append([it])

    # COLUMN-AWARE ordering: split each y-line into column fragments, then read
    # left column (top→bottom) before right column instead of interleaving them.
    split_x = _column_split_for_lines(items, pw)
    if split_x is None:
        frags = [(0, ln[0]["top"], ln) for ln in lines]      # single column
    else:
        gutter_min = max(6.0, 0.015 * pw)
        frags = []
        for ln in lines:
            for col, part in _line_columns(ln, split_x, gutter_min):
                frags.append((col, part[0]["top"], part))
    frags.sort(key=lambda f: (f[0], f[1]))                    # column, then y

    words: list[dict[str, Any]] = []
    for li, (_col, _y, frag) in enumerate(frags):
        _emit_words(frag, pg, li, words)
    for frag in _turned_lines(turned):
        _emit_words(frag, pg, len(frags), words)
    return [w for w in words if w["text"]]


# A line is display math when this share of its glyphs comes from a math font.
# High on purpose: a sentence carrying one ™, bullet or stray Greek from a
# symbol font must stay prose. A real equation is nearly all math glyphs.
# An equation line is built from two glyph classes, and WHICH one dominates
# depends on the producer:
#   TeX        - variables AND operators are math fonts (CMMI/CMSY) -> math share
#                alone is already ~1.0
#   OpenOffice - operators are OpenSymbol but variables are Times-*Italic*, so the
#                math share of a real equation is only ~0.4 and a math-only
#                threshold silently classifies every formula as prose.
# Measured on 1012.3259 (OpenOffice Writer): "At=An*e*sin2pi*fn*tpn" is 40% math
# + 40% italic. So the test is math+italic share, gated on at least two actual
# math glyphs -- an italic phrase in running prose carries none and is unaffected.
_MATH_LINE_SHARE = 0.6
_MATH_LINE_MIN = 2          # a single lone symbol is never an equation


def _type_math_lines(lines_json: dict[str, Any]) -> int:
    """Retype math-font-dominated lines from `text` to `math` (in place).

    Returns how many lines were retyped. This is the seam where the born-digital
    route stops discarding what pdfminer already told it: EquationProcessor and
    FormulaProcessor key on the line TYPE, so a correctly-read equation left
    labelled `text` produces no math object at all.
    """
    n = 0
    for page in lines_json.get("pages", []):
        for line in page.get("lines", []):
            if line.get("type") != "text":
                continue
            tot = line.pop("n_chars", 0) or 0
            mth = line.pop("math_chars", 0) or 0
            ita = line.pop("italic_chars", 0) or 0
            if (tot and mth >= _MATH_LINE_MIN
                    and (mth + ita) / tot >= _MATH_LINE_SHARE):
                line["type"] = "math"
                n += 1
    return n


def chars_to_lines_json(data: dict[str, Any]) -> dict[str, Any]:
    """Born-digital char dump → MathPix-compatible lines.json dict. The dump's own
    `source` label is preserved (pdfminer-chars / pdfplumber-chars).

    Math-font-dominated lines are typed `math` (see `_type_math_lines`) so the
    docmodel's equation/formula processors can build real objects from them.
    """
    words: list[dict] = []
    dims: dict[int, tuple[float, float]] = {}
    for page in data.get("pages", []):
        pg = page.get("page_number")
        dims[pg] = (float(page.get("width") or 0), float(page.get("height") or 0))
        words.extend(_page_words(page))
    out = ocr_lines.lines_json_from_words(
        words, dims, source=data.get("source", "pdfplumber-chars"))
    out["math_lines_typed"] = _type_math_lines(out)
    _append_image_lines(out, data.get("pages", []))
    return out

def _append_image_lines(out: dict, pages: list) -> int:
    """Put each page's image records into the assembled lines.json.

    Called by BOTH entry points, because `tests/test_chars_streaming.py`
    asserts the streaming route is byte-identical to the whole-document one.
    Two copies of this would be the one thing a memory optimisation must not
    do, so there is one.

    A page the assembler never emitted (all of its glyphs dropped, or a page of
    nothing but a raster) still gets its page entry here -- otherwise a
    full-page image would be the one thing a reading of it cannot show.
    """
    by_no = {p.get("page"): p for p in out.get("pages") or []}
    added = 0
    for page in pages:
        lines = _image_lines(page)
        if not lines:
            continue
        pg = page.get("page_number")
        entry = by_no.get(pg)
        if entry is None:
            entry = {"page": pg, "image_id": "p%s" % pg,
                     "page_width": float(page.get("width") or 0),
                     "page_height": float(page.get("height") or 0),
                     "lines": []}
            out.setdefault("pages", []).append(entry)
            by_no[pg] = entry
        entry.setdefault("lines", []).extend(lines)
        added += len(lines)
    return added


def lines_json_streaming(page_iter, *, source: str = "pdfplumber-chars") -> dict:
    """Char dump -> lines.json, processing ONE page at a time.

    `chars_to_lines_json` needs every page's glyphs in memory at once, and the
    caller has already materialised them all: on a 491-page book that is 2.2 GB
    for 1.3M glyphs (~1.7 KB each), and the library holds a 6216-page manual.

    Nothing here needs the whole document. Columns, words and lines are all
    decided WITHIN a page, and `lines_json_from_words` groups by (page, block,
    line) — so a page can be converted and its glyphs dropped before the next is
    read. Peak memory becomes one page instead of a book.

    Output is byte-identical to `chars_to_lines_json` (asserted in
    tests/test_chars_streaming.py); this is the same computation, ordered
    differently.
    """
    pages_out: list = []
    typed = 0
    for page in page_iter:
        pg = page.get("page_number")
        dims = {pg: (float(page.get("width") or 0), float(page.get("height") or 0))}
        one = ocr_lines.lines_json_from_words(_page_words(page), dims, source=source)
        typed += _type_math_lines(one)
        _append_image_lines(one, [page])
        pages_out.extend(one.get("pages") or [])
        del page                                  # release this page's glyphs
    # Exactly the keys `chars_to_lines_json` emits — an extra field here would
    # make the two routes distinguishable downstream, which is the one thing a
    # memory optimisation must not do.
    return {"source": source, "pages": pages_out, "math_lines_typed": typed}
