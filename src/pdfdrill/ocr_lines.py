"""
Tesseract OCR → enriched, MathPix-compatible `lines.json`.

Drop-in replacement for pdfdrill's `ocr_lines.py` (see
docs/superpowers/specs/2026-07-13-enriched-ocr-lines-design.md). Preserves the
full tesseract TSV fidelity — per-word boxes + confidence, block/paragraph/line
hierarchy — as additive keys on the same lines.json shape the docmodel already
ingests. Stdlib only; tesseract + ghostscript via subprocess.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

RASTER_MIN_DPI = 400    # pdfdrill floors gs rendering to 400 DPI (pdf_reading.py)
OCR_TIMEOUT = 300       # seconds per page (tesseract)
RASTER_TIMEOUT = 1800   # seconds per document (ghostscript)
PSM = 1                 # tesseract page segmentation: auto + OSD


def tools_available() -> tuple[bool, str]:
    """Return (ok, message). Needs Ghostscript (the only rasterizer) + tesseract."""
    have_gs = any(shutil.which(t) for t in ("gs", "gswin64c", "gswin32c"))
    missing = []
    if not have_gs:
        missing.append("ghostscript")
    if shutil.which("tesseract") is None:
        missing.append("tesseract")
    if missing:
        return False, (
            f"OCR needs {' and '.join(missing)} on PATH. Install ghostscript + "
            f"tesseract-ocr (plus a language pack, e.g. tesseract-ocr-eng)."
        )
    return True, ""


def parse_tsv(tsv_text: str) -> tuple[list[dict], dict[int, tuple[float, float]]]:
    """Parse tesseract/pdftotext TSV into (words, page_dims) — legacy shape.

    words: [{page, block, line, x0, y0, x1, y1, text}] from level-5 rows.
    page_dims: {page: (width, height)} from level-1 rows.
    """
    rows = tsv_text.splitlines()
    if not rows:
        return [], {}
    header = rows[0].split("\t")
    idx = {h: i for i, h in enumerate(header)}
    need = ("level", "page_num", "block_num", "line_num", "left", "top",
            "width", "height", "text")
    if not all(k in idx for k in need):
        return [], {}

    words: list[dict] = []
    page_dims: dict[int, tuple[float, float]] = {}
    for r in rows[1:]:
        c = r.split("\t")
        if len(c) < len(header):
            continue
        try:
            level = int(c[idx["level"]])
            page = int(c[idx["page_num"]])
            left = float(c[idx["left"]]); top = float(c[idx["top"]])
            w = float(c[idx["width"]]); h = float(c[idx["height"]])
        except ValueError:
            continue
        text = c[idx["text"]]
        if level == 1:
            page_dims[page] = (w, h)
        elif level == 5 and text.strip():
            words.append({
                "page": page,
                "block": int(c[idx["block_num"]]),
                "line": int(c[idx["line_num"]]),
                "x0": left, "y0": top, "x1": left + w, "y1": top + h,
                "text": text,
            })
    return words, page_dims


def _empty_enriched() -> dict:
    """Fresh empty enriched-parse result."""
    return {"page_dims": {}, "blocks": [], "pars": [], "lines": [], "words": []}


def _typed_row(c: list[str], idx: dict[str, int]) -> dict | None:
    """Parse one TSV row's 12 cells into typed values; None if unparseable."""
    try:
        return {
            "level": int(c[idx["level"]]), "page": int(c[idx["page_num"]]),
            "block_num": int(c[idx["block_num"]]),
            "par_num": int(c[idx["par_num"]]),
            "line_num": int(c[idx["line_num"]]),
            "word_num": int(c[idx["word_num"]]),
            "left": float(c[idx["left"]]), "top": float(c[idx["top"]]),
            "width": float(c[idx["width"]]), "height": float(c[idx["height"]]),
            "conf": float(c[idx["conf"]]), "text": c[idx["text"]],
        }
    except (ValueError, IndexError):
        return None


_TSV_COLUMNS = ("level", "page_num", "block_num", "par_num", "line_num",
                "word_num", "left", "top", "width", "height", "conf", "text")


def parse_tsv_enriched(tsv_text: str) -> dict:
    """Parse tesseract TSV keeping ALL levels (page/block/par/line/word).

    Returns {"page_dims", "blocks", "pars", "lines", "words"} — see spec.
    Pure; knows nothing about subprocesses or lines.json.
    """
    out = _empty_enriched()
    rows = tsv_text.splitlines()
    if not rows:
        return out
    header = rows[0].split("\t")
    idx = {h: i for i, h in enumerate(header)}
    if not all(k in idx for k in _TSV_COLUMNS):
        return out
    for r in rows[1:]:
        c = r.split("\t")
        if len(c) < len(header):
            continue
        t = _typed_row(c, idx)
        if t is None:
            continue
        box = {"page": t["page"], "x0": t["left"], "y0": t["top"],
               "x1": t["left"] + t["width"], "y1": t["top"] + t["height"]}
        if t["level"] == 1:
            out["page_dims"][t["page"]] = (t["width"], t["height"])
        elif t["level"] == 2:
            out["blocks"].append({**box, "block_num": t["block_num"]})
        elif t["level"] == 3:
            out["pars"].append({**box, "block_num": t["block_num"],
                                "par_num": t["par_num"]})
        elif t["level"] == 4:
            out["lines"].append({**box, "block_num": t["block_num"],
                                 "par_num": t["par_num"],
                                 "line_num": t["line_num"]})
        elif t["level"] == 5 and t["text"].strip():
            out["words"].append({**box, "block_num": t["block_num"],
                                 "par_num": t["par_num"],
                                 "line_num": t["line_num"],
                                 "word_num": t["word_num"],
                                 "conf": t["conf"], "text": t["text"]})
    return out


DEFAULT_MIN_WORD_CONF = 5.0   # below this, tesseract output is noise (punch
                              # holes, bleed-through) — measured on real scans

_QUOTE_MAP = str.maketrans({"„": '"', "“": '"', "”": '"',
                            "‚": "'", "‘": "'", "’": "'"})
# token STARTING with , directly before a letter = misread German „ opening
# quote (a real comma attaches to the previous token, never starts one)
_COMMA_QUOTE = re.compile(r'^,{1,2}(?=[A-Za-zÄÖÜäöüß])')
# OCR reads ß as B; German ß only ever follows a vowel, which spares
# CamelCase brands like KölnBonn
_ESZETT = re.compile(r'(?<=[aeiouäöü])B(?=[a-zäöüß])')
# printed bullets (•) OCR as these isolated glyphs at mid-low confidence;
# a crisply printed real ©/®/° scores high conf and is left alone
_BULLET_MISREADS = {"°", "©", "®", "·"}
_BULLET_MAX_CONF = 60.0


def _normalize_word_text(text: str, lang: str) -> str:
    """Repair common OCR misreads: typographic quotes -> ASCII, token-start
    comma -> opening quote, and (German only) B-for-ß between vowel and
    lowercase letter."""
    t = text.translate(_QUOTE_MAP)
    t = _COMMA_QUOTE.sub('"', t)
    if "deu" in lang:
        t = _ESZETT.sub("ß", t)
    return t


def clean_words(parsed: dict, *, lang: str = "",
                min_conf: float = DEFAULT_MIN_WORD_CONF) -> dict:
    """Filter noise words (conf < min_conf) and normalize the survivors' text.

    Mutates and returns `parsed` (a parse_tsv_enriched result). Adds
    "dropped_words" (count). A changed word keeps its original OCR text in
    "raw_text" — full TSV fidelity is preserved.
    """
    kept = []
    for w in parsed["words"]:
        if w["conf"] < min_conf:
            continue
        fixed = _normalize_word_text(w["text"], lang)
        if fixed in _BULLET_MISREADS and w["conf"] < _BULLET_MAX_CONF:
            fixed = "•"
        if fixed != w["text"]:
            w["raw_text"] = w["text"]
            w["text"] = fixed
        kept.append(w)
    parsed["dropped_words"] = len(parsed["words"]) - len(kept)
    parsed["words"] = kept
    return parsed


def _group_lines(words: list[dict]) -> list[dict]:
    """Group words into text lines by (page, block, line), emitted in READING
    order — sorted by that key, NOT by geometric y.

    The producers assign the key in reading order (tesseract TSV: block/par/line;
    pdfdrill's chars_to_lines: a per-page COLUMN-AWARE line index). A y-sort
    re-interleaves the two columns of a two-column paper ("left words RIGHT
    WORDS"), which is exactly the bug pdfdrill's geometry.group_lines was fixed
    for — this inlined copy must match it or the pdfminer/born-digital route
    regresses.
    """
    g: dict[tuple, list[dict]] = defaultdict(list)
    for w in words:
        g[(w["page"], w["block"], w["line"])].append(w)
    lines: list[dict] = []
    for (page, _b, _l), ws in sorted(g.items()):
        ws.sort(key=lambda w: w["x0"])
        lines.append({
            "page": page,
            "x0": min(w["x0"] for w in ws),
            "x1": max(w["x1"] for w in ws),
            "y0": min(w["y0"] for w in ws),
            "y1": max(w["y1"] for w in ws),
            "text": " ".join(w["text"] for w in ws),
        })
    return lines


def lines_json_from_words(
    words: list[dict[str, Any]],
    page_dims: dict[int, tuple[float, float]],
    *,
    source: str = "tesseract",
) -> dict[str, Any]:
    """Legacy assembler: words + page dims -> MathPix-shaped lines.json.

    Output is byte-identical to pdfdrill's current module (compat oracle in
    tests). Used by pdfdrill's pdfplumber-chars route; the enriched TSV path
    uses lines_json_from_tsv instead.
    """
    lines = _group_lines(words)
    by_page: dict[int, list[dict]] = {}
    for ln in lines:
        pg = ln["page"]
        x0, y0, x1, y1 = ln["x0"], ln["y0"], ln["x1"], ln["y1"]
        by_page.setdefault(pg, []).append({
            "id": f"ocr_p{pg}_l{len(by_page.get(pg, []))}",
            "type": "text",
            "text": ln["text"],
            "text_display": ln["text"],
            "region": {
                "top_left_x": round(x0, 2),
                "top_left_y": round(y0, 2),
                "width": round(x1 - x0, 2),
                "height": round(y1 - y0, 2),
            },
        })

    try:  # optional pdfdrill-side margin tagging; absent standalone
        from semantic.geometry_columns import tag_out_of_column
        for pg_lines in by_page.values():
            tag_out_of_column(pg_lines)
    except Exception:
        pass

    all_pages = sorted(set(page_dims) | set(by_page))
    pages = []
    for pg in all_pages:
        w, h = page_dims.get(pg, (0.0, 0.0))
        pages.append({
            "page": pg,
            "image_id": None,
            "page_width": round(w, 2),
            "page_height": round(h, 2),
            "lines": by_page.get(pg, []),
        })
    return {"source": source, "pages": pages}


def _union_bbox(items: list[dict]) -> dict:
    """Union bbox of dicts carrying x0/y0/x1/y1 (defensive fallback)."""
    return {"x0": min(i["x0"] for i in items),
            "y0": min(i["y0"] for i in items),
            "x1": max(i["x1"] for i in items),
            "y1": max(i["y1"] for i in items)}


def _line_dict(pg: int, n: int, key: tuple, row: dict, ws: list[dict]) -> dict:
    """Build one enriched output line from its level-4 row + sorted words."""
    text = " ".join(w["text"] for w in ws)
    return {
        "id": f"ocr_p{pg}_l{n}", "type": "text",
        "text": text, "text_display": text,
        "region": {"top_left_x": round(row["x0"], 2),
                   "top_left_y": round(row["y0"], 2),
                   "width": round(row["x1"] - row["x0"], 2),
                   "height": round(row["y1"] - row["y0"], 2)},
        "conf": round(sum(w["conf"] for w in ws) / len(ws), 1),
        "block_num": key[1], "par_num": key[2], "line_num": key[3],
        "words": [{"text": w["text"], "x0": w["x0"], "y0": w["y0"],
                   "x1": w["x1"], "y1": w["y1"], "conf": w["conf"],
                   "word_num": w["word_num"],
                   **({"raw_text": w["raw_text"]} if "raw_text" in w else {})}
                  for w in ws],
    }


def _blocks_tree(parsed: dict, pg: int, line_ids: dict) -> list[dict]:
    """Page's blocks>paragraphs tree from levels 2/3; line_ids maps
    (block_num, par_num) -> [emitted line ids]."""
    pars_by_block: dict[int, list[dict]] = defaultdict(list)
    for p in parsed["pars"]:
        if p["page"] == pg:
            pars_by_block[p["block_num"]].append(p)
    tree = []
    for b in (x for x in parsed["blocks"] if x["page"] == pg):
        paragraphs = [{
            "par_num": p["par_num"],
            "bbox": {"x0": p["x0"], "y0": p["y0"], "x1": p["x1"], "y1": p["y1"]},
            "line_ids": line_ids.get((b["block_num"], p["par_num"]), []),
        } for p in sorted(pars_by_block.get(b["block_num"], []),
                          key=lambda p: p["par_num"])]
        tree.append({"block_num": b["block_num"],
                     "bbox": {"x0": b["x0"], "y0": b["y0"],
                              "x1": b["x1"], "y1": b["y1"]},
                     "paragraphs": paragraphs})
    return tree


def lines_json_from_tsv(parsed_pages: list[dict], *, source: str = "tesseract",
                        ocr_meta: dict | None = None,
                        image_id_fmt: str | None = None) -> dict:
    """Enriched assembler: parse_tsv_enriched results -> lines.json dict.

    Legacy fields identical in shape to lines_json_from_words; enrichment is
    additive (conf/block_num/par_num/line_num/words per line, blocks per page,
    top-level "ocr"). Emission order is tesseract's (block, par, line).
    Pure — knows nothing about tesseract or the filesystem.
    """
    page_dims: dict[int, tuple[float, float]] = {}
    by_page: dict[int, list[dict]] = {}
    blocks_by_page: dict[int, list[dict]] = {}
    for parsed in parsed_pages:
        page_dims.update(parsed["page_dims"])
        wgroups: dict[tuple, list[dict]] = defaultdict(list)
        for w in parsed["words"]:
            wgroups[(w["page"], w["block_num"], w["par_num"],
                     w["line_num"])].append(w)
        line_rows = {(l["page"], l["block_num"], l["par_num"], l["line_num"]): l
                     for l in parsed["lines"]}
        line_ids: dict[tuple, list[str]] = defaultdict(list)
        for key in sorted(set(line_rows) | set(wgroups)):
            ws = sorted(wgroups.get(key, []), key=lambda w: w["word_num"])
            if not ws:
                continue                      # level-4 row with no words
            pg = key[0]
            row = line_rows.get(key) or _union_bbox(ws)
            ln = _line_dict(pg, len(by_page.setdefault(pg, [])), key, row, ws)
            by_page[pg].append(ln)
            line_ids[(key[1], key[2])].append(ln["id"])
        for pg in set(p["page"] for p in parsed["blocks"]) | set(by_page):
            blocks_by_page.setdefault(pg, []).extend(
                _blocks_tree(parsed, pg, line_ids))

    try:  # optional pdfdrill-side margin tagging; absent standalone
        from semantic.geometry_columns import tag_out_of_column
        for pg_lines in by_page.values():
            tag_out_of_column(pg_lines)
    except Exception:
        pass

    pages = []
    for pg in sorted(set(page_dims) | set(by_page)):
        w, h = page_dims.get(pg, (0.0, 0.0))
        pages.append({"page": pg,
                      "image_id": (image_id_fmt.format(page=pg)
                                   if image_id_fmt else None),
                      "page_width": round(w, 2), "page_height": round(h, 2),
                      "lines": by_page.get(pg, []),
                      "blocks": blocks_by_page.get(pg, [])})
    out = {"source": source, "pages": pages}
    if ocr_meta is not None:
        out["ocr"] = ocr_meta
    return out


# --- structural typing (font-free, MathPix-compatible vocabulary) ---------
HEADER_HEIGHT_RATIO = 1.35   # section_header: line height vs page body height
HEADER_MAX_WORDS = 8
HEADER_MIN_CONF = 60.0
PAGE_BAND_FRACTION = 0.06    # page_info: within top/bottom 6% of the page
PAGE_INFO_MAX_WORDS = 6
PAGE_INFO_DIGIT_RATIO = 0.5
PAGE_INFO_MAX_HEIGHT_RATIO = 1.2   # page furniture is body-sized or smaller
REPEAT_MIN_PAGES = 3         # footer/header text repeating on >= 3 pages
DIAG_CAND_MAX_CONF = 70.0    # diagram candidates: low-conf short fragments
DIAG_CAND_MAX_WORDS = 4
DIAG_MIN_LINES = 6           # a cluster this big is a diagram region
DIAG_MAX_MEAN_CONF = 65.0
VOID_MIN_PAGE_FRACTION = 0.2   # interior text-free area this big on a ...
VOID_MAX_MEDIAN_CONF = 80.0    # ...low-conf page = a pure-graphics region
TABLE_MIN_ROWS = 3           # consecutive multi-column / dot-leader rows
TABLE_MIN_COLS = 2           # aligned column starts shared by all rows
COL_GAP_FACTOR = 1.0         # intra-row gap >= this x body_h = column break
COL_TOL_FACTOR = 1.0         # column starts align within this x body_h
ROW_GAP_FACTOR = 2.5         # rows this close (x body_h) are one table
_DOT_LEADER = re.compile(r'(\.\s*){4,}')   # TOC rows -> table (deliberate:
                             # a TOC type false-positives on invoices, and
                             # the LaTeX branch ignores tables)
EQ_MAX_ALPHA = 0.4           # equation: mostly non-letter glyphs...
EQ_CENTER_TOL = 0.08         # ...and x-centered on the page
EQ_MIN_CONF = 40.0
EQ_BLOCK_GAP_FACTOR = 1.5    # DRILLPDFse _group_display_blocks: baselines of
                             # ONE formula (fraction parts, sum limits) sit
                             # within this x line-height vertically
# trailing dotted equation number "(2.13)" / "(7.4a)": the reliable display-
# math signal on scans, where OCR letters Greek symbols away and breaks '='.
# The dot is REQUIRED so bibliography years "(1959)" never match.
_EQNUM = re.compile(r'\(\s*\d+\s*[.,:]\s*\d+(\s*[.,:]\s*\d+)*\s*[a-z]?\s*\)'
                    r'\s*[.,]?\s*$')
BODY_MIN_LINES = 4           # fewer confident lines -> page stays untyped


def _body_height(lines: list[dict]) -> float | None:
    """Median height of confident multi-word lines; None if too few to judge."""
    hs = sorted(l["region"]["height"] for l in lines
                if len(l["words"]) >= 2 and l["conf"] >= HEADER_MIN_CONF)
    if len(hs) < BODY_MIN_LINES:
        return None
    mid = len(hs) // 2
    return float(hs[mid] if len(hs) % 2 else (hs[mid - 1] + hs[mid]) / 2)


def _norm_line_text(s: str) -> str:
    return " ".join(s.lower().split())


def _repeated_texts(doc: dict, min_pages: int = REPEAT_MIN_PAGES) -> set[str]:
    """Normalized line texts that appear on >= min_pages distinct pages."""
    seen: dict[str, set[int]] = defaultdict(set)
    for p in doc["pages"]:
        for l in p["lines"]:
            t = _norm_line_text(l["text"])
            if t:
                seen[t].add(p["page"])
    return {t for t, pgs in seen.items() if len(pgs) >= min_pages}


def _cluster_boxes(boxes: list[tuple], gap: float) -> list[list[int]]:
    """Union-find proximity clustering of (x0, y0, x1, y1) boxes."""
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if (a[0] - gap <= b[2] and b[0] - gap <= a[2] and
                    a[1] - gap <= b[3] and b[1] - gap <= a[3]):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(boxes)):
        groups[find(i)].append(i)
    return list(groups.values())


def _line_box(l: dict) -> tuple:
    r = l["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


def _extract_diagrams(page: dict, body_h: float, counts: dict) -> None:
    """Consolidate low-conf fragment clusters into type=\"diagram\" lines.

    Mutates page: absorbed lines are removed (also from the blocks tree) and
    one diagram line per region is inserted at the first absorbed position.
    """
    lines = page["lines"]
    cand = [i for i, l in enumerate(lines)
            if l["conf"] < DIAG_CAND_MAX_CONF
            and len(l["words"]) <= DIAG_CAND_MAX_WORDS]
    if not cand:
        return
    clusters = _cluster_boxes([_line_box(lines[i]) for i in cand],
                              gap=2.0 * body_h)
    absorbed: set[int] = set()
    regions = []
    for cluster in clusters:
        members = [cand[k] for k in cluster]
        if len(members) < DIAG_MIN_LINES:
            continue
        confs = [lines[i]["conf"] for i in members]
        if sum(confs) / len(confs) >= DIAG_MAX_MEAN_CONF:
            continue
        boxes = [_line_box(lines[i]) for i in members]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        # absorb every line whose center lies inside the region
        for i, l in enumerate(lines):
            bx = _line_box(l)
            cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                absorbed.add(i)
        regions.append((min(members), (x0, y0, x1, y1),
                        [lines[i]["conf"] for i in absorbed]))
    if not regions:
        return
    absorbed_ids = {lines[i]["id"] for i in absorbed}
    new_lines = []
    for i, l in enumerate(lines):
        for k, (first, (x0, y0, x1, y1), confs) in enumerate(regions):
            if i == first:
                new_lines.append({
                    "id": f"ocr_p{page['page']}_d{k}", "type": "diagram",
                    "text": "", "text_display": "",
                    "region": {"top_left_x": round(x0, 2),
                               "top_left_y": round(y0, 2),
                               "width": round(x1 - x0, 2),
                               "height": round(y1 - y0, 2)},
                    "conf": round(sum(confs) / len(confs), 1)})
                counts["diagram"] += 1
        if i not in absorbed:
            new_lines.append(l)
        else:
            counts["absorbed_lines"] += 1
    page["lines"] = new_lines
    for b in page.get("blocks", []):
        for par in b["paragraphs"]:
            par["line_ids"] = [i for i in par["line_ids"]
                               if i not in absorbed_ids]


def _void_region(page: dict, counts: dict) -> None:
    """Detect a large interior text-free area on a low-confidence page.

    Pure-graphics pages (wiring schematics, layout drawings) often OCR to a
    handful of lines around a big empty middle — no fragments to cluster, so
    _extract_diagrams sees nothing. The area itself is the evidence. Only
    fires when the page's median conf is low; clean half-filled letters
    (high conf, trailing margin) never qualify because only INTERIOR gaps
    between lines count. Mutates page (appends one diagram line).
    """
    lines = [l for l in page["lines"] if l["type"] != "diagram"]
    if len(lines) < 2:
        return
    confs = sorted(l["conf"] for l in lines)
    if confs[len(confs) // 2] >= VOID_MAX_MEDIAN_CONF:
        return
    page_h = page["page_height"]
    boxes = sorted(_line_box(l) for l in lines)
    ys = sorted((b[1], b[3]) for b in boxes)
    best_gap, best_y = 0.0, 0.0
    reach = ys[0][1]
    for y0, y1 in ys[1:]:
        if y0 - reach > best_gap:
            best_gap, best_y = y0 - reach, reach
        reach = max(reach, y1)
    if best_gap <= VOID_MIN_PAGE_FRACTION * page_h:
        return
    x0 = min(b[0] for b in boxes); x1 = max(b[2] for b in boxes)
    k = sum(l["type"] == "diagram" for l in page["lines"])
    page["lines"].append({
        "id": f"ocr_p{page['page']}_d{k}", "type": "diagram",
        "text": "", "text_display": "",
        "region": {"top_left_x": round(x0, 2), "top_left_y": round(best_y, 2),
                   "width": round(x1 - x0, 2), "height": round(best_gap, 2)},
        "conf": round(confs[len(confs) // 2], 1)})
    counts["diagram"] += 1


TOC_MIN_ROWS = 3
_PAGERANGE = re.compile(r'^\d+([-–—]\d+)?$')   # "7" or "2-7"


def _scrub_blocks(page: dict, absorbed_ids: set[str]) -> None:
    for b in page.get("blocks", []):
        for par in b["paragraphs"]:
            par["line_ids"] = [i for i in par["line_ids"]
                               if i not in absorbed_ids]


def _toc_table(page: dict, body_h: float, counts: dict) -> set[str]:
    """Resolve a TOC laid out as two blocks: entries left, page ranges right.

    Tesseract emits the page-number column as SEPARATE lines, so dot-leader
    and column-alignment rules never see one row. Pair each right-column
    range line with the entry sharing its y-band, merge the range INTO the
    entry row, and wrap the rows in one type="table" container (TOC is
    deliberately a table — the LaTeX branch ignores tables). Returns row ids.
    """
    lines = page["lines"]
    pw = page["page_width"]
    nums = [i for i, l in enumerate(lines)
            if l["type"] == "text" and len(l["words"]) <= 2
            and _PAGERANGE.match(l["text"].replace(" ", ""))
            and l["region"]["top_left_x"] > 0.6 * pw
            and l["region"]["width"] < 0.15 * pw]
    if len(nums) < TOC_MIN_ROWS:
        return set()
    pairs, used = [], set()
    for i in nums:
        nb = lines[i]["region"]
        for j, l in enumerate(lines):
            if (j == i or j in used or l["type"] != "text"
                    or l["region"]["top_left_x"] > 0.4 * pw):
                continue
            r = l["region"]
            ov = (min(nb["top_left_y"] + nb["height"],
                      r["top_left_y"] + r["height"])
                  - max(nb["top_left_y"], r["top_left_y"]))
            if ov >= 0.5 * min(nb["height"], r["height"]):
                pairs.append((j, i))
                used.add(j)
                break
    if len(pairs) < TOC_MIN_ROWS:
        return set()
    absorbed_idx: set[int] = set()
    rows = []
    for e_i, n_i in sorted(pairs):
        e, n = lines[e_i], lines[n_i]
        eb, nb = _line_box(e), _line_box(n)
        x0 = min(eb[0], nb[0]); y0 = min(eb[1], nb[1])
        x1 = max(eb[2], nb[2]); y1 = max(eb[3], nb[3])
        e["region"] = {"top_left_x": round(x0, 2), "top_left_y": round(y0, 2),
                       "width": round(x1 - x0, 2), "height": round(y1 - y0, 2)}
        e["text"] = e["text"].rstrip() + " " + n["text"].strip()
        e["text_display"] = e["text"]
        e["words"] = e["words"] + n["words"]
        absorbed_idx.add(n_i)
        rows.append(e)
        counts["toc_rows"] += 1
    boxes = [_line_box(r) for r in rows]
    k = sum(l["type"] == "table" for l in lines)
    container = {
        "id": f"ocr_p{page['page']}_t{k}", "type": "table",
        "text": "", "text_display": "",
        "region": {"top_left_x": round(min(b[0] for b in boxes), 2),
                   "top_left_y": round(min(b[1] for b in boxes), 2),
                   "width": round(max(b[2] for b in boxes)
                                  - min(b[0] for b in boxes), 2),
                   "height": round(max(b[3] for b in boxes)
                                   - min(b[1] for b in boxes), 2)},
        "conf": round(sum(r["conf"] for r in rows) / len(rows), 1),
        "children_ids": [r["id"] for r in rows]}
    counts["table"] += 1
    first_row_idx = min(i for i, _ in pairs)
    absorbed_ids = {lines[i]["id"] for i in absorbed_idx}
    new_lines = []
    for i, l in enumerate(lines):
        if i == first_row_idx:
            new_lines.append(container)
        if i not in absorbed_idx:
            new_lines.append(l)
    page["lines"] = new_lines
    _scrub_blocks(page, absorbed_ids)
    return {r["id"] for r in rows}


def _col_starts(l: dict, body_h: float) -> list[float]:
    """x positions where a new column starts inside a line (gap-based)."""
    ws = l["words"]
    if not ws:
        return []
    starts = [ws[0]["x0"]]
    for prev, w in zip(ws, ws[1:]):
        if w["x0"] - prev["x1"] >= COL_GAP_FACTOR * body_h:
            starts.append(w["x0"])
    return starts


def _table_regions(page: dict, body_h: float, counts: dict,
                   skip: set[str] = frozenset()) -> set[str]:
    """Detect column-aligned / dot-leader row groups; emit table containers.

    Members stay type "text" (searchable) and are referenced from the
    container's children_ids — recursion-ready for later table tools.
    Returns the set of member line ids (skipped by further typing).
    """
    lines = page["lines"]
    rows = []                            # (index, col_starts, is_dots)
    for i, l in enumerate(lines):
        if l["type"] != "text" or l["id"] in skip:
            continue
        cols = _col_starts(l, body_h)
        dots = bool(_DOT_LEADER.search(l["text"]))
        if len(cols) >= TABLE_MIN_COLS or dots:
            rows.append((i, cols, dots))

    groups, cur = [], []
    for r in rows:
        if cur:
            prev, this = lines[cur[-1][0]], lines[r[0]]
            gap = (this["region"]["top_left_y"]
                   - prev["region"]["top_left_y"] - prev["region"]["height"])
            if gap > ROW_GAP_FACTOR * body_h:
                groups.append(cur)
                cur = []
        cur.append(r)
    if cur:
        groups.append(cur)

    members: set[str] = set()
    tol = COL_TOL_FACTOR * body_h
    k = sum(l["type"] == "table" for l in lines)
    inserts = []
    for g in groups:
        if len(g) < TABLE_MIN_ROWS:
            continue
        dots_rows = sum(1 for _, _, d in g if d)
        # MAJORITY column alignment: a column counts when >= 70% of rows
        # share it — real tables contain wrapped-cell continuation rows
        # that break strict all-rows alignment (allocr p94)
        rows_cols = [cols for _, cols, _ in g if cols]
        need = max(2, int(0.7 * len(rows_cols)))
        aligned, last = 0, None
        for c in sorted({c for cols in rows_cols for c in cols}):
            if last is not None and c - last <= tol:
                continue
            if sum(any(abs(c - c2) <= tol for c2 in cols)
                   for cols in rows_cols) >= need:
                aligned += 1
                last = c
        if aligned < TABLE_MIN_COLS and dots_rows < 2:
            continue
        idx = [i for i, _, _ in g]
        # absorb non-candidate text fragments lying inside the table span
        # (wrapped cell tails) into the children
        span_y0 = min(_line_box(lines[i])[1] for i in idx)
        span_y1 = max(_line_box(lines[i])[3] for i in idx)
        for j, l in enumerate(lines):
            if (j not in idx and l["type"] == "text" and l["id"] not in skip
                    and l["id"] not in members):
                b = _line_box(l)
                cy = (b[1] + b[3]) / 2
                if span_y0 <= cy <= span_y1:
                    idx.append(j)
        idx.sort()
        boxes = [_line_box(lines[i]) for i in idx]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        confs = [lines[i]["conf"] for i in idx]
        inserts.append((idx[0], {
            "id": f"ocr_p{page['page']}_t{k}", "type": "table",
            "text": "", "text_display": "",
            "region": {"top_left_x": round(x0, 2), "top_left_y": round(y0, 2),
                       "width": round(x1 - x0, 2), "height": round(y1 - y0, 2)},
            "conf": round(sum(confs) / len(confs), 1),
            "children_ids": [lines[i]["id"] for i in idx]}))
        members.update(lines[i]["id"] for i in idx)
        counts["table"] += 1
        k += 1
    for at, tline in reversed(inserts):
        lines.insert(at, tline)
    return members


def _is_equation(l: dict, page_w: float) -> bool:
    """Centered, symbol/digit-dominated line = display-math candidate.

    Type + rectangle only: LaTeX reconstruction happens in a later stage
    (other project); the region is what the crop route displays.
    """
    text = l["text"]
    glyphs = text.replace(" ", "")
    if len(glyphs) < 3 or l["conf"] < EQ_MIN_CONF:
        return False
    if _EQNUM.search(text):
        return True
    alpha = sum(c.isalpha() for c in glyphs) / len(glyphs)
    if alpha >= EQ_MAX_ALPHA:
        return False
    # a STRONG operator is required: dashes/slashes/dots alone also occur in
    # account numbers, fax numbers, and dates (measured on the ocrtest corpus)
    if not (any(c in "=∑∫√×±≤≥≈≠^" for c in glyphs)
            and any(c.isdigit() for c in glyphs)):
        return False
    r = l["region"]
    center = r["top_left_x"] + r["width"] / 2
    return abs(center - page_w / 2) <= EQ_CENTER_TOL * page_w


def _type_line(l: dict, body_h: float, page_h: float, page_w: float,
               repeated: set[str], counts: dict) -> None:
    """Apply section_header / page_info / equation rules to one line."""
    r = l["region"]
    band = PAGE_BAND_FRACTION * page_h
    in_band = (r["top_left_y"] + r["height"] <= band or
               r["top_left_y"] >= page_h - band)
    text = l["text"]
    if in_band and r["height"] <= PAGE_INFO_MAX_HEIGHT_RATIO * body_h:
        digits = sum(c.isdigit() for c in text)
        ratio = digits / max(1, len(text.replace(" ", "")))
        if (len(l["words"]) <= PAGE_INFO_MAX_WORDS
                or ratio >= PAGE_INFO_DIGIT_RATIO
                or _norm_line_text(text) in repeated):
            l["type"] = "page_info"
            counts["page_info"] += 1
            return
    if (r["height"] >= HEADER_HEIGHT_RATIO * body_h
            and len(l["words"]) <= HEADER_MAX_WORDS
            and l["conf"] >= HEADER_MIN_CONF
            and any(c.isalpha() for c in text)):
        l["type"] = "section_header"
        counts["section_header"] += 1
        return
    if _is_equation(l, page_w):
        l["type"] = "equation"
        counts["equation"] += 1


def _merge_equation_blocks(page: dict, counts: dict) -> None:
    """Re-join equation lines that form ONE displayed formula.

    Port of DRILLPDFse mathdet._group_display_blocks: a real display formula
    spans several baselines (fraction numerator/denominator, summation
    limits like "k=1") that OCR emits as separate lines. Vertically adjacent
    (gap <= EQ_BLOCK_GAP_FACTOR x height) and horizontally proximate
    equation lines merge into the topmost member: union region, joined text,
    concatenated words, children_ids = all member ids (stable-id provenance).
    """
    lines = page["lines"]
    eqs = sorted((i for i, l in enumerate(lines) if l["type"] == "equation"),
                 key=lambda i: lines[i]["region"]["top_left_y"])
    groups: list[list[int]] = []
    for i in eqs:
        b = _line_box(lines[i])
        if groups:
            gb = groups[-1]
            y1 = max(_line_box(lines[j])[3] for j in gb)
            hmax = max(lines[j]["region"]["height"] for j in gb + [i])
            x0g = min(_line_box(lines[j])[0] for j in gb)
            x1g = max(_line_box(lines[j])[2] for j in gb)
            vgap = b[1] - y1
            hgap = max(b[0], x0g) - min(b[2], x1g)
            if (0 <= vgap <= EQ_BLOCK_GAP_FACTOR * hmax
                    and hgap <= EQ_BLOCK_GAP_FACTOR * hmax):
                gb.append(i)
                continue
        groups.append([i])

    absorbed: set[int] = set()
    for g in groups:
        if len(g) < 2:
            continue
        members = [lines[i] for i in g]
        primary = members[0]
        boxes = [_line_box(l) for l in members]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        primary["region"] = {"top_left_x": round(x0, 2),
                             "top_left_y": round(y0, 2),
                             "width": round(x1 - x0, 2),
                             "height": round(y1 - y0, 2)}
        primary["text"] = " ".join(l["text"] for l in members)
        primary["text_display"] = primary["text"]
        primary["words"] = [w for l in members for w in l["words"]]
        primary["conf"] = round(sum(l["conf"] for l in members) / len(members), 1)
        primary["children_ids"] = [l["id"] for l in members]
        absorbed.update(g[1:])
        counts["equation"] -= len(g) - 1
        counts["equation_lines_merged"] += len(g) - 1
    if not absorbed:
        return
    absorbed_ids = {lines[i]["id"] for i in absorbed}
    page["lines"] = [l for i, l in enumerate(lines) if i not in absorbed]
    for b in page.get("blocks", []):
        for par in b["paragraphs"]:
            par["line_ids"] = [i for i in par["line_ids"]
                               if i not in absorbed_ids]


def classify_lines(doc: dict) -> dict:
    """Structural typing post-processor (MathPix-compatible vocabulary).

    section_header / page_info / diagram via font-free page-relative rules;
    everything else stays \"text\". Never fatal: a failing page stays
    untyped and is noted in ocr.warnings. Mutates and returns doc.
    """
    counts = {"section_header": 0, "page_info": 0, "diagram": 0,
              "absorbed_lines": 0, "table": 0, "equation": 0,
              "equation_lines_merged": 0, "toc_rows": 0}
    repeated = _repeated_texts(doc)
    for page in doc["pages"]:
        try:
            body_h = _body_height(page["lines"])
            if body_h is None:
                continue
            _extract_diagrams(page, body_h, counts)
            _void_region(page, counts)
            toc_rows = _toc_table(page, body_h, counts)
            table_members = toc_rows | _table_regions(page, body_h, counts,
                                                      skip=toc_rows)
            for l in page["lines"]:
                if l["type"] == "text" and l["id"] not in table_members:
                    _type_line(l, body_h, page["page_height"],
                               page["page_width"], repeated, counts)
            _merge_equation_blocks(page, counts)
        except Exception as e:
            doc.setdefault("ocr", {}).setdefault("warnings", []).append(
                f"typing failed on page {page.get('page')}: {e}")
    meta = doc.setdefault("ocr", {})
    meta["typing"] = True
    meta["type_counts"] = counts
    return doc


def _page_num_from_png(png: Path) -> int:
    """Real page number from a page-%04d.png name (0 if no digits)."""
    digits = "".join(c for c in png.stem if c.isdigit())
    return int(digits) if digits else 0


def _rasterize(pdf: Path, out_dir: Path, ppi: int) -> list[Path]:
    """Render all pages to page-%04d.png via Ghostscript at max(ppi, 400) DPI
    (pdfdrill's RASTER_MIN_DPI floor). The only rasterizer; raises without gs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    gs = next((t for t in ("gs", "gswin64c", "gswin32c") if shutil.which(t)),
              None)
    if gs is None:
        raise RuntimeError("ghostscript not found on PATH")
    subprocess.run(
        [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m",
         f"-r{max(int(ppi), RASTER_MIN_DPI)}",
         f"-sOutputFile={out_dir}/page-%04d.png", str(pdf)],
        check=True, capture_output=True, timeout=RASTER_TIMEOUT)
    return sorted(out_dir.glob("page-*.png"))


OSD_MIN_CONF = 2.0           # tesseract --psm 0 orientation confidence floor


def _osd_rotation(png: Path) -> int:
    """Orientation via tesseract OSD: degrees to rotate (0/90/180/270).

    0 on low confidence or any failure — an upright page is the safe
    default. Fast: --psm 0 runs detection only, no recognition."""
    try:
        res = subprocess.run(
            ["tesseract", str(png), "-", "--psm", "0"],
            capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            return 0
        rot = conf = None
        for line in res.stdout.splitlines():
            if line.startswith("Rotate:"):
                rot = int(line.split(":")[1])
            elif line.startswith("Orientation confidence:"):
                conf = float(line.split(":")[1])
        if rot and conf is not None and conf >= OSD_MIN_CONF:
            return rot % 360
    except Exception:
        pass
    return 0


def _png_size(png: Path) -> tuple[int, int]:
    """(width, height) in px from the PNG IHDR header."""
    data = png.read_bytes()[16:24]
    return (int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big"))


def _upright_install(rot: int, w_pt: float, h_pt: float) -> str | None:
    """PS Install body mapping original page space to the upright frame.

    rot is tesseract OSD's "Rotate:" value (clockwise degrees needed).
    For 90/270 the upright frame has swapped dimensions."""
    if rot == 180:
        return f"{w_pt} {h_pt} translate 180 rotate"
    if rot == 90:
        return f"0 {w_pt} translate -90 rotate"
    if rot == 270:
        return f"{h_pt} 0 translate 90 rotate"
    return None


def _render_page_upright(pdf: Path, page: int, dpi: int, png: Path,
                         rot: int) -> None:
    """Re-render one rotated page upright, overwriting its PNG.

    Rotation happens at render time (gs Install), so the OCR, all TSV
    coordinates, and later region crops live in the TRUE page frame.
    For 90/270 the raster dimensions swap."""
    w_px, h_px = _png_size(png)
    w_pt, h_pt = w_px * 72.0 / dpi, h_px * 72.0 / dpi
    install = _upright_install(rot, w_pt, h_pt)
    if install is None:
        return
    gw, gh = (w_px, h_px) if rot == 180 else (h_px, w_px)
    gs = next((t for t in ("gs", "gswin64c", "gswin32c") if shutil.which(t)),
              None)
    if gs is None:
        raise RuntimeError("ghostscript not found on PATH")
    subprocess.run(
        [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m",
         f"-r{dpi}", f"-g{gw}x{gh}", "-dFIXEDMEDIA",
         f"-dFirstPage={page}", f"-dLastPage={page}",
         f"-sOutputFile={png}",
         "-c", f"<</Install {{{install}}}>> setpagedevice",
         "-f", str(pdf)],
        check=True, capture_output=True, timeout=120)


def _ocr_page(png: Path, lang: str) -> str:
    """OCR one page image to raw TSV text (tesseract --psm 1, stdout)."""
    res = subprocess.run(
        ["tesseract", str(png), "-", "-l", lang, "--psm", str(PSM), "tsv"],
        capture_output=True, text=True, timeout=OCR_TIMEOUT)
    if res.returncode != 0:
        tail = (res.stderr or "").strip()[-200:]
        raise RuntimeError(f"tesseract failed on {png.name}: {tail}")
    return res.stdout


def _tesseract_version() -> str:
    """First line of `tesseract --version`; '' if unavailable (never raises)."""
    try:
        res = subprocess.run(["tesseract", "--version"],
                             capture_output=True, text=True, timeout=30)
        return (res.stdout or res.stderr).splitlines()[0].strip()
    except Exception:
        return ""


def _scale_parsed(parsed: dict, factor: float) -> dict:
    """Convert one parsed page from raster px to PDF points (x factor).

    The ONE place raster pixels become points (72/dpi); everything downstream
    — regions, word boxes, blocks tree — is then uniformly in points, which
    is what docmodel.mathpix.local_crop_url expects (units=pt).
    """
    parsed["page_dims"] = {pg: (round(w * factor, 2), round(h * factor, 2))
                           for pg, (w, h) in parsed["page_dims"].items()}
    for kind in ("blocks", "pars", "lines", "words"):
        for r in parsed[kind]:
            for k in ("x0", "y0", "x1", "y1"):
                r[k] = round(r[k] * factor, 2)
    return parsed


def _available_langs() -> set[str]:
    """Installed tesseract language packs ('' set if the probe fails)."""
    try:
        res = subprocess.run(["tesseract", "--list-langs"],
                             capture_output=True, text=True, timeout=30)
        return {l.strip() for l in res.stdout.splitlines()[1:] if l.strip()}
    except Exception:
        return set()


# stopword sets for the language-order plausibility check: tesseract's FIRST
# pack dominates its dictionary, so eng+deu on a German scan yields
# high-confidence misreads like "Griiner" (Grüner) that conf cannot catch —
# but stopword statistics can.
_STOPWORDS = {
    "deu": {"und", "der", "die", "das", "nicht", "mit", "von", "für", "ist",
            "im", "den", "dem", "ein", "eine", "auf", "sich", "werden",
            "nach", "sowie", "über", "bei", "auch", "oder", "dass", "sie",
            "bitte", "durch", "wird", "einer", "eines", "zur", "zum"},
    "eng": {"the", "and", "of", "to", "in", "is", "for", "with", "that",
            "on", "as", "are", "this", "by", "be", "from"},
}


def _detect_dominant(text: str) -> str | None:
    """Dominant document language by stopword statistics, or None."""
    words = [w.strip(".,;:()[]").lower() for w in text.split()]
    counts = {k: sum(w in sw for w in words) for k, sw in _STOPWORDS.items()}
    dominant = max(counts, key=lambda k: counts[k])
    other = min(counts, key=lambda k: counts[k])
    if counts[dominant] < 10 or counts[dominant] < 2 * max(1, counts[other]):
        return None                       # undecidable — stay quiet
    return dominant


def _lang_order_warning(text: str, lang: str) -> str | None:
    """Warn when the document's dominant language is not the FIRST pack."""
    dominant = _detect_dominant(text)
    first = lang.split("+")[0].strip().lower()
    if dominant is None or first not in _STOPWORDS or first == dominant:
        return None
    ordered = [dominant] + [p for p in lang.split("+") if p != dominant]
    return (f"document appears to be '{dominant}' but lang='{lang}' puts "
            f"'{first}' first — tesseract's first pack dominates; rerun "
            f"with lang='{'+'.join(ordered)}'")


def _has_text_layer(pdf: Path, probe_pages: int = 3,
                    min_chars: int = 10) -> bool:
    """True if the PDF carries an embedded text layer (OCR overlay/underlay
    or born-digital text). Probed with gs's txtwrite device — no new
    dependency. Invisible (render-mode-3) overlay text never reaches the
    raster, so it cannot disturb tesseract; but it is often BETTER than a
    re-OCR (correct umlauts), so callers deserve to know it exists."""
    gs = next((t for t in ("gs", "gswin64c", "gswin32c") if shutil.which(t)),
              None)
    if gs is None:
        return False
    try:
        res = subprocess.run(
            [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
             "-sDEVICE=txtwrite", f"-dLastPage={probe_pages}",
             "-sOutputFile=-", str(pdf)],
            capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            return False
        return len("".join(res.stdout.split())) >= min_chars
    except Exception:
        return False


def _patch_page(parsed: dict, page_num: int) -> dict:
    """Rewrite a single-image parse (tesseract says page 1) to the real page."""
    dims = list(parsed["page_dims"].values())
    parsed["page_dims"] = {page_num: dims[0] if dims else (0.0, 0.0)}
    for kind in ("blocks", "pars", "lines", "words"):
        for r in parsed[kind]:
            r["page"] = page_num
    return parsed


def _render_and_ocr(
    pdf: Path, out_dir: Path, ppi: int, lang: str,
) -> tuple[list[dict], dict[int, tuple[float, float]]]:
    """LEGACY contract: (words, page_dims), pages patched to real numbers.
    Kept for pdfdrill's continuity.py; build_lines_json uses the enriched path."""
    all_words: list[dict] = []
    page_dims: dict[int, tuple[float, float]] = {}
    for png in _rasterize(Path(pdf), Path(out_dir), ppi):
        page_num = _page_num_from_png(png)
        words, dims = parse_tsv(_ocr_page(png, lang))
        for w in words:
            w["page"] = page_num
        all_words.extend(words)
        if 1 in dims:
            page_dims[page_num] = dims[1]
    return all_words, page_dims


def build_lines_json(
    pdf: Path, out_dir: Path, *, ppi: int = 300, lang: str = "eng",
    min_conf: float = DEFAULT_MIN_WORD_CONF, typing: bool = True,
    with_math_pass: bool = True, with_layer_merge: bool = True,
    with_barcodes: bool = True,
) -> dict[str, Any]:
    """Render + OCR `pdf`; return the ENRICHED lines.json dict.

    RuntimeError iff tools are missing or rasterization yields no pages.
    A failing page never aborts the document: it appears with lines: [] and
    a note in ocr.warnings (DRILLPDFse never-fatal convention). Noise words
    (conf < min_conf) are dropped and German/quote misreads repaired via
    clean_words; originals survive in each word's raw_text.
    """
    ok, msg = tools_available()
    if not ok:
        raise RuntimeError(msg)
    pngs = _rasterize(Path(pdf), Path(out_dir), ppi)
    if not pngs:
        raise RuntimeError(f"rasterization produced no pages for {pdf}")
    text_layer = _has_text_layer(Path(pdf))
    available = _available_langs()
    # equ is EXPLICIT-only: in the main pass it injects math glyphs into
    # plain text (measured: 9 junk chars/page on business letters) and
    # doubles OCR time; math recovery lives in the ell second pass instead
    lang_effective = lang
    warnings: list[str] = []
    if text_layer:
        warnings.append(
            "document carries an embedded text layer (OCR overlay or "
            "born-digital) — it is invisible to this re-OCR but may be "
            "higher quality; consider the born-digital route (pdfminer/"
            "pdfdrill model) or cross-checking against it")

    def _ocr_parse(png, l):
        try:
            return parse_tsv_enriched(_ocr_page(png, l)), None
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            return _empty_enriched(), str(e)

    # orientation first: flipped pages are re-rendered upright BEFORE any
    # OCR so text, coordinates, and crops all live in the true page frame
    rotations: dict[int, int] = {}

    def _maybe_upright(png: Path, page_num: int) -> None:
        rot = _osd_rotation(png)
        if not rot:
            return
        rotations[page_num] = rot
        _render_page_upright(Path(pdf), page_num, dpi, png, rot)
        warnings.append(f"page {page_num} was rotated ({rot}°) — "
                        f"auto-corrected before OCR")

    dpi = max(int(ppi), RASTER_MIN_DPI)
    _maybe_upright(pngs[0], _page_num_from_png(pngs[0]))

    # probe page 1: if the document's dominant language is not the first
    # pack, fix the order (or add the pack) and redo page 1 — tesseract's
    # first pack dominates its dictionary (Griiner-for-Grüner class errors).
    first_parsed, first_err = _ocr_parse(pngs[0], lang_effective)
    dominant = _detect_dominant(
        " ".join(w["text"] for w in first_parsed["words"]))
    packs = [p for p in lang.split("+") if p != "equ"]
    if dominant and packs and packs[0] != dominant:
        if dominant in available:
            keep = [p for p in lang.split("+") if p != dominant]
            corrected = "+".join([dominant] + keep)
            warnings.append(f"auto-corrected language order to "
                            f"'{corrected}' (document appears '{dominant}', "
                            f"requested lang='{lang}')")
            lang_effective = corrected
            first_parsed, first_err = _ocr_parse(pngs[0], lang_effective)
        else:
            warnings.append(f"document appears to be '{dominant}' but the "
                            f"'{dominant}' tesseract pack is not installed — "
                            f"OCR quality will suffer (lang='{lang}')")

    parsed_pages: list[dict] = []
    dropped = 0
    for i, png in enumerate(pngs):
        page_num = _page_num_from_png(png)
        if i == 0:
            parsed, err = first_parsed, first_err
        else:
            _maybe_upright(png, page_num)
            parsed, err = _ocr_parse(png, lang_effective)
        if err:
            warnings.append(f"page {page_num}: {err}")
        parsed = clean_words(parsed, lang=lang_effective, min_conf=min_conf)
        dropped += parsed["dropped_words"]
        parsed = _scale_parsed(parsed, 72.0 / dpi)
        parsed_pages.append(_patch_page(parsed, page_num))
    meta = {"ppi": ppi, "lang": lang, "lang_effective": lang_effective,
            "psm": PSM, "tesseract_version": _tesseract_version(),
            "min_conf": min_conf, "dropped_words": dropped,
            "units": "pt", "render_dpi": max(int(ppi), RASTER_MIN_DPI),
            "text_layer": text_layer,
            "warnings": warnings}
    doc = lines_json_from_tsv(parsed_pages, ocr_meta=meta,
                              image_id_fmt="tesseract-p{page}")
    for p in doc["pages"]:
        if p["page"] in rotations:
            p["osd_rotation"] = rotations[p["page"]]
    if typing:
        doc = classify_lines(doc)
        if with_math_pass:
            math_pass(doc, Path(pdf), Path(out_dir) / "mathpass", dpi=dpi)
    if text_layer and with_layer_merge:
        text_layer_pass(doc, Path(pdf))
    if with_barcodes:
        barcode_pass(doc, Path(pdf), Path(out_dir), dpi=dpi, pngs=pngs)
    return doc


MATH_LANGS = "ell+eng"       # Greek FIRST recovers ψ/Ψ/Ω from equation crops
MATH_PASS_PAD_PT = 4.0


def _render_region(pdf: Path, page: int, region: dict, page_h: float,
                   dpi: int, out_png: Path, *, rot: int = 0,
                   page_w: float = 0.0) -> Path:
    """Render one region (PDF points, top-left, UPRIGHT frame) to a PNG.

    Uses gs Install-translate (PageOffset is ignored by the gs 10 PDF
    interpreter): shift the page so the region's lower-left lands at the
    origin, then clip with -g. For pages that were upside down
    (osd_rotation 180) the upright transform is composed in first, so the
    crop matches the upright-frame region coordinates."""
    pad = MATH_PASS_PAD_PT
    x0 = region["top_left_x"] - pad
    y_bot = page_h - (region["top_left_y"] + region["height"]) - pad
    w_px = int((region["width"] + 2 * pad) * dpi / 72.0)
    h_px = int((region["height"] + 2 * pad) * dpi / 72.0)
    gs = next((t for t in ("gs", "gswin64c", "gswin32c") if shutil.which(t)),
              None)
    if gs is None:
        raise RuntimeError("ghostscript not found on PATH")
    install = f"{-x0} {-y_bot} translate"
    if rot:
        # compose the upright transform; the ORIGINAL page dims are the
        # upright dims swapped back for 90/270
        ow, oh = (page_w, page_h) if rot == 180 else (page_h, page_w)
        up = _upright_install(rot, ow, oh)
        if up:
            install += " " + up
    subprocess.run(
        [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m",
         f"-r{dpi}", f"-g{max(1, w_px)}x{max(1, h_px)}", "-dFIXEDMEDIA",
         f"-dFirstPage={page}", f"-dLastPage={page}",
         f"-sOutputFile={out_png}",
         "-c", f"<</Install {{{install}}}>> setpagedevice",
         "-f", str(pdf)],
        check=True, capture_output=True, timeout=60)
    return out_png


def _ocr_text(png: Path, lang: str, psm: int) -> str:
    """Plain-text OCR of one image (used by the math second pass)."""
    res = subprocess.run(
        ["tesseract", str(png), "-", "-l", lang, "--psm", str(psm)],
        capture_output=True, text=True, timeout=OCR_TIMEOUT)
    if res.returncode != 0:
        raise RuntimeError(f"tesseract failed on {png.name}")
    return res.stdout.strip()


def math_pass(doc: dict, pdf: Path, work_dir: Path, *, dpi: int = 400) -> int:
    """Second pass over equation regions with Greek+math language packs.

    Adds `text_math` to each equation line (original `text` kept) — the
    later-stage-update pattern: additive keys, stable ids, never fatal.
    Returns the number of lines enriched.
    """
    if not any(l["type"] == "equation"
               for p in doc["pages"] for l in p["lines"]):
        return 0
    meta = doc.setdefault("ocr", {})
    warnings = meta.setdefault("warnings", [])
    langs = _available_langs()
    if not {"ell", "grc"} & langs:
        warnings.append("math pass skipped: no Greek pack (ell/grc) installed")
        return 0
    lang = MATH_LANGS if "ell" in langs else "grc+eng"
    work_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for page in doc["pages"]:
        for l in page["lines"]:
            if l["type"] != "equation":
                continue
            try:
                png = work_dir / f"eq-p{page['page']}-{l['id']}.png"
                _render_region(Path(pdf), page["page"], l["region"],
                               page["page_height"], dpi, png,
                               rot=page.get("osd_rotation", 0),
                               page_w=page["page_width"])
                psm = 6 if l.get("children_ids") else 7
                text = _ocr_text(png, lang, psm)
                if text:
                    l["text_math"] = text
                    done += 1
            except Exception as e:
                warnings.append(f"math pass p{page['page']} {l['id']}: {e}")
    meta.setdefault("type_counts", {})["math_pass_lines"] = done
    return done


def _pdftotext_tsv(pdf: Path) -> str | None:
    """Raw `pdftotext -tsv` output (same 12-column schema as tesseract, in
    PDF points) — or None when poppler is absent or extraction fails."""
    if shutil.which("pdftotext") is None:
        return None
    res = subprocess.run(["pdftotext", "-tsv", str(pdf), "-"],
                         capture_output=True, text=True, timeout=180)
    return res.stdout if res.returncode == 0 else None


def text_layer_pass(doc: dict, pdf: Path) -> int:
    """Merge the embedded text layer as a THIRD per-line channel.

    pdftotext -tsv shares tesseract's TSV schema and reports PDF points —
    our own units — so parse_tsv_enriched reads it directly and layer words
    map onto line regions with no coordinate conversion. Each line whose
    region contains layer words gains `text_layer_text` (additive; `text`
    = tesseract OCR and `text_math` stay untouched). Container lines
    (empty text) are skipped — their children carry the channel.
    """
    meta = doc.setdefault("ocr", {})
    warnings = meta.setdefault("warnings", [])
    try:
        tsv = _pdftotext_tsv(Path(pdf))
    except Exception as e:
        warnings.append(f"text-layer pass failed: {e}")
        return 0
    if tsv is None:
        warnings.append("text-layer pass skipped: pdftotext (poppler) "
                        "not on PATH")
        return 0
    parsed = parse_tsv_enriched(tsv)
    by_page: dict[int, list[dict]] = defaultdict(list)
    for w in parsed["words"]:
        by_page[w["page"]].append(w)
    done = 0
    for page in doc["pages"]:
        words = by_page.get(page["page"], [])
        if not words:
            continue
        for l in page["lines"]:
            r = l.get("region")
            if not r or not l.get("text"):
                continue
            x0, y0 = r["top_left_x"] - 2, r["top_left_y"] - 2
            x1 = r["top_left_x"] + r["width"] + 2
            y1 = r["top_left_y"] + r["height"] + 2
            hits = [w for w in words
                    if x0 <= (w["x0"] + w["x1"]) / 2 <= x1
                    and y0 <= (w["y0"] + w["y1"]) / 2 <= y1]
            if not hits:
                continue
            hits.sort(key=lambda w: (round(w["y0"]), w["x0"]))
            l["text_layer_text"] = " ".join(w["text"] for w in hits)
            done += 1
    meta.setdefault("type_counts", {})["text_layer_lines"] = done
    return done


def _zbar_scan(png: Path) -> list[dict]:
    """QR + 1D symbols on one image via zbarimg: [{symbology, data}]."""
    res = subprocess.run(["zbarimg", "-q", str(png)],
                         capture_output=True, text=True, timeout=60)
    out = []
    for line in res.stdout.splitlines():
        if ":" in line:
            sym, data = line.split(":", 1)
            out.append({"symbology": sym, "data": data})
    return out


# pylibdmtx helper (Solus ships libdmtx but no dmtx-utils CLI). Runs in a
# subprocess so this module stays import-free; emits top-left px coords
# (libdmtx's rect.top is measured from the BOTTOM — flipped here).
_DMTX_HELPER = """\
import json, sys
from PIL import Image
from pylibdmtx.pylibdmtx import decode
img = Image.open(sys.argv[1]).convert("L")
out = []
for s in decode(img, timeout=int(sys.argv[2])):
    r = s.rect
    out.append({"data": s.data.decode("utf-8", "replace"),
                "left": r.left, "top": img.height - r.top - r.height,
                "width": r.width, "height": r.height})
print(json.dumps(out))
"""


def _dmtx_available() -> bool:
    if shutil.which("dmtxread"):
        return True
    import importlib.util
    return (importlib.util.find_spec("pylibdmtx") is not None
            and importlib.util.find_spec("PIL") is not None)


def _dmtx_scan(png: Path, ms_timeout: int = 1500) -> list[dict]:
    """DataMatrix symbols (Deutsche Post franking etc.): dmtxread CLI when
    present, else pylibdmtx over the system libdmtx (with px rectangles)."""
    if shutil.which("dmtxread"):
        res = subprocess.run(["dmtxread", "-n", f"-m{ms_timeout}", str(png)],
                             capture_output=True, text=True, timeout=60)
        return [{"symbology": "DataMatrix", "data": line}
                for line in res.stdout.splitlines() if line.strip()]
    res = subprocess.run(
        [sys.executable, "-c", _DMTX_HELPER, str(png), str(ms_timeout)],
        capture_output=True, text=True, timeout=90)
    if res.returncode != 0:
        return []
    return [{"symbology": "DataMatrix", "data": s["data"],
             "rect_px": {"left": s["left"], "top": s["top"],
                         "width": s["width"], "height": s["height"]}}
            for s in json.loads(res.stdout)]


def barcode_pass(doc: dict, pdf: Path, work_dir: Path, *, dpi: int = 300,
                 pngs: list[Path] | None = None) -> int:
    """Detect + decode barcodes per page: QR/1D (zbarimg), DataMatrix
    (dmtxread). Page dicts gain `barcodes: [{symbology, data}]` — the
    region slot is deliberately left to image-side tools (zbar/dmtx CLIs
    decode but do not report coordinates). Never fatal; skips per missing
    tool. Reuses the build's page PNGs when given, else renders."""
    meta = doc.setdefault("ocr", {})
    warnings = meta.setdefault("warnings", [])
    have_zbar = shutil.which("zbarimg") is not None
    have_dmtx = _dmtx_available()
    if not (have_zbar or have_dmtx):
        warnings.append("barcode pass skipped: neither zbarimg nor "
                        "dmtxread on PATH")
        return 0
    if pngs is None:
        work_dir.mkdir(parents=True, exist_ok=True)
        pngs = _rasterize(Path(pdf), Path(work_dir), dpi)
    by_page = {_page_num_from_png(p): p for p in pngs}
    total = 0
    for page in doc["pages"]:
        png = by_page.get(page["page"])
        if png is None:
            continue
        found: list[dict] = []
        try:
            if have_zbar:
                found.extend(_zbar_scan(png))
            if have_dmtx:
                found.extend(_dmtx_scan(png))
        except Exception as e:
            warnings.append(f"barcode pass p{page['page']}: {e}")
            continue
        if found:
            for s in found:            # px rectangles -> region in PDF points
                r = s.pop("rect_px", None)
                if r:
                    f = 72.0 / dpi
                    s["region"] = {"top_left_x": round(r["left"] * f, 2),
                                   "top_left_y": round(r["top"] * f, 2),
                                   "width": round(r["width"] * f, 2),
                                   "height": round(r["height"] * f, 2)}
            page["barcodes"] = found
            total += len(found)
    if total or have_zbar or have_dmtx:
        meta.setdefault("type_counts", {})["barcodes"] = total
    return total


def main(argv: list[str] | None = None) -> int:
    """Standalone CLI: PDF -> enriched lines.json (file or stdout)."""
    ap = argparse.ArgumentParser(
        description="Tesseract OCR -> enriched MathPix-compatible lines.json")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="output path ('-' = stdout); default: "
                         "<pdf>.drill/<stem>.tesseract.lines.json")
    ap.add_argument("--ppi", type=int, default=300)
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--min-conf", type=float, default=DEFAULT_MIN_WORD_CONF,
                    help="drop words below this confidence (0 disables)")
    ap.add_argument("--no-typing", action="store_true",
                    help="skip structural typing (all lines stay type=text)")
    ap.add_argument("--no-math-pass", action="store_true",
                    help="skip the Greek/math re-OCR of equation regions")
    ap.add_argument("--no-layer-merge", action="store_true",
                    help="skip merging an embedded text layer as "
                         "text_layer_text")
    ap.add_argument("--no-barcodes", action="store_true",
                    help="skip QR/DataMatrix detection (zbarimg/dmtxread)")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="ocrlines-") as td:
        doc = build_lines_json(a.pdf, Path(td), ppi=a.ppi, lang=a.lang,
                               min_conf=a.min_conf, typing=not a.no_typing,
                               with_math_pass=not a.no_math_pass,
                               with_layer_merge=not a.no_layer_merge,
                               with_barcodes=not a.no_barcodes)
    payload = json.dumps(doc, indent=1, ensure_ascii=False)
    if a.output and str(a.output) == "-":
        print(payload)
        return 0
    out = a.output
    if out is None:                       # pdfdrill artifact convention
        drill = a.pdf.parent / (a.pdf.name + ".drill")
        drill.mkdir(parents=True, exist_ok=True)
        out = drill / (a.pdf.stem + ".tesseract.lines.json")
    out.write_text(payload, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
