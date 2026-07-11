"""
The pdfminer leg of the three-source merge — the RICH one.

MathPix gives clean LaTeX + a coarse paragraph box but FLATTENS every local
formatting decision: a bold key term, an italic definiendum, a small-font
footnote, a superscript, a colour change — all become one plain string. The
born-digital text layer, read through pdfminer.six's `LTChar`, still carries all
of it: per-glyph `fontname`, `size`, the CTM `matrix` (exact position/scale), and
the graphics-state colour. This module recovers that signal as **style runs**
and the **font/size changes** MathPix loses, in the MathPix top-left coordinate
convention so it fuses onto the same objects.

Layers:
  * `font_style(name)`         — subset-prefix-stripped {family,bold,italic,mono}
  * `char_records(pdf, pages)` — per-glyph {text,font,size,color,bbox,style} (needs
                                 pdfminer.six; degrades to [] when absent)
  * `font_runs(chars)`         — group adjacent same-style glyphs into runs (+region)
  * `dominant_style(chars)`    — the body font/size (most glyphs)
  * `emphasis_spans(runs,body)`— runs deviating from the body font (the local
                                 formatting MathPix drops), each tagged by kind

Pure functions have no pdfminer dependency; only `char_records` imports it lazily.
"""
from __future__ import annotations

import re

# ── font-name classification ────────────────────────────────────────────────
_SUBSET = re.compile(r"^[A-Z]{6}\+")          # "ABCDEF+" random subset tag
_BOLD_RE = re.compile(r"bold|black|heavy|semibold|cmbx|-bd\b|-bx\b", re.I)
_ITALIC_RE = re.compile(r"italic|oblique|slant|cmti|-it\b", re.I)
_MONO_RE = re.compile(r"mono|courier|typewriter|consol|cmtt|-tt\b", re.I)


def font_style(name: str) -> dict:
    """Classify a font NAME into {family, bold, italic, mono} — subset prefix
    stripped, robust to both TeX (CMBX10/CMTI10/CMTT10) and real-world
    (Arial-BoldMT, NimbusRomNo9L-RegularItalic) conventions."""
    low = _SUBSET.sub("", name or "").lower()
    fam = re.sub(r"\d+$", "", re.sub(r"[-\s].*$", "", low))   # family up to '-'/size
    return {"family": fam,
            "bold": bool(_BOLD_RE.search(low)),
            "italic": bool(_ITALIC_RE.search(low)),
            "mono": bool(_MONO_RE.search(low))}


# ── pdfminer extraction (lazy) ──────────────────────────────────────────────
def available() -> bool:
    try:
        import pdfminer  # noqa: F401
        return True
    except Exception:
        return False


def _page_range(spec, n_pages):
    """'N' / 'N-M' / 'all' / None → a 0-based set of page indices (None = all)."""
    if not spec or str(spec).lower() == "all":
        return None
    out = set()
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a) - 1, int(b)))
        elif part:
            out.add(int(part) - 1)
    return out


def _color_str(gs) -> str:
    """A stable colour string from a glyph's graphics state (fill colour)."""
    for attr in ("ncolor", "scolor"):
        c = getattr(gs, attr, None)
        if c is None:
            continue
        if isinstance(c, (int, float)):
            return f"g{round(float(c), 3)}"
        try:
            return "rgb" + ",".join(str(round(float(v), 3)) for v in c)
        except TypeError:
            return str(c)
    return "black"


def char_records(pdf_path: str, pages=None) -> list[dict]:
    """Per-glyph records in MathPix top-left convention (top = page_h − y1):
    {page, text, font, size, color, x0, top, x1, bottom, family, bold, italic,
    mono}. Returns [] if pdfminer.six is absent. Whitespace glyphs are kept
    (they carry spacing) but empty glyphs are skipped."""
    if not available():
        return []
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextContainer, LTTextLine

    want = _page_range(pages, None)          # 0-based indices to keep, or None=all
    recs: list[dict] = []

    def walk_line(line, page_no, page_h):
        for ch in line:
            if not isinstance(ch, LTChar):
                continue
            t = ch.get_text()
            if t == "":
                continue
            size = round(float(getattr(ch, "size", 0.0)), 2)
            font = getattr(ch, "fontname", "") or ""
            st = font_style(font)
            recs.append({
                "page": page_no, "text": t, "font": font, "size": size,
                "color": _color_str(getattr(ch, "graphicstate", None)),
                "x0": round(ch.x0, 2), "x1": round(ch.x1, 2),
                "top": round(page_h - ch.y1, 2), "bottom": round(page_h - ch.y0, 2),
                **st,
            })

    def walk(obj, page_no, page_h):
        if isinstance(obj, LTTextLine):
            walk_line(obj, page_no, page_h)
        elif isinstance(obj, LTTextContainer):
            for child in obj:
                walk(child, page_no, page_h)

    for idx, layout in enumerate(extract_pages(pdf_path)):
        if want is not None and idx not in want:
            continue
        page_h = layout.height
        for element in layout:
            walk(element, idx + 1, page_h)
    return recs


# ── run grouping + emphasis ─────────────────────────────────────────────────
_STYLE_KEYS = ("page", "font", "size", "bold", "italic", "mono", "color")


def _key(c) -> tuple:
    return tuple(c.get(k) for k in _STYLE_KEYS)


def _same_line(a, b, tol: float = 3.0) -> bool:
    return a["page"] == b["page"] and abs(a["top"] - b["top"]) <= tol


def font_runs(chars: list[dict]) -> list[dict]:
    """Group consecutive same-style glyphs (same font/size/bold/italic/color, on
    the same visual line) into runs. Each run carries the joined text and a
    union `region` in MathPix convention — so a bold key term inside body text
    surfaces as its OWN run (the local formatting MathPix flattens)."""
    runs: list[dict] = []
    cur: list[dict] = []

    def flush():
        if not cur:
            return
        # born-digital PDFs often render inter-word spacing as glyph POSITIONING,
        # not a space glyph — reinsert a space where the x-gap exceeds ~0.25em so
        # the run text is readable ("Formal Concepts", not "FormalConcepts").
        parts = [cur[0]["text"]]
        for prev, c in zip(cur, cur[1:]):
            gap = c["x0"] - prev["x1"]
            if not c["text"].isspace() and not prev["text"].isspace() \
                    and gap > 0.25 * (c.get("size") or 10):
                parts.append(" ")
            parts.append(c["text"])
        text = "".join(parts)
        x0 = min(c["x0"] for c in cur); x1 = max(c["x1"] for c in cur)
        top = min(c["top"] for c in cur); bot = max(c["bottom"] for c in cur)
        f = cur[0]
        runs.append({
            "page": f["page"], "text": text, "font": f["font"], "size": f["size"],
            "bold": f["bold"], "italic": f["italic"], "mono": f["mono"],
            "color": f["color"],
            "region": {"top_left_x": round(x0, 2), "top_left_y": round(top, 2),
                       "width": round(x1 - x0, 2), "height": round(bot - top, 2)},
        })

    for c in chars:
        if cur and (_key(c) != _key(cur[-1]) or not _same_line(c, cur[-1])):
            flush(); cur = []
        cur.append(c)
    flush()
    return runs


def dominant_style(chars: list[dict]) -> dict:
    """The body font: the (font, size) carrying the most glyphs."""
    from collections import Counter
    tally = Counter((c.get("font"), c.get("size")) for c in chars
                    if (c.get("text") or "").strip())
    if not tally:
        return {"font": None, "size": None}
    (font, size), _ = tally.most_common(1)[0]
    return {"font": font, "size": size}


def page_dims(pdf_path: str, pages=None) -> dict:
    """{page_no (1-based): (width_pt, height_pt)} for the PDF's pages — the
    denominators that normalise pdfminer regions to page fractions. {} if
    pdfminer.six is absent."""
    if not available():
        return {}
    from pdfminer.high_level import extract_pages
    want = _page_range(pages, None)
    out: dict[int, tuple] = {}
    for idx, layout in enumerate(extract_pages(pdf_path)):
        if want is not None and idx not in want:
            continue
        out[idx + 1] = (round(layout.width, 2), round(layout.height, 2))
    return out


def _overlap(a, b) -> float:
    """Intersection area of two (x0,y0,x1,y1) fraction boxes (0 if disjoint)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def fuse_emphasis(paragraphs: list[dict], runs: list[dict]) -> dict:
    """Assign each emphasis run to the same-page paragraph it overlaps MOST (all
    boxes in page fractions). A run overlapping no paragraph is left unassigned
    (it stays page-level only). Returns {paragraph_id: [run, ...]} preserving the
    runs' input (reading) order.

    `paragraphs`: [{id, page, frac:(x0,y0,x1,y1)}]; `runs`: [{page, frac, ...}].
    """
    out: dict[str, list[dict]] = {}
    by_page: dict[int, list[dict]] = {}
    for p in paragraphs:
        if p.get("frac"):
            by_page.setdefault(int(p["page"]), []).append(p)
    for r in runs:
        if not r.get("frac"):
            continue
        best, best_ov = None, 0.0
        for p in by_page.get(int(r["page"]), ()):
            ov = _overlap(r["frac"], p["frac"])
            if ov > best_ov:
                best_ov, best = ov, p
        if best is not None and best_ov > 0:
            out.setdefault(best["id"], []).append(r)
    return out


def attach_page_emphasis(doc, spans: list[dict]) -> int:
    """Attach the classified emphasis runs to each model `Page` (matched by
    `page_number`) as `props['font_emphasis']` — the headings / key-terms /
    footnotes MathPix flattened, now queryable per page. Keyed on page number
    only (no coordinate-system mix), idempotent. Returns #pages enriched."""
    by_page: dict[int, list[dict]] = {}
    for s in spans:
        rec = {k: s[k] for k in ("text", "kind", "font", "size", "region")
               if k in s}
        by_page.setdefault(int(s["page"]), []).append(rec)
    n = 0
    for o in doc.objects_of_type("Page"):
        pn = o.props.get("page_number") or o.props.get("page")
        if pn is None:
            continue
        got = by_page.get(int(pn))
        if got:
            o.props["font_emphasis"] = got
            n += 1
    return n


def emphasis_spans(runs: list[dict], body: dict) -> list[dict]:
    """Runs whose style DEVIATES from the body font — the local formatting
    MathPix drops. Each is tagged `kind`: bold / italic / mono / smaller /
    larger (or combined, e.g. 'bold+larger'). Whitespace-only runs are ignored."""
    bsize = body.get("size")
    out: list[dict] = []
    for r in runs:
        if not (r.get("text") or "").strip():
            continue
        tags = []
        if r.get("bold"):
            tags.append("bold")
        if r.get("italic"):
            tags.append("italic")
        if r.get("mono"):
            tags.append("mono")
        if bsize and r.get("size"):
            if r["size"] > bsize + 0.5:
                tags.append("larger")
            elif r["size"] < bsize - 0.5:
                tags.append("smaller")
        if tags:
            out.append({**r, "kind": "+".join(tags)})
    return out
