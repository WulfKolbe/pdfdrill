"""Node 1 — Ingest pdfplumber .chars.json into DocumentContext.

Builds graphemes string with newlines at detected line breaks,
learns visual templates via run-length clustering, and populates L1 style_run spans.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ..context import (
    CharMeta,
    DefaultStyle,
    DocMeta,
    DocumentContext,
    PageMeta,
    Span,
    STYLE_RUN,
    Template,
    TemplateProperties,
)
from ..engine import Node

# CID glyph code resolution for fonts that pdfplumber can't decode.
# Key: (font_keyword_in_name, cid_number) -> replacement character
_CID_MAP: dict[tuple[str, int], str] = {
    # LMMathExtension / CMEX10 — big delimiters
    ("mathextension", 0): "(", ("mathextension", 1): ")",
    ("mathextension", 4): "[", ("mathextension", 5): "]",
    ("mathextension", 12): "|", ("mathextension", 16): "/",
    ("mathextension", 18): "(", ("mathextension", 19): ")",
    ("mathextension", 22): "{", ("mathextension", 23): "}",
    ("mathextension", 26): "{", ("mathextension", 27): "}",
    ("cmex", 0): "(", ("cmex", 1): ")",
    ("cmex", 4): "[", ("cmex", 5): "]",
    ("cmex", 12): "|", ("cmex", 16): "/",
    ("cmex", 18): "(", ("cmex", 19): ")",
    ("cmex", 22): "{", ("cmex", 23): "}",
    ("cmex", 26): "{", ("cmex", 27): "}",
    # LMMathItalic / CMMI
    ("mathitalic", 15): "ε", ("mathitalic", 21): "α",
    ("mathitalic", 22): "β", ("mathitalic", 26): "ζ",
    ("mathitalic", 13): "γ",
    # LMMathSymbols / CMSY
    ("mathsymbol", 0): "−", ("mathsymbol", 16): "·",
    ("mathsymbol", 17): "×", ("mathsymbol", 20): "≤",
    ("mathsymbol", 21): "≥",
    # MathTime II (MT2xxx)
    ("mt2sy", 0): "−", ("mt2sy", 17): "≈", ("mt2sy", 20): "≤",
    ("mt2sy", 21): "≥",
    ("mt2mi", 13): "γ", ("mt2mi", 21): "α", ("mt2mi", 22): "β",
    ("mt2mi", 26): "ζ",
    ("mt2ex", 0): "(", ("mt2ex", 1): ")",
    ("mt2ex", 16): "/", ("mt2ex", 26): "{", ("mt2ex", 27): "}",
    # TX fonts (txex, txexs, txexas, txbex)
    ("txex", 0): "(", ("txex", 1): ")",
    ("txex", 12): "|", ("txex", 26): "{", ("txex", 27): "}",
    ("txex", 101): "∑", ("txex", 205): "∏",
    ("txex", 32): "√",
    # CMEX larger variants
    ("cmex", 17): "/", ("cmex", 104): "{", ("cmex", 105): "}",
    # MT2 additional
    ("mt2mi", 30): "φ", ("mt2mi", 31): "χ",
    ("mt2sy", 1): "·",
    ("mt2ex", 17): "/",
    # LINE10 (horizontal/vertical rules)
    ("line", 0): "—",
}


def _resolve_cid(text: str, fontname: str) -> str:
    """Replace (cid:XX) glyph codes with their Unicode equivalent."""
    if not text.startswith("(cid:"):
        return text
    import re
    m = re.match(r"\(cid:(\d+)\)", text)
    if not m:
        return text
    cid = int(m.group(1))
    fn_lower = fontname.lower()
    for (font_key, cid_num), replacement in _CID_MAP.items():
        if font_key in fn_lower and cid_num == cid:
            return replacement
    return text


MATH_FONT_KEYWORDS = [
    "mathitalic", "mathsymbol", "mathextension", "msbm", "eufm",
    "symbolmt", "mt-extra", "cmsy", "cmmi", "cmex",
    "mt2mi", "mt2sy", "mt2ex", "mt2ms",
    "newpxmi", "pxsy", "pxmi", "pxex", "newtxmi", "txsy",
    "msam", "cmmib", "cmbsy", "rsfs",
]


def _classify_font(fontname: str) -> str:
    fn = fontname.lower()
    if any(kw in fn for kw in MATH_FONT_KEYWORDS):
        return "math"
    if "boldital" in fn or ("bold" in fn and "ital" in fn):
        return "bold_italic"
    if "bold" in fn or "medi" in fn:
        return "bold"
    if "ital" in fn and "math" not in fn:
        return "italic"
    return "text"


def _color_str(c: Any) -> str:
    if c is None:
        return "#000"
    if isinstance(c, (list, tuple)):
        if len(c) == 1:
            g = int(c[0] * 255) if isinstance(c[0], float) and c[0] <= 1.0 else int(c[0])
            return f"#{g:02x}{g:02x}{g:02x}"
        if len(c) >= 3:
            rgb = []
            for v in c[:3]:
                iv = int(v * 255) if isinstance(v, float) and v <= 1.0 else int(v)
                rgb.append(max(0, min(255, iv)))
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    return "#000"


def _color_distance(a: str, b: str) -> float:
    def _parse(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        h = h.ljust(6, "0")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r1, g1, b1 = _parse(a)
    r2, g2, b2 = _parse(b)
    return math.sqrt((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)


# ---------------------------------------------------------------------------
# Template learning
# ---------------------------------------------------------------------------

class _AttrVec:
    __slots__ = ("font", "size", "color")

    def __init__(self, font: str, size: float, color: str):
        self.font = font
        self.size = round(size, 1)
        self.color = color

    def key(self) -> tuple:
        return (self.font, self.size, self.color)

    def matches(self, other: _AttrVec, size_tol: float = 0.5, color_tol: float = 30.0) -> bool:
        if self.font != other.font:
            return False
        if abs(self.size - other.size) > size_tol:
            return False
        if _color_distance(self.color, other.color) > color_tol:
            return False
        return True


def _learn_templates(
    attr_vecs: list[_AttrVec],
    min_count: int = 5,
) -> tuple[list[Template], list[int]]:
    """Run-length encode attr vectors, cluster, return templates and per-char template indices."""

    # Step 1: run-length encode
    runs: list[tuple[int, int, _AttrVec]] = []
    if not attr_vecs:
        return [], []
    cur = attr_vecs[0]
    start = 0
    for i in range(1, len(attr_vecs)):
        if attr_vecs[i].key() != cur.key():
            runs.append((start, i, cur))
            cur = attr_vecs[i]
            start = i
    runs.append((start, len(attr_vecs), cur))

    # Step 2: count unique vectors
    vec_counts: Counter[tuple] = Counter()
    for s, e, v in runs:
        vec_counts[v.key()] += (e - s)

    # Step 3: cluster similar vectors using greedy union-find
    unique_keys = list(vec_counts.keys())
    cluster_map: dict[tuple, int] = {}
    clusters: list[_AttrVec] = []

    for key in unique_keys:
        vec = _AttrVec(*key)
        merged = False
        for ci, centroid in enumerate(clusters):
            if vec.matches(centroid):
                cluster_map[key] = ci
                merged = True
                break
        if not merged:
            cluster_map[key] = len(clusters)
            clusters.append(vec)

    # Step 4: filter clusters by total character count
    cluster_counts: Counter[int] = Counter()
    for key, count in vec_counts.items():
        cluster_counts[cluster_map[key]] += count

    valid_clusters = {ci for ci, cnt in cluster_counts.items() if cnt >= min_count}

    # Step 5: build templates
    templates: list[Template] = []
    ci_to_tid: dict[int, str] = {}
    for ci in sorted(valid_clusters):
        v = clusters[ci]
        tid = f"T{len(templates)}"
        templates.append(Template(
            id=tid,
            properties=TemplateProperties(font=v.font, size=v.size, color=v.color),
        ))
        ci_to_tid[ci] = tid

    # Step 6: assign per-character template index (-1 = no template)
    tid_list: list[str] = []
    no_template = ""
    for v in attr_vecs:
        ci = cluster_map.get(v.key())
        if ci is not None and ci in ci_to_tid:
            tid_list.append(ci_to_tid[ci])
        else:
            tid_list.append(no_template)

    return templates, tid_list


# ---------------------------------------------------------------------------
# Line-break detection from y-coordinates
# ---------------------------------------------------------------------------

def _split_into_columns(chars: list[dict]) -> list[list[dict]]:
    """Split a page's chars into reading-order COLUMNS (left→right) by detecting a
    vertical gutter — an empty x-band in the central region. Returns [chars] for a
    single-column page. Prevents the 2-column interleaving that merges left+right
    lines at the same y into garbled text."""
    if len(chars) < 60:
        return [chars]
    left = min(c.get("x0", 0) for c in chars)
    right = max(c.get("x1", c.get("x0", 0)) for c in chars)
    width = right - left
    if width <= 0:
        return [chars]
    def cx(c):
        return (c.get("x0", 0) + c.get("x1", c.get("x0", 0))) / 2

    nbins = 100
    binw = width / nbins
    # DENSITY per x-bin (char centres) — a gutter is a LOW-density central band,
    # not necessarily empty: a full-width title/author header puts a few chars in
    # the gutter, so requiring 'empty' fails on real papers. Compare against the
    # typical column density (median of non-empty bins).
    # COVERAGE: each char fills its [x0,x1] bins, so within-column bins stay dense
    # even though glyphs are spaced — otherwise intra-column gaps look like gutters.
    counts = [0] * nbins
    for c in chars:
        a = int((c.get("x0", left) - left) / binw)
        b = int((c.get("x1", c.get("x0", left)) - left) / binw)
        for k in range(max(0, a), min(nbins, b + 1)):
            counts[k] += 1
    nonzero = sorted(v for v in counts if v)
    if not nonzero:
        return [chars]
    typical = nonzero[len(nonzero) // 2]            # median non-empty bin
    lo, hi = int(nbins * 0.35), int(nbins * 0.65)
    gk = min(range(lo, hi + 1), key=lambda k: counts[k])
    if counts[gk] > 0.25 * typical:                 # central band not empty enough
        return [chars]
    gutter = left + (gk + 0.5) * binw
    leftcol = [c for c in chars if cx(c) < gutter]
    rightcol = [c for c in chars if cx(c) >= gutter]
    if min(len(leftcol), len(rightcol)) < 0.15 * len(chars):
        return [chars]                              # one side too small → not 2-col
    return [leftcol, rightcol]


def _detect_line_breaks(chars: list[dict]) -> list[list[dict]]:
    """Group characters into lines by y-coordinate proximity."""
    if not chars:
        return []

    # Median character height for threshold
    heights = [c.get("height", c.get("size", 10)) for c in chars]
    heights.sort()
    median_h = heights[len(heights) // 2] if heights else 10.0
    y_threshold = median_h * 0.4

    lines: list[list[dict]] = []
    current_line: list[dict] = [chars[0]]
    current_top = chars[0].get("top", chars[0].get("y0", 0))

    for c in chars[1:]:
        c_top = c.get("top", c.get("y0", 0))
        if abs(c_top - current_top) > y_threshold:
            # Sort current line by x0 for reading order
            current_line.sort(key=lambda ch: ch.get("x0", 0))
            lines.append(current_line)
            current_line = [c]
            current_top = c_top
        else:
            current_line.append(c)

    if current_line:
        current_line.sort(key=lambda ch: ch.get("x0", 0))
        lines.append(current_line)

    return lines


def _detect_word_gaps(line_chars: list[dict]) -> list[int]:
    """Return indices within line_chars where a space should be inserted."""
    if len(line_chars) < 2:
        return []

    gaps = []
    for i in range(1, len(line_chars)):
        prev_x1 = line_chars[i-1].get("x1", 0)
        cur_x0 = line_chars[i].get("x0", 0)
        gap = cur_x0 - prev_x1
        avg_w = (line_chars[i-1].get("width", 5) + line_chars[i].get("width", 5)) / 2
        if gap > avg_w * 0.3:
            gaps.append(i)
    return gaps


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class IngestPdfplumberNode(Node):
    name = "ingest_pdfplumber"

    def __init__(self, chars_json_path: str | Path):
        self.path = Path(chars_json_path)

    def should_run(self, ctx: DocumentContext) -> bool:
        return self.path.exists()

    def run(self, ctx: DocumentContext) -> DocumentContext:
        with open(self.path, encoding="utf-8") as f:
            raw = json.load(f)

        pages_data = raw.get("pages", [])
        source_name = raw.get("source", self.path.name)

        page_metas = []
        all_text_parts: list[str] = []
        all_attr_vecs: list[_AttrVec] = []
        all_char_meta: list[CharMeta] = []

        global_line_idx = 0

        for page_idx, page in enumerate(pages_data):
            page_metas.append(PageMeta(
                width=page.get("width", 612),
                height=page.get("height", 792),
            ))

            chars = page.get("chars", [])
            if not chars:
                continue

            # Column-aware reading order: split into columns (left→right), then
            # detect lines WITHIN each column so a 2-column page isn't interleaved.
            lines = []
            for col in _split_into_columns(chars):
                col.sort(key=lambda c: (c.get("top", c.get("y0", 0)), c.get("x0", 0)))
                lines.extend(_detect_line_breaks(col))

            for li, line in enumerate(lines):
                space_positions = set(_detect_word_gaps(line))

                for ci, ch in enumerate(line):
                    if ci in space_positions:
                        all_text_parts.append(" ")
                        prev = line[ci - 1] if ci > 0 else ch
                        all_attr_vecs.append(_AttrVec(
                            font=prev.get("fontname", ""),
                            size=prev.get("size", 10.0),
                            color=_color_str(prev.get("non_stroking_color")),
                        ))
                        all_char_meta.append(CharMeta(
                            font_name=prev.get("fontname", ""),
                            font_class=_classify_font(prev.get("fontname", "")),
                            size=prev.get("size", 10.0),
                            x0=ch.get("x0", 0), y0=ch.get("top", ch.get("y0", 0)),
                            x1=ch.get("x0", 0), y1=ch.get("bottom", ch.get("y1", 0)),
                            page=page_idx, line_idx=global_line_idx,
                            baseline=prev.get("bottom", prev.get("y1", 0)),
                        ))

                    ch_text = _resolve_cid(ch.get("text", ""), ch.get("fontname", ""))
                    all_text_parts.append(ch_text)
                    all_attr_vecs.append(_AttrVec(
                        font=ch.get("fontname", ""),
                        size=ch.get("size", 10.0),
                        color=_color_str(ch.get("non_stroking_color")),
                    ))
                    ch_meta = CharMeta(
                        font_name=ch.get("fontname", ""),
                        font_class=_classify_font(ch.get("fontname", "")),
                        size=ch.get("size", 10.0),
                        x0=ch.get("x0", 0), y0=ch.get("top", ch.get("y0", 0)),
                        x1=ch.get("x1", ch.get("x0", 0)),
                        y1=ch.get("bottom", ch.get("y1", 0)),
                        page=page_idx, line_idx=global_line_idx,
                        baseline=ch.get("bottom", ch.get("y1", 0)),
                    )
                    # Multi-char text (e.g. "(cid:12)") needs one meta per char
                    for _ in range(max(1, len(ch_text))):
                        all_char_meta.append(ch_meta)

                if li < len(lines) - 1:
                    all_text_parts.append("\n")
                    last_ch = line[-1] if line else chars[0]
                    all_attr_vecs.append(_AttrVec(
                        font=last_ch.get("fontname", ""),
                        size=last_ch.get("size", 10.0),
                        color=_color_str(last_ch.get("non_stroking_color")),
                    ))
                    all_char_meta.append(CharMeta(
                        font_name="", font_class="text", size=0,
                        page=page_idx, line_idx=global_line_idx,
                    ))

                global_line_idx += 1

            all_text_parts.append("\f")
            last = chars[-1] if chars else {"fontname": "", "size": 10.0}
            all_attr_vecs.append(_AttrVec(
                font=last.get("fontname", ""),
                size=last.get("size", 10.0),
                color=_color_str(last.get("non_stroking_color")),
            ))
            all_char_meta.append(CharMeta(
                font_name="", font_class="text", size=0,
                page=page_idx, line_idx=global_line_idx,
            ))

        full_text = "".join(all_text_parts)

        # Learn templates
        templates, tid_per_char = _learn_templates(all_attr_vecs)

        # Build style_run spans by run-length encoding the template assignments
        style_runs: list[Span] = []
        if tid_per_char:
            cur_tid = tid_per_char[0]
            cur_start = 0
            for i in range(1, len(tid_per_char)):
                if tid_per_char[i] != cur_tid:
                    if cur_tid:
                        style_runs.append(Span(
                            start=cur_start, end=i,
                            kind=STYLE_RUN, template=cur_tid,
                        ))
                    else:
                        # No template — store explicit properties
                        v = all_attr_vecs[cur_start]
                        style_runs.append(Span(
                            start=cur_start, end=i,
                            kind=STYLE_RUN,
                            props={"font": v.font, "size": v.size, "color": v.color},
                        ))
                    cur_tid = tid_per_char[i]
                    cur_start = i
            # Final run
            if cur_tid:
                style_runs.append(Span(
                    start=cur_start, end=len(tid_per_char),
                    kind=STYLE_RUN, template=cur_tid,
                ))
            else:
                v = all_attr_vecs[cur_start]
                style_runs.append(Span(
                    start=cur_start, end=len(tid_per_char),
                    kind=STYLE_RUN,
                    props={"font": v.font, "size": v.size, "color": v.color},
                ))

        # Determine default style from the most common template
        default_style = None
        if templates:
            best = max(
                templates,
                key=lambda t: sum(1 for tid in tid_per_char if tid == t.id),
            )
            default_style = DefaultStyle(
                font=best.properties.font,
                size=best.properties.size,
                color=best.properties.color,
            )

        # Store results on context
        ctx.meta = DocMeta(
            source=source_name,
            pages=page_metas,
            default_style=default_style,
        )
        ctx.graphemes = full_text
        ctx.templates = templates
        ctx.L1 = style_runs
        ctx.char_meta = all_char_meta

        return ctx
