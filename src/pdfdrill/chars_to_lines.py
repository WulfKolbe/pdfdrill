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
        })

    prev_x1 = None
    for c in line:
        if c["t"].isspace():
            flush(); cur.clear(); prev_x1 = c["x1"]; continue
        if prev_x1 is not None and (c["x0"] - prev_x1) > gap and cur:
            flush(); cur.clear()
        cur.append(c); prev_x1 = c["x1"]
    flush()


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
              "t": c["text"], "mi": font_flags(c.get("fontname") or "")}
             for c in chars]
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
    split_x = _column_split(items, pw)
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
    return out
