#: ------------------------------------------------------------------
#: A PINNED COPY. The original is `scripts/pagecheck.py` in the owner's
#: `drillgroup` repository, which OWNS it; this copy exists only so
#: pdfdrill's own suite can measure the board's model counts from a fresh
#: clone, with no file from outside git (group rule 7).
#:
#: Pinned 2026-11-22 at drillgroup 1f6f664, "pagecheck: _ancestors takes
#: every container of an object (union), not the last that listed it".
#: `parents` became a set-valued map: a child listed by two containers used
#: to keep only one parent, so an overlap finding between an object and its
#: SECOND container was reported where there is no overlap. LATENT ON THIS
#: CORPUS, measured and not assumed -- across the three ratchet models
#: (0864, 1805.01788, 2312.11532; 273 objects) NO child is listed by more
#: than one container, so every pinned count is unchanged and this re-pin
#: moves no baseline. drillgroup's own four models agree: 0 of up to 14,716
#: objects (coordinator, 2026-11-22). The previous pin was 2026-11-21 at
#: fed0bef, "pagecheck: MathPix's page is scaled into our page's pixel
#: frame before the box, column and margin checks (they compared raw pixels
#: across 250/400 dpi frames)", and its body matched byte for byte when it
#: was replaced. Not edited:
#: a divergence is resolved by RE-PINNING, never by patching this file,
#: because a ratchet that measures something other than the board measures
#: nothing. The pin before this one was 2026-11-20 at deab8a0, whose body
#: this file matched byte for byte when it was replaced -- checked, not
#: assumed, because a pin that has drifted measures neither repository.
#:
#: It is stdlib EXCEPT for one optional accelerator -- `rapidfuzz` for the
#: Levenshtein distance, guarded by `try/except ImportError` with a
#: pure-Python fallback beside it, so a base install runs it slower and not
#: differently. `test_suite_runs_on_the_documented_install` was extended to
#: recognise that guard rather than this file being patched to drop it.
#:
#: The box-text check reads `--words`: a folder of p<N>.bbox.html, the output
#: of `pdftotext -bbox-layout -cropbox`, pinned beside each fixture. That is
#: deliberate -- it keeps three third-party PDFs out of a public repository
#: (2312.11532's alone is 20 MB, over this repo's own commit limit).
#: ------------------------------------------------------------------
#!/usr/bin/env python3
"""T-0154 page check: do a reading's boxes, texts and paragraphs agree with the page and with MathPix?

    python3 -I scripts/pagecheck.py --pdf X.pdf --lines X.lines.json [--model model.docmodel.json]
                                    [--mathpix MP.lines.json] [--pages 1,3-4] [--json out.json]

Line recall/precision counts boxes. A box with the wrong text, a paragraph that lost its last line, or a whole
column read as one paragraph still counts as matched. These checks look at what the owner saw on the inspect page
(T-0154, 2026-11-17). Each finding names the page, the unit and a text snippet.

1. **box-text.** Born-digital pages only. The PDF text-layer words (`pdftotext -bbox-layout -cropbox`) whose centre
   lies in a unit's box, in the text layer's order, against the unit's own text:
   - CER over letters (NFKC, lowercase, LaTeX commands dropped, tokens of 2+ letters, spaces and hyphens ignored);
   - FAIL above 0.25 when either side has 10+ letters. The task's 0.10 was corrected: on MathPix's own correct
     lines, inline maths costs 0.10-0.20 (the text layer spells `w_{dn}` as "w dn"), while the owner's mismatches
     measure 0.7 and more.
   Units in a lines.json: leaf lines of text types (text, section_header, title, authors, abstract, footnote,
   figure_label, page_info). Units in a docmodel: Paragraph, Section, Footnote and ListItem objects, with the box
   pdfdrill's inspect page draws (the union of the object's lines on its own page) and the object's text (Paragraph
   text, Section caption, Footnote and ListItem content). Running it on both places a mismatch in the reader or in
   the model build.
2. **overlap.** Two leaf boxes on a page overlapping by more than 50 % of the smaller one FAIL. Parents and children
   are not compared (in a docmodel: an object and any object in its `parent` chain, since 2026-11-19), nor table structure (rows, columns and cells overlap by design). The task's 10 % was corrected:
   MathPix pads every line box, so its own consecutive lines overlap by 10-30 %, while the owner's cases (a footnote
   on a paragraph) overlap by 100 %. In a docmodel the leaves are Paragraph, Section, Footnote, ListItem, Equation, Diagram, Picture
   and Table. Inline Formula and TableCell lie inside them by design.
3. **paragraphs per column against MathPix** (needs --mathpix). MathPix's units, page by page:
   - each container (section_header, footnote, title, authors, abstract, figure_label) with its lines;
   - each run of `text` lines in a column, a new one starting where `text_display` starts a paragraph.
   Every MathPix line with 2+ words is assigned to one of OUR units twice:
   - by text: the unit holding the largest share of the line's word pairs (single words for a line of 2), at
     least 0.6; a near tie (within 0.05) stays in the unit of the line before;
   - by box: the smallest of our boxes holding the line's centre.
   Per MathPix unit, each way:
   - **matched**: all its lines in one of ours, and that one holds no other MathPix unit's lines;
   - **merged**: our unit also holds lines of other MathPix units;
   - **split**: its lines go to 2+ of ours;
   - **missing**: none of its lines assigned;
   - **lost_start / lost_end**: lines at its start or end that are not in its main unit of ours.
   Our units come from the lines.json (same paragraph rule) and, with --model, from the docmodel objects of check 1.

7. **columns** (needs --mathpix; asked by the coordinator from pdfdrill-a2's trace). Where MathPix reads the page
   in side-by-side `column` containers, the reading must declare `column` lines too, and no text unit (a lines.json
   paragraph, a docmodel object) may cross a gutter. Without column lines pdfdrill joins text across the gutter into
   one Paragraph whose box spans both columns while its text is one column's.

5. **margin** (needs --mathpix). MathPix's margin notes are its page_info lines standing upright (taller than 3x
   their width: the rotated arXiv stamp) or outside every column. FAIL when one of our text boxes reaches across
   half a note's width beside it (the box took the note's ink), and when no page_info line of ours covers the note.

Scan mode: a page without a text layer is checked against MathPix when --mathpix is given. The reference text
inside a box is MathPix's text of the lines whose centre lies in it; every page record says which reference it used
("reference": "pdf text layer" or "mathpix"). Box-text, lines lost at start/end and paragraphs then run on scans too.

Exit 0 always. The report says PASS/FAIL per check and page, and --json writes every finding.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path
import sys
import unicodedata
from collections import Counter, defaultdict

TEXTY = {"text", "section_header", "title", "authors", "abstract", "footnote", "figure_label", "page_info",
         # contents entries in MathPix's form (GLYPHDRILL3 cf892ba writes them too): the item and its page number are
         # checked as lines, and their row is one unit, so a contents page is not dropped from the check
         "table_of_contents_item", "table_of_contents_number", "table_of_contents_row"}
CONTAINERS = {"section_header", "footnote", "title", "authors", "abstract", "figure_label", "table_of_contents_row"}
MODEL_TEXT = {"Paragraph": "text", "Section": "caption", "Footnote": "content", "ListItem": "content"}
MODEL_LEAVES = {"Paragraph", "Section", "Footnote", "ListItem", "Equation", "Diagram", "Picture", "Table"}
CMD = re.compile(r"\\[a-zA-Z@]+\*?")
ENV = re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?")
SPACED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_] ){2,}[^\W\d_](?![^\W\d_])")   # "G r e e d y" in \mathbf{G r e e d y}
TABLE_PARTS = {"table", "table_row", "table_column", "simple_cell", "complex_cell", "table_cell", "tabular"}
TOK = re.compile(r"[^\W\d_]{2,}")
CER_FAIL, OVERLAP_FAIL, SHARE = 0.25, 0.50, 0.6

try:
    from rapidfuzz.distance import Levenshtein as _L

    def lev(a: str, b: str) -> int:
        return _L.distance(a, b)
except ImportError:                                            # pragma: no cover
    def lev(a: str, b: str) -> int:
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s or "")
    s = ENV.sub(" ", s)
    s = SPACED.sub(lambda m: m.group(0).replace(" ", ""), s)
    s = CMD.sub(" ", s).replace("{", " ").replace("}", " ")
    return [w.lower() for w in TOK.findall(s)]


def letters(s: str) -> str:
    return "".join(words(s))


def pages_arg(s: str | None) -> set[int] | None:
    if not s:
        return None
    out = set()
    for part in s.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def box(region: dict | None):
    if not region:
        return None
    try:
        x, y = float(region["top_left_x"]), float(region["top_left_y"])
        return (x, y, x + float(region["width"]), y + float(region["height"]))
    except (KeyError, TypeError, ValueError):
        return None


def union(a, b):
    return b if a is None else (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inside(pt, b) -> bool:
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]


def centre(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def snip(s: str, n: int = 70) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 3] + "..."


# ---- the PDF text layer ---------------------------------------------------------------------------------------

def text_layer(pdf: str | None, page: int, words: str | None = None):
    """(width_pt, height_pt, [(x0, y0, x1, y1, word)] in the text layer's order), or None for a page without text.

    With `words`, a folder holding p<N>.bbox.html (the output of `pdftotext -bbox-layout -cropbox -f N -l N`) is read
    instead of running pdftotext, so a test suite can pin one page's word boxes without the PDF (2026-11-20)."""
    if words:
        f = Path(words) / f"p{page}.bbox.html"
        out = f.read_text(encoding="utf-8") if f.exists() else ""
    else:
        out = subprocess.run(["pdftotext", "-bbox-layout", "-cropbox", "-f", str(page), "-l", str(page), pdf, "-"],
                             capture_output=True, text=True).stdout
    m = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', out)
    if not m:
        return None
    ws = [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in
          re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', out)]
    return float(m.group(1)), float(m.group(2)), ws


# ---- units ----------------------------------------------------------------------------------------------------

def line_units(page: dict) -> list[dict]:
    """Paragraph-level units of a MathPix-shaped page, by MathPix's own rule. Leaf lines only carry text."""
    lines = page.get("lines") or []
    byid = {l.get("id"): l for l in lines if l.get("id")}
    units, cur = [], None
    for l in lines:
        if l.get("children_ids"):
            continue
        par = byid.get(l.get("parent_id")) or {}
        ptype = par.get("type")
        t = l.get("type")
        if ptype in CONTAINERS:
            key, kind = par.get("id"), ptype
        elif t == "text":
            starts = (l.get("text_display") or "").startswith("\n\n") or l.get("subtype") == "paragraph_start"
            col = l.get("column")
            if cur is None or cur["kind"] != "text" or starts or cur["column"] != col:
                key = f"p{len(units)}"
            else:
                key = cur["key"]
            kind = "text"
        else:
            key, kind = f"o{len(units)}", t
        if cur is None or cur["key"] != key:
            cur = {"key": key, "kind": kind, "column": l.get("column"), "lines": [], "box": None}
            units.append(cur)
        cur["lines"].append(l)
        b = box(l.get("region"))
        if b:
            cur["box"] = union(cur["box"], b)
    for u in units:
        u["text"] = " ".join(l.get("text") or "" for l in u["lines"])
    return units


def model_units(model: dict) -> dict[int, list[dict]]:
    """Docmodel objects with the box pdfdrill's inspect page draws for them, per page."""
    st = model.get("streams", {}).get("mathpix_lines", {})
    anchors, payload = st.get("anchors", []), st.get("payload", {})
    pos = {a: i for i, a in enumerate(anchors)}
    out: dict[int, list[dict]] = defaultdict(list)
    # containment: `children` is the fuller relation (a Section lists its Paragraphs while their `parent` is null:
    # 7,030 such links on lib:d68e0271bd4d, pdfdrill-a2 2026-11-19); invert it, and fall back to `parent`
    # every container counts: a child listed by two containers has two parents (the union, coordinator 2026-11-22;
    # before, the last container that listed it won)
    parents: dict[str, set] = defaultdict(set)
    for o in model.get("objects", []):
        if o.get("id") and o.get("parent"):
            parents[o["id"]].add(o["parent"])
        for c in o.get("children") or []:
            if isinstance(c, str) and o.get("id"):
                parents[c].add(o["id"])
    for o in model.get("objects", []):
        t = o.get("type")
        if t not in MODEL_LEAVES:
            continue
        pr = o.get("props", {})
        page = pr.get("page")
        b = None
        for rz in o.get("realizations", []):
            if rz.get("stream") != "mathpix_lines" or rz.get("start") not in pos or rz.get("end") not in pos:
                continue
            i, j = sorted((pos[rz["start"]], pos[rz["end"]]))
            for a in anchors[i:j + 1]:
                p = payload.get(a, {})
                if page is None:
                    page = p.get("_page")
                if p.get("_page") not in (None, page):
                    continue
                bb = box(p.get("region"))
                if bb:
                    b = union(b, bb)
        if b is None:
            r = pr.get("region")
            b = box(r if isinstance(r, dict) else None)
        if page is None:
            continue
        # an object with no box still holds text: it takes part in the paragraph match by text, as a reading line
        # without a region does in line_units, and the geometric checks skip it (pdfdrill-a2, 2026-11-20)
        out[int(page)].append({"key": o["id"], "kind": t, "box": b, "text": pr.get(MODEL_TEXT.get(t, ""), "") or "",
                               "texty": t in MODEL_TEXT, "ancestors": _ancestors(o["id"], parents)})
    return out


def _ancestors(oid: str, parents: dict) -> set:
    """The ids above an object in the docmodel's parent chain (a container holding its own lines is no overlap)."""
    seen, todo = set(), list(parents.get(oid, ()))
    while todo:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        todo.extend(parents.get(cur, ()))
    return seen


# ---- checks ---------------------------------------------------------------------------------------------------

def check_box_text(units: list[dict], tl, pw: float, ph: float) -> list[dict]:
    wpt, hpt, ws = tl
    sx, sy = pw / wpt, ph / hpt
    pix = [((a * sx + c * sx) / 2, (b * sy + d * sy) / 2, w) for a, b, c, d, w in ws]
    found = []
    for u in units:
        if u.get("box") is None:
            continue
        ref = letters(" ".join(w for x, y, w in pix if inside((x, y), u["box"])))
        hyp = letters(u["text"])
        if max(len(ref), len(hyp)) < 10:
            continue
        cer = lev(ref, hyp) / max(1, len(ref))
        u["cer"] = round(cer, 3)
        if cer > CER_FAIL:
            found.append({"check": "box-text", "unit": u["key"], "kind": u["kind"], "cer": round(cer, 3),
                          "box": [round(v) for v in u["box"]], "text": snip(u["text"]),
                          "ink_text": snip(" ".join(w for x, y, w in pix if inside((x, y), u["box"])))})
    return found


def check_overlap(units: list[dict]) -> list[dict]:
    found = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if units[j].get("key") in units[i].get("ancestors", ()) or units[i].get("key") in units[j].get("ancestors", ()):
                continue                       # a docmodel container and its own descendant (2026-11-19)
            a, b = units[i]["box"], units[j]["box"]
            if a is None or b is None:
                continue
            inter = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
            small = min(area(a), area(b))
            if small <= 0 or inter[2] <= inter[0] or inter[3] <= inter[1]:
                continue
            f = area(inter) / small
            if f > OVERLAP_FAIL:
                found.append({"check": "overlap", "a": f"{units[i]['kind']}:{snip(units[i]['text'], 35)}",
                              "b": f"{units[j]['kind']}:{snip(units[j]['text'], 35)}", "share_of_smaller": round(f, 2)})
    return found


def in_frame(mp_page: dict, our_page: dict) -> dict:
    """MathPix's page with every region scaled into OUR page's pixel frame (coordinator, 2026-11-21). The checks below
    compare MathPix boxes with ours; they were compared raw, which holds only when both readings share a page size.
    MathPix reads at 250 dpi, gd3 at 400 dpi, Gemma4 at its own size: without this, box matches land on the wrong
    units (Lurie p1, gd3 3400 px against MathPix 2125 px)."""
    pw, ph = float(our_page.get("page_width") or 0), float(our_page.get("page_height") or 0)
    mw, mh = float(mp_page.get("page_width") or 0), float(mp_page.get("page_height") or 0)
    if not (pw and ph and mw and mh) or (abs(pw - mw) < 0.5 and abs(ph - mh) < 0.5):
        return mp_page
    kx, ky = pw / mw, ph / mh
    q = dict(mp_page, page_width=pw, page_height=ph, lines=[])
    for l in mp_page.get("lines") or []:
        r = l.get("region")
        if isinstance(r, dict):
            r = dict(r, top_left_x=float(r.get("top_left_x") or 0) * kx, top_left_y=float(r.get("top_left_y") or 0) * ky,
                     width=float(r.get("width") or 0) * kx, height=float(r.get("height") or 0) * ky)
            l = dict(l, region=r)
        q["lines"].append(l)
    return q


def check_paragraphs(mp_units: list[dict], ours: list[dict]) -> dict:
    """Assign MathPix lines to our units by text and by box; classify each MathPix text unit."""
    ours = [u for u in ours if u.get("texty", u["kind"] in TEXTY)]
    def grams(ws):
        return Counter(zip(ws, ws[1:])) if len(ws) >= 3 else Counter(ws)
    bags = [(Counter(words(u["text"])), Counter(zip(words(u["text"]), words(u["text"])[1:]))) for u in ours]
    res = {}
    for mode in ("text", "box"):
        assign = {}                                   # (unit idx, line idx) -> our idx or None
        last = None
        for ui, mu in enumerate(mp_units):
            if mu["kind"] not in TEXTY or mu["kind"] == "page_info":
                continue
            for li, l in enumerate(mu["lines"]):
                ws = words(l.get("text") or "")
                if len(ws) < 2:
                    continue
                best = None
                if mode == "text":
                    lw = grams(ws)
                    big = len(ws) >= 3
                    sc = [(sum(min(c, bag[1 if big else 0][w]) for w, c in lw.items()) / sum(lw.values()), k)
                          for k, bag in enumerate(bags)]
                    s, k = max(sc, default=(0, None))
                    prev = assign.get((ui, li - 1)) if li else last
                    if prev is not None and k != prev and sc[prev][0] >= s - 0.05:
                        s, k = sc[prev]                    # a near tie stays in the previous line's unit
                    best = k if s >= SHARE else None
                else:
                    b = box(l.get("region"))
                    if b:
                        c = centre(b)
                        hits = [k for k, u in enumerate(ours) if u["box"] and inside(c, u["box"])]
                        best = min(hits, key=lambda k: area(ours[k]["box"])) if hits else None
                assign[(ui, li)] = best
                if best is not None:
                    last = best
        holders = defaultdict(set)                   # our idx -> MathPix units with lines in it
        for (ui, li), k in assign.items():
            if k is not None:
                holders[k].add(ui)
        rows = []
        for ui, mu in enumerate(mp_units):
            seq = [assign[(ui, li)] for li in range(len(mu["lines"])) if (ui, li) in assign]
            if not seq:
                continue
            got = [k for k in seq if k is not None]
            row = {"unit": ui, "kind": mu["kind"], "column": mu["column"], "lines": len(seq), "text": snip(mu["text"])}
            if not got:
                row["status"] = "missing"
            else:
                main = Counter(got).most_common(1)[0][0]
                ls = next(i for i, k in enumerate(seq) if k == main)
                le = next(i for i, k in enumerate(reversed(seq)) if k == main)
                row.update(lost_start=ls, lost_end=le, ours=snip(ours[main]["text"]), our_kind=ours[main]["kind"])
                if len(set(got)) > 1:
                    row["status"] = "split"
                elif len(holders[main]) > 1:
                    row["status"] = "merged"
                else:
                    row["status"] = "matched"
            rows.append(row)
        res[mode] = rows
    return res


def gutters(page: dict) -> list[tuple]:
    """Gutters between MathPix `column` containers that stand side by side: (x0, y0, x1, y1) of the white strip."""
    cols = [box(l.get("region")) for l in page.get("lines") or [] if l.get("type") == "column" and box(l.get("region"))]
    out = []
    for a in cols:
        for b in cols:
            if a[2] <= b[0] and min(a[3], b[3]) > max(a[1], b[1]):
                nearer = [c for c in cols if c is not a and c is not b and a[2] <= c[0] and c[2] <= b[0]]
                if not nearer:
                    out.append((a[2], max(a[1], b[1]), b[0], min(a[3], b[3])))
    return out


def check_columns(our_page: dict, units: list[dict], mp_page: dict, label: str) -> list[dict]:
    """A page MathPix reads in side-by-side columns: ours declares columns too, and no text unit crosses a gutter."""
    gs = gutters(mp_page)
    if not gs:
        return []
    found = []
    if not any(l.get("type") == "column" for l in our_page.get("lines") or []):
        found.append({"check": "columns", "what": f"no column lines in the reading; MathPix has {len(gs)} gutter(s)"})
    for u in units:
        if not u.get("texty", u["kind"] in TEXTY) or u["kind"] == "page_info":
            continue
        b = u["box"]
        if b is None:
            continue
        for g in gs:
            if b[0] < g[0] and b[2] > g[2] and min(b[3], g[3]) > max(b[1], g[1]):
                found.append({"check": "columns", "what": f"{label} unit crosses the gutter x {round(g[0])}-{round(g[2])}",
                              "kind": u["kind"], "box": [round(v) for v in b], "text": snip(u["text"])})
                break
    return found


def margin_notes(mp_page: dict) -> list[tuple]:
    """MathPix's margin notes: page_info lines standing upright (taller than 3x their width, e.g. the rotated arXiv
    stamp) or lying outside every `column` container."""
    cols = [box(l.get("region")) for l in mp_page.get("lines") or [] if l.get("type") == "column" and box(l.get("region"))]
    out = []
    for l in mp_page.get("lines") or []:
        b = box(l.get("region"))
        if l.get("type") != "page_info" or b is None:
            continue
        upright = (b[3] - b[1]) > 3 * (b[2] - b[0])
        outside = bool(cols) and all(b[2] <= c[0] or b[0] >= c[2] for c in cols)
        if upright or outside:
            out.append((b, l.get("text") or ""))
    return out


def check_margin(our_page: dict, mp_page: dict) -> list[dict]:
    """Check 5: no text box of ours takes a margin note's ink (it reaches across half the note's width beside it),
    and the note is a line of its own (a page_info box over it)."""
    found = []
    for nb_, ntext in margin_notes(mp_page):
        nw = nb_[2] - nb_[0]
        own = False
        for l in our_page.get("lines") or []:
            b = box(l.get("region"))
            if b is None or l.get("children_ids") or l.get("type") == "column":
                continue
            ix = min(b[2], nb_[2]) - max(b[0], nb_[0])
            iy = min(b[3], nb_[3]) - max(b[1], nb_[1])
            if ix <= 0 or iy <= 0:
                continue
            if l.get("type") == "page_info" and ix >= 0.5 * nw:
                own = True
            elif l.get("type") != "page_info" and ix >= 0.5 * nw:
                found.append({"check": "margin", "what": "text box takes the margin note's ink",
                              "note": snip(ntext, 40), "kind": l.get("type"), "box": [round(v) for v in b],
                              "text": snip(l.get("text") or "")})
        if not own:
            found.append({"check": "margin", "what": "margin note has no line of its own", "note": snip(ntext, 40),
                          "note_box": [round(v) for v in nb_]})
    return found


def summarise_paragraphs(rows: list[dict]) -> dict:
    out: dict = defaultdict(Counter)
    for r in rows:
        c = out[r["column"] if r["column"] is not None else "-"]
        c[r["status"]] += 1
        c["lines_lost_start"] += r.get("lost_start", 0)
        c["lines_lost_end"] += r.get("lost_end", 0)
    return {str(k): dict(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


# ---- main -----------------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf")
    ap.add_argument("--words", help="folder of p<N>.bbox.html (pdftotext -bbox-layout -cropbox), in place of --pdf")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--model")
    ap.add_argument("--mathpix")
    ap.add_argument("--pages")
    ap.add_argument("--json")
    a = ap.parse_args()
    if not (a.pdf or a.words):
        ap.error("one of --pdf or --words is required")
    want = pages_arg(a.pages)
    lines = json.load(open(a.lines, encoding="utf-8"))
    mp = {p["page"]: p for p in json.load(open(a.mathpix, encoding="utf-8"))["pages"]} if a.mathpix else {}
    mdl = model_units(json.load(open(a.model, encoding="utf-8"))) if a.model else {}
    report = {"pdf": a.pdf, "lines": a.lines, "model": a.model, "mathpix": a.mathpix, "pages": []}
    for page in lines["pages"]:
        n = page.get("page")
        if want and n not in want:
            continue
        pw, ph = float(page.get("page_width") or 0), float(page.get("page_height") or 0)
        units = line_units(page)
        unplaced = sum(1 for l in page.get("lines") or [] if l.get("type") in TEXTY and not l.get("children_ids")
                       and box(l.get("region")) is None)
        byid = {l.get("id"): l for l in page.get("lines") or [] if l.get("id")}
        leaves = [{"key": l.get("id") or f"l{i}", "kind": l.get("type"), "box": box(l.get("region")),
                   "text": l.get("text") or ""}
                  for i, l in enumerate(page.get("lines") or []) if not l.get("children_ids") and box(l.get("region"))
                  and l.get("type") not in TABLE_PARTS
                  and (byid.get(l.get("parent_id")) or {}).get("type") not in TABLE_PARTS]
        rec = {"page": n, "checks": {}, "text_lines_without_box": unplaced}
        tl = text_layer(a.pdf, n, a.words)
        born = tl is not None and len(tl[2]) >= 20
        rec["reference"] = "pdf text layer" if born else "none"
        if not born and n in mp:
            # scan mode: no text layer, so the reference inside a box is MathPix's text of the lines whose centre
            # lies in it (a reading checked against MathPix, not against the ink; labelled as such)
            q = mp[n]
            ws = [(*b, l.get("text") or "") for l in q.get("lines") or []
                  if not l.get("children_ids") and l.get("type") in TEXTY and (b := box(l.get("region")))]
            tl = (float(q.get("page_width") or pw), float(q.get("page_height") or ph), ws)
            born = True
            rec["reference"] = "mathpix"
        texty_leaves = [u for u in leaves if u["kind"] in TEXTY]
        rec["checks"]["box_text_lines"] = (check_box_text(texty_leaves, tl, pw, ph) if born else "NOT RUN: no text layer")
        rec["checks"]["overlap_lines"] = check_overlap(leaves)
        mu = mdl.get(n, [])
        if a.model:
            rec["checks"]["box_text_model"] = (check_box_text([u for u in mu if u["texty"]], tl, pw, ph)
                                               if born else "NOT RUN: no text layer")
            rec["checks"]["overlap_model"] = check_overlap(mu)
        if n in mp:
            mq = in_frame(mp[n], page)              # MathPix's boxes in our page's pixel frame
            mpu = line_units(mq)
            rec["checks"]["columns_lines"] = check_columns(page, units, mq, "lines.json")
            rec["checks"]["margin_lines"] = check_margin(page, mq)
            if a.model:
                rec["checks"]["columns_model"] = check_columns(page, mu, mq, "docmodel")
            rec["paragraphs_lines"] = check_paragraphs(mpu, units)
            if a.model:
                rec["paragraphs_model"] = check_paragraphs(mpu, mu)
        report["pages"].append(rec)
        # human report
        print(f"== page {n}")
        for k, v in rec["checks"].items():
            if isinstance(v, str):
                print(f"  {k:16s} {v}")
                continue
            print(f"  {k:16s} {'FAIL' if v else 'PASS'} {len(v)}")
            for f in v[:12]:
                print("     ", {x: y for x, y in f.items() if x != "check"})
        for src in ("paragraphs_lines", "paragraphs_model"):
            if src in rec:
                for mode, rows in rec[src].items():
                    print(f"  {src}/{mode}: per column {summarise_paragraphs(rows)}")
                    for r in rows:
                        if r["status"] != "matched" or r.get("lost_start") or r.get("lost_end"):
                            print("     ", r["status"], f"col {r['column']}", r["kind"], f"lines {r['lines']}",
                                  f"lost start/end {r.get('lost_start', '-')}/{r.get('lost_end', '-')}", "|", r["text"],
                                  "| ours:", r.get("our_kind", ""), r.get("ours", ""))
    # the summary line every layout report carries (T-0154): a failure must not hide by losing its box
    n_text = sum(1 for page in lines["pages"] if not want or page.get("page") in want
                 for l in page.get("lines") or [] if l.get("type") in TEXTY and not l.get("children_ids"))
    bad = sum(len(r["checks"]["box_text_lines"]) for r in report["pages"] if isinstance(r["checks"]["box_text_lines"], list))
    nobox = sum(r["text_lines_without_box"] for r in report["pages"])
    report["summary"] = {"text_lines": n_text, "box_text_fail": bad, "box_text_rate": round(bad / max(1, n_text), 3),
                         "without_box": nobox, "without_box_rate": round(nobox / max(1, n_text), 3)}
    refs = sorted({r.get("reference", "-") for r in report["pages"]})
    report["summary"]["reference"] = refs
    print(f"SUMMARY text lines {n_text}: box-text fail {bad} ({bad / max(1, n_text):.1%}), "
          f"without box {nobox} ({nobox / max(1, n_text):.1%}); reference: {', '.join(refs)}")
    # The model line (audit 2026-11-19): until now the SUMMARY counted only the lines.json box-text failures, and the
    # exit code was always 0. The owner inspects pdfdrill's docmodel objects (obj_...), whose overlaps, wrong texts and
    # merged/split paragraphs were found here per page but appeared in no summary and failed no run.
    def _count(key):
        return sum(len(r["checks"].get(key) or []) for r in report["pages"] if isinstance(r["checks"].get(key), list))
    para = {}
    for src in ("paragraphs_lines", "paragraphs_model"):
        tally = {}
        for r in report["pages"]:
            for row in (r.get(src) or {}).get("text", []):
                tally[row["status"]] = tally.get(row["status"], 0) + 1
        if tally:
            para[src] = tally
    report["summary"]["findings"] = {k: _count(k) for k in ("box_text_lines", "overlap_lines", "columns_lines",
                                                            "margin_lines", "box_text_model", "overlap_model",
                                                            "columns_model")}
    report["summary"]["paragraphs_by_text"] = para
    fm = report["summary"]["findings"]
    print("SUMMARY findings: " + ", ".join(f"{k} {v}" for k, v in fm.items()))
    for src, t in para.items():
        n = sum(t.values())
        print(f"SUMMARY {src} (MathPix units by text): matched {t.get('matched', 0)} of {n}, "
              + ", ".join(f"{k} {v}" for k, v in sorted(t.items()) if k != "matched"))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    # exit 1 when anything failed, so a run can fail (a probe whose answer is the same on a good and a broken page
    # is no probe)
    # Paragraph statuses do not fail the run: MathPix's own lines.json checked against itself matches only 107 of 128
    # units on 1805.01788 (the lines-to-units rule is not exact), so they are reported beside that ceiling instead.
    failed = any(fm.values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
