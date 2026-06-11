"""
rectoverso.py — classify book pages as recto (right) / verso (left) from
MathPix lines.json layout. Vendored from the user's prototype, extended with
roman-numeral PARITY and the sequence-alternation post-pass.

Why: column indices in OCR output are LAYOUT positions, not semantic roles.
On a book with marginal side notes the meaning flips with the page side:

    verso (left page):  col 0 = side notes (outer/left margin), col 1 = body
    recto (right page): col 0 = body,                col 1 = side notes (outer/right)

So before mapping "column N" to "body text" vs "side note", you need the page
side. Three independent per-page signals, fused by confidence-weighted vote:

  1. printed page number PARITY: odd = recto, even = verso (Western books).
     Roman front-matter numerals (xii = 12) count too.
  2. page number X POSITION: page numbers sit on the OUTER edge -> number on
     the right edge = recto, left edge = verso. (Centered numbers abstain.)
  3. column-width asymmetry: the NARROW column is the side-note margin, which
     sits on the OUTER edge: narrow right of body = recto, left = verso.

Plus one sequence signal (`apply_alternation`): physical book pages ALTERNATE
sides, so the confidence-weighted best alternating phase fills pages where the
per-page signals abstain and overrules isolated weak contradictions (the
repair stays visible: `signals["alternation"]`, original side in evidence).

Tolerant input: works with MathPix lines.json shapes where each line has a
region ({top_left_x, top_left_y, width, height} or [x,y,w,h] / point list
under "bbox"/"cnt") and "text". An explicit per-line "column" field is used
when present, else columns are derived by x-clustering.

A sibling annotation for FRONT/BACK side of scanned duplex documents is
planned on the same fusion shape (parity of the physical scan index + staple/
punch-hole mirror geometry).

API:
    classify_page(page_dict) -> PageSide(side, confidence, evidence)
    classify_lines_json(path_or_dict) -> list[PageSide]
    apply_alternation(list[PageSide]) -> list[PageSide]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

ROMAN_RE = re.compile(r"^[ivxlcdm]{1,7}$", re.I)
NUM_RE = re.compile(r"^\(?(\d{1,4})\)?$")

_ROMAN_VAL = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def roman_to_int(s: str) -> Optional[int]:
    """Strict-enough roman parser; None for non-numerals (e.g. 'mix' is a
    valid numeral 1009 by subtractive reading — we only reject impossible
    sequences, the header/footer band + length cap do the rest)."""
    s = s.lower()
    if not ROMAN_RE.match(s):
        return None
    total = 0
    for ch, nxt in zip(s, list(s[1:]) + [None]):
        v = _ROMAN_VAL[ch]
        total += -v if (nxt and _ROMAN_VAL[nxt] > v) else v
    return total if total > 0 else None


@dataclass
class PageSide:
    side: Optional[str]            # "recto" | "verso" | None
    confidence: float              # 0..1
    evidence: dict = field(default_factory=dict)


# ----------------------------------------------------------- line accessors
def _region(line: dict) -> Optional[tuple[float, float, float, float]]:
    """(x, y, w, h) from whatever shape this lines.json uses."""
    r = line.get("region")
    if isinstance(r, dict):
        if "top_left_x" in r:
            return (float(r["top_left_x"]), float(r["top_left_y"]),
                    float(r.get("width", 0)), float(r.get("height", 0)))
        if "x" in r:
            return (float(r["x"]), float(r["y"]),
                    float(r.get("width", r.get("w", 0))),
                    float(r.get("height", r.get("h", 0))))
    for key in ("bbox", "cnt"):
        v = line.get(key)
        if isinstance(v, (list, tuple)) and len(v) >= 4 and not isinstance(v[0], (list, tuple)):
            x0, y0, x1, y1 = (float(v[0]), float(v[1]), float(v[2]), float(v[3]))
            if x1 > x0 and y1 > y0 and (x1 - x0) < 10000:
                return (x0, y0, x1 - x0, y1 - y0)
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
            xs = [float(p[0]) for p in v]
            ys = [float(p[1]) for p in v]
            return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return None


def _page_geometry(page: dict, lines: list[dict]) -> tuple[float, float]:
    for wk, hk in (("image_width", "image_height"),
                   ("page_width", "page_height"), ("width", "height")):
        if page.get(wk) and page.get(hk):
            return float(page[wk]), float(page[hk])
    # fall back to the extent of the content
    xs, ys = [], []
    for ln in lines:
        r = _region(ln)
        if r:
            xs += [r[0], r[0] + r[2]]
            ys += [r[1], r[1] + r[3]]
    return (max(xs) if xs else 1.0, max(ys) if ys else 1.0)


# ------------------------------------------------------------------ signals
def _page_number_signal(lines: list[dict], pw: float, ph: float
                        ) -> tuple[Optional[str], Optional[str], dict]:
    """(parity_vote, position_vote, evidence). Looks in header/footer bands."""
    band = 0.12 * ph
    for ln in lines:
        r = _region(ln)
        text = (ln.get("text") or "").strip()
        if not r or not text:
            continue
        x, y, w, h = r
        in_band = y < band or (y + h) > ph - band
        if not in_band:
            continue
        is_pageno = (str(ln.get("type", "")).lower() in
                     ("page_number", "page_info", "pagination"))
        m = NUM_RE.match(text)
        roman = roman_to_int(text)
        if not (is_pageno or m or roman):
            continue
        ev = {"page_number_text": text,
              "page_number_xc": round((x + w / 2) / pw, 3)}
        parity = None
        n = int(m.group(1)) if m else roman
        if n:
            parity = "recto" if n % 2 == 1 else "verso"
            ev["printed_number"] = n
        xc = (x + w / 2) / pw
        pos = None
        if xc > 0.62:
            pos = "recto"          # number on the right edge -> right page
        elif xc < 0.38:
            pos = "verso"
        return parity, pos, ev
    return None, None, {}


def _column_signal(lines: list[dict], pw: float, ph: float
                   ) -> tuple[Optional[str], dict]:
    """
    Narrow side-note column vs wide body column.
    Uses explicit 'column' fields when present, else x-clusters line starts.
    """
    body_band = (0.15 * ph, 0.88 * ph)     # exclude header/footer
    cols: dict[Any, list[tuple[float, float]]] = {}

    explicit = all("column" in ln for ln in lines if _region(ln))
    for ln in lines:
        r = _region(ln)
        if not r:
            continue
        x, y, w, h = r
        if not (body_band[0] <= y <= body_band[1]):
            continue
        key = ln["column"] if explicit else round(x / pw, 1)  # cluster by left edge
        cols.setdefault(key, []).append((x, w))

    if len(cols) < 2:
        return None, {"columns_found": len(cols)}

    stats = []
    for key, items in cols.items():
        xs = [x for x, w in items]
        ws = [w for x, w in items]
        stats.append({
            "key": key, "n": len(items),
            "x_center": (sum(x + w / 2 for x, w in items) / len(items)) / pw,
            "median_w": sorted(ws)[len(ws) // 2] / pw,
        })
    stats = [s for s in stats if s["n"] >= 2]
    if len(stats) < 2:
        return None, {"columns_found": len(stats)}
    stats.sort(key=lambda s: s["median_w"])
    narrow, body = stats[0], stats[-1]
    ev = {"narrow_col": narrow, "body_col": body}
    if body["median_w"] < 1.8 * narrow["median_w"]:
        return None, ev | {"note": "no clear narrow margin column"}
    side = "recto" if narrow["x_center"] > body["x_center"] else "verso"
    return side, ev


# --------------------------------------------------------------- classifier
def classify_page(page: dict) -> PageSide:
    lines = page.get("lines") or page.get("text_lines") or []
    if not lines:
        return PageSide(None, 0.0, {"note": "no lines"})
    pw, ph = _page_geometry(page, lines)

    parity, numpos, ev_num = _page_number_signal(lines, pw, ph)
    colside, ev_col = _column_signal(lines, pw, ph)

    votes = {"recto": 0.0, "verso": 0.0}
    weights = ((parity, 0.5, "number_parity"),
               (numpos, 0.3, "number_position"),
               (colside, 0.35, "column_asymmetry"))
    used = {}
    for vote, w, name in weights:
        if vote:
            votes[vote] += w
            used[name] = vote
    total = votes["recto"] + votes["verso"]
    if total == 0:
        return PageSide(None, 0.0, {"signals": used, **ev_num, **ev_col})
    side = "recto" if votes["recto"] >= votes["verso"] else "verso"
    margin = abs(votes["recto"] - votes["verso"])
    conf = min(1.0, margin / 0.5 * 0.6 + (0.4 if len(used) > 1 else 0.0))
    return PageSide(side, round(conf, 2),
                    {"signals": used, **ev_num, **ev_col})


# ---------------------------------------------------------------- sequence
def apply_alternation(results: list[PageSide]) -> list[PageSide]:
    """Physical book pages alternate recto/verso, so the page sequence itself
    is a signal. Pick the alternating PHASE that best agrees with the
    confidence-weighted per-page votes, then fill abstaining pages and
    overrule contradictions whose confidence is below the phase's support.
    The repair stays visible: `signals["alternation"]` + the original side
    kept as `before_alternation`."""
    if not results:
        return results
    # phase 0: even index = recto; phase 1: even index = verso
    score = [0.0, 0.0]
    for i, r in enumerate(results):
        if not r.side:
            continue
        expected0 = "recto" if i % 2 == 0 else "verso"
        score[0 if r.side == expected0 else 1] += r.confidence
    if max(score) == 0:
        # No page anchored a phase (e.g. a slide deck with no book layout):
        # do NOT invent sides from an arbitrary alternation.
        return results
    phase = 0 if score[0] >= score[1] else 1
    support = max(score) - min(score)
    out = []
    for i, r in enumerate(results):
        expected = ("recto" if i % 2 == 0 else "verso") if phase == 0 else \
                   ("verso" if i % 2 == 0 else "recto")
        if r.side == expected:
            out.append(r)
            continue
        if r.side and r.confidence > support:
            out.append(r)          # strong local evidence beats the sequence
            continue
        ev = dict(r.evidence)
        if r.side:
            ev["before_alternation"] = r.side
        ev.setdefault("signals", {})
        ev["signals"] = dict(ev["signals"], alternation=expected)
        conf = round(min(1.0, 0.3 + 0.1 * min(support, 4.0)), 2)
        out.append(PageSide(expected, conf, ev))
    return out


def classify_lines_json(src) -> list[PageSide]:
    data = src if isinstance(src, (dict, list)) else json.load(open(src))
    pages = data.get("pages", data) if isinstance(data, dict) else data
    out = []
    for pg in pages:
        out.append(classify_page(pg) if isinstance(pg, dict)
                   else PageSide(None, 0.0, {}))
    return out


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m pdfdrill.rectoverso lines.json [--json] [--alternation]")
        return 2
    results = classify_lines_json(args[0])
    if "--alternation" in args:
        results = apply_alternation(results)
    if "--json" in args:
        print(json.dumps([r.__dict__ for r in results], indent=2))
        return 0
    for i, r in enumerate(results, 1):
        sig = ", ".join(f"{k}={v}" for k, v in r.evidence.get("signals", {}).items())
        print(f"page {i:3d}: {r.side or 'unknown':6s} conf {r.confidence:.2f}"
              + (f"  [{sig}]" if sig else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
