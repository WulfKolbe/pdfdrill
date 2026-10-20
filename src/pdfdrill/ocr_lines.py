"""
A 12-column word TSV → enriched, MathPix-compatible `lines.json`.

This module used to be an OCR ENGINE as well as an assembler: it rendered every
page, ran tesseract, and assembled the result. The engine half is gone (see
`docs/LANES.md` — pdfdrill runs no OCR engine), and what is left is the half
that was never tesseract's: the TSV parsers, the word cleaner, the line
grouper, and the structural typing that turns grouped lines into
`section_header` / `table` / `equation` / `diagram` / `page_info`.

It keeps full word-level fidelity — per-word boxes + confidence,
block/paragraph/line hierarchy — as additive keys on the same lines.json shape
the docmodel already ingests. The TSV it reads now comes from the PDF's own
text layer (`word_boxes`), from pdfminer chars (`chars_to_lines`), or from any
other producer of the same schema; `source` says which, and nothing in here
cares. Stdlib only.

Two passes that lived here went with the engine, because the engine was their
only caller: the text-layer merge (a third per-line channel — `linescmp` now
compares two readings instead) and the barcode pass (`pdfdrill qr` already
decodes every symbology with the same zxing-cpp engine, standalone).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any


def parse_tsv(tsv_text: str) -> tuple[list[dict], dict[int, tuple[float, float]]]:
    """Parse a 12-column word TSV into (words, page_dims) — legacy shape.

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
    """Parse a 12-column TSV keeping ALL levels (page/block/par/line/word).

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


DEFAULT_MIN_WORD_CONF = 5.0   # below this, an OCR'd layer is noise (punch
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

    The producers assign the key in reading order (a word TSV: block/par/line;
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
        # Per-glyph font counts, when the caller supplied them (the born-digital
        # chars route does; a plain word TSV has no font layer and does not).
        # Added ONLY when present, so a TSV-built lines.json stays byte-identical
        # to its compat oracle.
        if any("n_chars" in w for w in ws):
            lines[-1]["n_chars"] = sum(w.get("n_chars", 0) for w in ws)
            lines[-1]["math_chars"] = sum(w.get("math_chars", 0) for w in ws)
            lines[-1]["italic_chars"] = sum(w.get("italic_chars", 0) for w in ws)
    return lines


def lines_json_from_words(
    words: list[dict[str, Any]],
    page_dims: dict[int, tuple[float, float]],
    *,
    source: str = "tsv",
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
        if "n_chars" in ln:                 # chars route only; popped downstream
            by_page[pg][-1]["n_chars"] = ln["n_chars"]
            by_page[pg][-1]["math_chars"] = ln["math_chars"]
            by_page[pg][-1]["italic_chars"] = ln["italic_chars"]

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


def lines_json_from_tsv(parsed_pages: list[dict], *, source: str = "tsv",
                        ocr_meta: dict | None = None,
                        image_id_fmt: str | None = None) -> dict:
    """Enriched assembler: parse_tsv_enriched results -> lines.json dict.

    Legacy fields identical in shape to lines_json_from_words; enrichment is
    additive (conf/block_num/par_num/line_num/words per line, blocks per page,
    top-level "ocr"). Emission order is the TSV's (block, par, line).
    Pure — knows nothing about its producer or the filesystem.
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

    A word TSV emits the page-number column as SEPARATE lines, so dot-leader
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
