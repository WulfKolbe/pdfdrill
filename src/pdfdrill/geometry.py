"""
Cheap word-geometry level (pdftotext -tsv) and its fusion onto mathpix_lines.

This is the substrate for cross-level information fusion: MathPix gives us
text + LaTeX but flattens layout; pdftotext -tsv gives us per-word bounding
boxes (and the page box) essentially for free. We lift the tsv into a
`pdf_lines` Stream, then for each MathPix line find the geometrically- and
textually-matching pdftotext line and record an `Alignment(kind="geometry")`.
Each matched MathPix line is annotated with a `_geom` dict carrying its
normalized left/right margins, baseline y, and **indentation** relative to the
page's body-left margin — the signal block detectors (algorithm, itemize) and
equation-number fusion build on.

Coordinates are normalized to the page box ([0,1]) so the two coordinate
systems (tsv points vs MathPix image px) become comparable.
"""
from __future__ import annotations

import difflib
import subprocess
from collections import defaultdict
from typing import Any


def run_tsv(pdf_path: str, timeout: float = 180.0) -> str:
    """Return raw `pdftotext -tsv` output for the whole document."""
    out = subprocess.run(
        ["pdftotext", "-tsv", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=timeout,
    )
    return out.stdout


def parse_tsv(tsv_text: str) -> tuple[list[dict], dict[int, tuple[float, float]]]:
    """Parse tsv into (words, page_dims).

    words: [{page, block, line, x0, y0, x1, y1, text}] for level-5 word rows.
    page_dims: {page_num: (width_pts, height_pts)} from level-1 page rows.
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
        if level == 1:                      # page row carries the page box
            page_dims[page] = (w, h)
        elif level == 5 and text.strip():   # word row
            words.append({
                "page": page,
                "block": int(c[idx["block_num"]]),
                "line": int(c[idx["line_num"]]),
                "x0": left, "y0": top, "x1": left + w, "y1": top + h,
                "text": text,
            })
    return words, page_dims


def group_lines(words: list[dict]) -> list[dict]:
    """Group words into text lines by (page, block, line)."""
    g: dict[tuple, list[dict]] = defaultdict(list)
    for w in words:
        g[(w["page"], w["block"], w["line"])].append(w)
    lines: list[dict] = []
    for (page, _b, _l), ws in g.items():
        ws.sort(key=lambda w: w["x0"])
        lines.append({
            "page": page,
            "x0": min(w["x0"] for w in ws),
            "x1": max(w["x1"] for w in ws),
            "y0": min(w["y0"] for w in ws),
            "y1": max(w["y1"] for w in ws),
            "text": " ".join(w["text"] for w in ws),
        })
    lines.sort(key=lambda l: (l["page"], l["y0"], l["x0"]))
    return lines


def _norm_txt(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _percentile(sorted_vals: list[float], frac: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, int(len(sorted_vals) * frac))
    return sorted_vals[i]


def clear_geometry(doc) -> None:
    """Remove a prior fusion (pdf_lines stream, geometry alignments, _geom)."""
    doc.streams.pop("pdf_lines", None)
    doc.alignments = [a for a in doc.alignments if a.kind != "geometry"]
    if "mathpix_lines" in doc.streams:
        for a in doc.stream("mathpix_lines").anchors:
            doc.stream("mathpix_lines").payload[a].pop("_geom", None)
    doc.meta.get("geometry", {}).pop("body_left_norm", None)


def fuse(doc, pdf_lines: list[dict], page_dims_pts: dict[int, tuple[float, float]],
         y_tol: float = 0.025) -> dict[str, Any]:
    """Add a pdf_lines stream, fuse it onto mathpix_lines, annotate _geom.

    Returns stats {pdf_lines, matched, mean_sim}.
    """
    from docmodel.core import Range, Alignment

    s_pl = doc.ensure_stream("pdf_lines")
    pl_by_page: dict[int, list[tuple]] = defaultdict(list)
    for L in pdf_lines:
        pw, ph = page_dims_pts.get(L["page"], (None, None))
        x0n = L["x0"] / pw if pw else None
        x1n = L["x1"] / pw if pw else None
        yn = L["y0"] / ph if ph else None
        a = s_pl.append(page=L["page"], text=L["text"],
                        x0_norm=x0n, x1_norm=x1n, y_norm=yn)
        pl_by_page[L["page"]].append((a, L, x0n, x1n, yn))

    # Per-page body-left margin = ~10th percentile of line left edges.
    body_left: dict[int, float] = {}
    for pg, tups in pl_by_page.items():
        xs = sorted(t[2] for t in tups if t[2] is not None)
        body_left[pg] = _percentile(xs, 0.10)
    doc.meta.setdefault("geometry", {})["body_left_norm"] = {
        str(k): round(v, 4) for k, v in body_left.items()}

    pages_meta = {p["page"]: p for p in doc.meta.get("pages", [])}
    mp = doc.stream("mathpix_lines") if "mathpix_lines" in doc.streams else None
    matched = 0
    sims: list[float] = []
    if mp is not None:
        for anchor in mp.anchors:
            p = mp.payload[anchor]
            region = p.get("region")
            page = p.get("_page")
            pm = pages_meta.get(page)
            if not region or not pm or not pm.get("page_height"):
                continue
            y_mp = region.get("top_left_y")
            if y_mp is None:
                continue
            yn_mp = y_mp / pm["page_height"]
            cands = [t for t in pl_by_page.get(page, [])
                     if t[4] is not None and abs(t[4] - yn_mp) <= y_tol]
            if not cands:
                continue
            mptext = _norm_txt(p.get("text") or p.get("text_display") or "")

            def score(t):
                s = (difflib.SequenceMatcher(None, mptext, _norm_txt(t[1]["text"])).ratio()
                     if mptext else 0.0)
                return (s, -abs(t[4] - yn_mp))

            best = max(cands, key=score)
            a, L, x0n, x1n, yn = best
            s = score(best)[0]
            indent = (x0n - body_left.get(page, 0.0)) if x0n is not None else None
            p["_geom"] = {
                "x0_norm": round(x0n, 4) if x0n is not None else None,
                "x1_norm": round(x1n, 4) if x1n is not None else None,
                "y_norm": round(yn, 4) if yn is not None else None,
                "indent_norm": round(indent, 4) if indent is not None else None,
                "sim": round(s, 3),
                "pdf_text": L["text"],
            }
            doc.add_alignment(Alignment(
                kind="geometry",
                left=Range("mathpix_lines", anchor, anchor),
                right=Range("pdf_lines", a, a),
                props={"x0_norm": p["_geom"]["x0_norm"],
                       "indent_norm": p["_geom"]["indent_norm"],
                       "sim": p["_geom"]["sim"]},
            ))
            matched += 1
            sims.append(s)

    return {
        "pdf_lines": len(pdf_lines),
        "matched": matched,
        "mean_sim": round(sum(sims) / len(sims), 3) if sims else None,
    }
