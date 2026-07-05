#!/usr/bin/env python3
"""
docinspect.py — a DevTools-style inspector view over a pdfdrill docmodel.

This is an ADDITIONAL lens on the same 600-DPI pyramid that the existing
OpenSeadragon viewer uses (tools/imageserver/). Where that viewer is a deep-zoom
image, this one overlays the *docmodel* on the page and lets you drill into every
element the way Chrome's "Inspect element" does:

  ┌───────────────────────────────┬───────────────────────────┐
  │  PAGE (pixel-faithful 600 DPI) │  ELEMENTS  (DOM-like tree) │
  │  every DocObject drawn as a    │  Document ▸ Page 3 ▸ …     │
  │  hover/click highlight box     │    [Diagram] Fig 1 …       │
  │        ── or ──                │    [Formula] 64.5×…        │
  │  REFLOW (arXiv/LaTeX2HTML-ish  ├───────────────────────────┤
  │  reading order, KaTeX + crops) │  INSPECTOR (selected elem) │
  │                                │  type · page · region ·   │
  │                                │  latex(KaTeX) · props ·   │
  │                                │  realizations · alignments │
  └───────────────────────────────┴───────────────────────────┘

Hovering an element in the tree highlights its box on the page (and vice
versa); selecting shows its full record. The reflow tab reconstructs a near-
identical reading-order HTML from the model (headings, prose, KaTeX math,
cropped figures) — the docmodel analogue of arXiv's LaTeX2HTML output, except
the source of truth is the layered docmodel rather than raw .tex.

DATA IN
  model.docmodel.json   the DocObject graph (streams / objects / alignments)
  <name>.tiddlers.json  optional, for the rendered templated content

IMAGE SOURCE (one of)
  --pages-dir DIR    page images at DIR/p{N}.png (a 600-DPI folder)
  --image-base URL   a mathpix_server.py origin (/pages/pN.png + /cropped/…)
  --embed            inline downscaled page images as data: URIs; figures are
                     cropped client-side from the page image (self-contained,
                     offline — this is the mode for the Claude.ai preview)

The core is pure-stdlib. --embed uses Pillow (already a pdfdrill dep) to
downscale the page images before inlining.

CLI
  python3 tools/docinspect.py MODEL.docmodel.json --pages-dir PAGES -o out.html
  python3 tools/docinspect.py MODEL.docmodel.json --embed --embed-dpi 120 -o out.html
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import sys
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Model loading + geometry
# ---------------------------------------------------------------------------

# Content object types that participate in the reading-order reflow, in the
# rough visual weight we give them.
_TEXTY = {"Abstract", "Paragraph", "ListItem", "Footnote", "Sidenote", "Caption"}
_IMAGEY = {"Picture", "Diagram", "Chart"}


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _int(v: Any) -> Optional[int]:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def build_stream_index(model: dict) -> dict:
    """anchor_id -> payload, plus per-stream ordered anchor id list."""
    payload_of: dict[str, dict] = {}
    order_of: dict[str, list[str]] = {}
    for name, st in model.get("streams", {}).items():
        anchors = st.get("anchors", [])
        order_of[name] = anchors
        pl = st.get("payload", {})
        for aid in anchors:
            payload_of[aid] = pl.get(aid, {})
    return {"payload": payload_of, "order": order_of}


def _region_to_box(region: dict) -> Optional[dict]:
    if not region:
        return None
    x = _int(region.get("top_left_x"))
    y = _int(region.get("top_left_y"))
    w = _int(region.get("width"))
    h = _int(region.get("height"))
    if None in (x, y, w, h):
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _union(a: Optional[dict], b: Optional[dict]) -> Optional[dict]:
    if a is None:
        return b
    if b is None:
        return a
    x0 = min(a["x"], b["x"])
    y0 = min(a["y"], b["y"])
    x1 = max(a["x"] + a["w"], b["x"] + b["w"])
    y1 = max(a["y"] + a["h"], b["y"] + b["h"])
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def object_geometry(obj: dict, sidx: dict) -> tuple[Optional[int], Optional[dict], str]:
    """
    Return (page, bbox_in_mathpix_points, text_preview) for a DocObject.

    Geometry is the union of the regions of the mathpix_lines anchors the object
    realizes; the text preview joins those lines. Falls back to props['region']
    for images that only realize into the 'cdn' stream.
    """
    payload_of = sidx["payload"]
    order_of = sidx["order"]
    page: Optional[int] = obj.get("props", {}).get("page")
    bbox: Optional[dict] = None
    texts: list[str] = []

    for rz in obj.get("realizations", []):
        if rz.get("stream") != "mathpix_lines":
            continue
        anchors = order_of.get("mathpix_lines", [])
        start, end = rz.get("start"), rz.get("end")
        if start is None or end is None:
            continue
        try:
            i, j = anchors.index(start), anchors.index(end)
        except ValueError:
            continue
        if i > j:
            i, j = j, i
        for aid in anchors[i : j + 1]:
            p = payload_of.get(aid, {})
            box = _region_to_box(p.get("region") or {})
            bbox = _union(bbox, box)
            if page is None:
                page = p.get("_page")
            t = p.get("text") or p.get("text_display")
            if t:
                texts.append(t)

    if bbox is None:
        # image objects: region lives directly on props
        bbox = _region_to_box(obj.get("props", {}).get("region") or {})

    preview = " ".join(texts).strip()
    return page, bbox, preview


def reading_order(objects: list[dict]) -> list[dict]:
    """Reading order: flow_index when present, else (page, y-top)."""
    def key(o: dict):
        pr = o.get("props", {})
        fi = pr.get("flow_index")
        if fi is not None:
            return (0, fi, 0)
        return (1, pr.get("page") or 0, 0)

    flow = [o for o in objects if o["type"] not in ("Page", "Document", "Reference", "Citation")]
    return sorted(flow, key=key)


# ---------------------------------------------------------------------------
# Assemble the client-side element records
# ---------------------------------------------------------------------------

def _short_label(obj: dict, preview: str) -> str:
    t = obj["type"]
    pr = obj.get("props", {})
    if t == "Section":
        return pr.get("caption") or preview[:60] or "section"
    if t == "Equation":
        ref = pr.get("refnum")
        head = f"({ref}) " if ref else ""
        return head + (pr.get("latex") or preview[:40] or "equation")
    if t == "Formula":
        return pr.get("latex") or preview[:40] or "formula"
    if t in _IMAGEY:
        ref = pr.get("refnum")
        cap = pr.get("caption") or ""
        head = f"Fig {ref}" if ref else t
        return f"{head} — {cap[:48]}" if cap else head
    if t == "Table":
        return "table"
    if t == "Abstract":
        return "Abstract"
    return preview[:60] or t.lower()


def collect_elements(model: dict, sidx: dict) -> tuple[list[dict], list[dict]]:
    """Return (elements, pages_meta). Elements are the client records."""
    id_index = {o["id"]: o for o in model["objects"]}
    ro = reading_order(model["objects"])
    flow_rank = {o["id"]: i for i, o in enumerate(ro)}

    elements: list[dict] = []
    for obj in model["objects"]:
        if obj["type"] in ("Document", "Reference", "Citation"):
            continue
        page, bbox, preview = object_geometry(obj, sidx)
        pr = obj.get("props", {})
        rec: dict[str, Any] = {
            "id": obj["id"],
            "type": obj["type"],
            "page": page,
            "bbox": bbox,  # MathPix points
            "label": _short_label(obj, preview),
            "flow": flow_rank.get(obj["id"]),
            "realizations": [
                {"stream": r.get("stream"), "role": r.get("role")}
                for r in obj.get("realizations", [])
            ],
        }
        # type-specific payloads used by reflow + inspector
        if obj["type"] in ("Formula", "Equation"):
            rec["latex"] = pr.get("latex", "")
            # a numbered Equation is display math by definition; a Formula
            # follows its own display flag (inline vs block).
            rec["display"] = True if obj["type"] == "Equation" else bool(pr.get("display"))
            rec["refnum"] = pr.get("refnum")
            rec["cdn_url"] = pr.get("cdn_url") or ""
            rec["image_id"] = pr.get("image_id")
        if obj["type"] == "Section":
            rec["level"] = pr.get("level", 1)
            rec["caption"] = pr.get("caption", "")
        if obj["type"] == "Abstract":
            rec["text"] = pr.get("text", preview)
        if obj["type"] in _TEXTY and obj["type"] != "Abstract":
            rec["text"] = pr.get("text", preview)
        if obj["type"] in _IMAGEY:
            rec["caption"] = pr.get("caption", "")
            rec["refnum"] = pr.get("refnum")
            rec["cdn_url"] = pr.get("cdn_url") or pr.get("url") or ""
            rec["image_id"] = pr.get("image_id")
        if obj["type"] == "Table":
            rec["raw_text"] = pr.get("raw_text", preview)
        # a trimmed props dump for the inspector (skip flow bookkeeping)
        skip = {"prev_in_flow", "next_in_flow", "flow_index"}
        rec["props"] = {k: v for k, v in pr.items() if k not in skip}
        rec["preview"] = preview[:400]
        elements.append(rec)

    # alignments touching each object (cross-stream provenance links)
    align_by_obj: dict[str, int] = {}
    for al in model.get("alignments", []):
        for side in ("a", "b", "left", "right", "source", "target"):
            oid = al.get(side)
            if isinstance(oid, str) and oid in id_index:
                align_by_obj[oid] = align_by_obj.get(oid, 0) + 1
    for rec in elements:
        rec["n_align"] = align_by_obj.get(rec["id"], 0)

    pages_meta = []
    for pm in model["meta"]["pages"]:
        pages_meta.append(
            {
                "page": pm.get("page"),
                "pt_w": _int(pm.get("page_width")),
                "pt_h": _int(pm.get("page_height")),
            }
        )
    return elements, pages_meta


# ---------------------------------------------------------------------------
# Image sourcing
# ---------------------------------------------------------------------------

def prepare_pages(
    pages_meta: list[dict],
    *,
    mode: str,
    pages_dir: Optional[str],
    image_base: Optional[str],
    embed_dpi: int,
    src_dpi: int,
) -> dict:
    """
    Return {page_number: {"src": <url|data-uri>, "img_w":..., "img_h":...}}.
    For --embed, downscale the folder PNGs to embed_dpi JPEGs and inline them.
    """
    out: dict[int, dict] = {}
    for pm in pages_meta:
        n = pm["page"]
        if mode == "image-base":
            out[n] = {"src": f"{image_base.rstrip('/')}/pages/p{n}.png",
                      "img_w": None, "img_h": None}
            continue
        # both folder and embed need the on-disk PNG
        png = os.path.join(pages_dir, f"p{n}.png") if pages_dir else None
        if not png or not os.path.exists(png):
            out[n] = {"src": "", "img_w": None, "img_h": None}
            continue
        if mode == "pages-dir":
            # reference relatively; read dims for scaling
            try:
                from PIL import Image
                with Image.open(png) as im:
                    w, h = im.size
            except Exception:
                w = h = None
            out[n] = {"src": f"pages/p{n}.png", "img_w": w, "img_h": h}
        else:  # embed
            from PIL import Image
            with Image.open(png) as im:
                w0, h0 = im.size
                scale = embed_dpi / float(src_dpi)
                w, h = max(1, int(w0 * scale)), max(1, int(h0 * scale))
                im = im.convert("RGB").resize((w, h), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=72, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            out[n] = {"src": f"data:image/jpeg;base64,{b64}", "img_w": w, "img_h": h}
    return out


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_KATEX_CSS = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.css"
_KATEX_JS = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.js"

_FONT_MIME = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf"}


def vendor_katex(katex_dir: str) -> Optional[dict]:
    """
    Read a KaTeX dist folder and return {'css':..., 'js':...} with the fonts
    inlined into the CSS as data: URIs — so math renders with no network at all.
    Returns None if the folder isn't a KaTeX dist.
    """
    css_p = os.path.join(katex_dir, "katex.min.css")
    js_p = os.path.join(katex_dir, "katex.min.js")
    fonts_d = os.path.join(katex_dir, "fonts")
    if not (os.path.exists(css_p) and os.path.exists(js_p)):
        return None
    css = open(css_p, "r", encoding="utf-8").read()
    if os.path.isdir(fonts_d):
        cache: dict[str, str] = {}
        for fn in os.listdir(fonts_d):
            ext = os.path.splitext(fn)[1].lower()
            mime = _FONT_MIME.get(ext)
            if not mime:
                continue
            with open(os.path.join(fonts_d, fn), "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            cache[fn] = f"data:{mime};base64,{b64}"
        # rewrite url(fonts/NAME.ext) -> url(data:...)
        import re
        def repl(m):
            path = m.group(1).strip("'\"")
            name = os.path.basename(path)
            return f"url({cache[name]})" if name in cache else m.group(0)
        css = re.sub(r"url\(([^)]+)\)", repl, css)
    js = open(js_p, "r", encoding="utf-8").read()
    return {"css": css, "js": js}


def build_inspector_html(
    model: dict,
    *,
    pages: dict,
    title: str = "docinspect",
    image_mode: str = "embed",
    katex_inline: Optional[dict] = None,
) -> str:
    sidx = build_stream_index(model)
    elements, pages_meta = collect_elements(model, sidx)
    meta = model["meta"]

    payload = {
        "title": title,
        "bibkey": meta.get("bibkey", ""),
        "num_pages": meta.get("num_pages", len(pages_meta)),
        "image_mode": image_mode,
        "pages_meta": pages_meta,
        "pages": {str(k): v for k, v in pages.items()},
        "elements": elements,
    }
    data_json = json.dumps(payload).replace("</", "<\\/")

    counts: dict[str, int] = {}
    for e in elements:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    subtitle = " · ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))

    if katex_inline:
        katex_head = f"<style>{katex_inline['css']}</style>"
        katex_script = f"<script>{katex_inline['js']}</script>"
    else:
        katex_head = (f'<link rel="stylesheet" href="{_KATEX_CSS}" crossorigin="anonymous">')
        katex_script = (f'<script src="{_KATEX_JS}" crossorigin="anonymous" '
                        f'onerror="window.__noKatex=1"></script>')

    return _TEMPLATE.replace("__DATA__", data_json) \
                    .replace("__TITLE__", html.escape(title)) \
                    .replace("__SUBTITLE__", html.escape(subtitle)) \
                    .replace("__KATEX_HEAD__", katex_head) \
                    .replace("__KATEX_SCRIPT__", katex_script)


# The template is a single self-contained HTML doc. All UI is built client-side
# from the injected __DATA__ record so the same file works from a folder, a
# crop server, or fully inlined.
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · docinspect</title>
__KATEX_HEAD__
<style>
:root{
  --bg:#0f1216; --panel:#161b22; --panel2:#1b2027; --line:#2b333d;
  --ink:#d7dee8; --dim:#8b97a6; --faint:#5b6675;
  --accent:#5cc8ff;         /* inspect cyan */
  --accent2:#ffb454;        /* figure amber */
  --sel:#264056; --hl:rgba(92,200,255,.16);
  --mono:"SFMono-Regular",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:13px/1.5 var(--sans);overflow:hidden}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}

/* ---- top bar ---- */
.topbar{height:46px;display:flex;align-items:center;gap:14px;padding:0 14px;
  background:var(--panel);border-bottom:1px solid var(--line)}
.brand{font-weight:700;letter-spacing:.02em}
.brand .k{color:var(--accent)}
.crumb{color:var(--dim);font-family:var(--mono);font-size:12px}
.crumb b{color:var(--ink)}
.spacer{flex:1}
.seg{display:flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.seg button{padding:6px 12px;color:var(--dim);font-size:12px}
.seg button.on{background:var(--panel2);color:var(--accent)}
.tool{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:12px}
.tool select{background:var(--panel2);color:var(--ink);border:1px solid var(--line);
  border-radius:6px;padding:4px 6px;font:inherit}
.inspectbtn{border:1px solid var(--line);border-radius:7px;padding:6px 10px;color:var(--dim);
  display:flex;align-items:center;gap:6px}
.inspectbtn.on{color:var(--accent);border-color:var(--accent)}

/* ---- layout ---- */
.wrap{display:flex;height:calc(100% - 46px)}
.stagewrap{flex:1;min-width:0;overflow:auto;background:
  repeating-conic-gradient(#12161b 0% 25%, #10141a 0% 50%) 0 0/22px 22px;
  padding:26px;display:flex;justify-content:center}
.side{width:430px;min-width:300px;max-width:60%;display:flex;flex-direction:column;
  background:var(--panel);border-left:1px solid var(--line)}
.dragbar{width:6px;cursor:col-resize;background:transparent}
.dragbar:hover{background:var(--line)}

/* ---- page stage ---- */
.stage{position:relative;box-shadow:0 6px 40px rgba(0,0,0,.6);background:#fff;
  align-self:flex-start}
.stage img{display:block;width:100%;height:auto}
.overlay{position:absolute;inset:0;pointer-events:none}
.box{position:absolute;pointer-events:auto;border:1px solid transparent;border-radius:2px}
.box:hover{background:var(--hl);border-color:var(--accent)}
.box.sel{background:var(--hl);border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.box.hl{background:var(--hl);border-color:var(--accent)}
.box[data-cat="image"]:hover,.box[data-cat="image"].sel{border-color:var(--accent2);
  box-shadow:0 0 0 1px var(--accent2)}
.tag{position:absolute;top:-18px;left:-1px;font:10px/1 var(--mono);white-space:nowrap;
  background:var(--accent);color:#04222f;padding:2px 5px;border-radius:3px 3px 3px 0;
  opacity:0;transition:opacity .08s}
.box:hover .tag,.box.sel .tag{opacity:1}
.box[data-cat="image"] .tag{background:var(--accent2);color:#3a2600}

/* ---- reflow ---- */
.reflow{max-width:820px;background:#fbfbf7;color:#181a1f;border-radius:4px;
  padding:56px 64px;box-shadow:0 6px 40px rgba(0,0,0,.6);
  font:16px/1.6 Georgia,"Times New Roman",serif;align-self:flex-start}
.reflow h1{font-size:24px;margin:.2em 0 .6em}
.reflow h2{font-size:19px;margin:1.3em 0 .4em;font-family:var(--sans);font-weight:700}
.reflow h3{font-size:16px;margin:1.1em 0 .3em;font-family:var(--sans);font-weight:700}
.reflow p{margin:.55em 0;text-align:justify}
.reflow .abstract{font-size:14px;background:#f0efe6;border-left:3px solid var(--accent2);
  padding:12px 16px;margin:1em 0}
.reflow .abstract b{font-family:var(--sans);display:block;margin-bottom:4px}
.reflow figure{margin:1.4em 0;text-align:center}
.reflow figure img{max-width:100%;border:1px solid #ddd;background:#fff}
.reflow figcaption{font:13px/1.4 var(--sans);color:#555;margin-top:6px}
.reflow .eqblock{margin:1em 0;text-align:center;overflow-x:auto}
.reflow .eqblock.numbered{position:relative;display:flex;align-items:center;justify-content:center}
.reflow .eqblock.numbered .eqmath{flex:1;overflow-x:auto}
.reflow .eqblock.numbered .eqnum{flex:none;font:14px/1 var(--sans);color:#444;padding-left:12px}
.reflow table{border-collapse:collapse;margin:1em auto;font:13px/1.4 var(--sans)}
.reflow td,.reflow th{border:1px solid #ccc;padding:4px 8px}
.reflow pre.table{font:12px/1.4 var(--mono);background:#f0efe6;padding:10px;overflow-x:auto;
  text-align:left}
.reflow [data-obj]{cursor:pointer;transition:background .1s;border-radius:2px}
.reflow [data-obj]:hover{background:rgba(92,150,200,.14)}
.reflow .reflow-el.hl{background:rgba(92,150,200,.14)}
.reflow [data-obj].sel{background:rgba(92,150,200,.22);box-shadow:0 0 0 2px rgba(92,150,200,.5)}
.katex-missing{font-family:var(--mono);font-size:.85em;background:#eee;padding:1px 4px;border-radius:3px}

/* ---- sidebar: tree ---- */
.side h4{margin:0;padding:9px 12px;font:11px/1 var(--sans);letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--line);
  display:flex;align-items:center;gap:8px}
.side h4 .count{color:var(--dim);font-family:var(--mono)}
.treewrap{flex:1;overflow:auto;padding:4px 0}
.filterbar{padding:6px 10px;border-bottom:1px solid var(--line)}
.filterbar input{width:100%;background:var(--panel2);border:1px solid var(--line);
  border-radius:6px;color:var(--ink);padding:5px 8px;font:12px var(--mono)}
.node{user-select:none}
.row{display:flex;align-items:center;gap:6px;padding:2px 10px 2px 0;cursor:pointer;
  white-space:nowrap;overflow:hidden}
.row:hover{background:var(--panel2)}
.row.sel{background:var(--sel)}
.row.hl{background:var(--panel2)}
.tw{width:14px;text-align:center;color:var(--faint);flex:none}
.badge{font:9px/1 var(--mono);padding:2px 4px;border-radius:3px;flex:none;
  background:#233; color:var(--dim);text-transform:uppercase;letter-spacing:.03em}
.b-Section{background:#1d3a2b;color:#7fe0a5}
.b-Formula{background:#3a2b1d;color:#ffcf8f}
.b-Equation{background:#3a2416;color:#ffbf6b}
.b-Picture,.b-Diagram,.b-Chart{background:#402a17;color:var(--accent2)}
.b-Table{background:#2a2340;color:#c3a7ff}
.b-Page{background:#1b2733;color:var(--accent)}
.b-Abstract{background:#3a1d33;color:#ff9fd6}
.lbl{overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.row.dim .lbl{color:var(--dim)}
.lblmono{font-family:var(--mono);font-size:11.5px}

/* ---- sidebar: inspector ---- */
.inspector{height:44%;min-height:150px;border-top:1px solid var(--line);
  display:flex;flex-direction:column;background:var(--panel2)}
.insphead{padding:8px 12px;border-bottom:1px solid var(--line);display:flex;
  align-items:center;gap:8px}
.insphead .t{font-weight:700}
.inspbody{overflow:auto;padding:10px 12px;font-size:12.5px}
.empty{color:var(--faint);padding:24px 12px;text-align:center}
.kv{display:grid;grid-template-columns:96px 1fr;gap:2px 10px;margin:2px 0}
.kv .k{color:var(--dim);font-family:var(--mono);font-size:11px}
.kv .v{font-family:var(--mono);font-size:11.5px;word-break:break-word}
.sec{margin:12px 0 4px;font:10px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;
  color:var(--faint)}
.chip{display:inline-block;font:10px/1 var(--mono);background:#233;color:var(--dim);
  border:1px solid var(--line);border-radius:4px;padding:3px 6px;margin:2px 3px 0 0}
.eqrender{background:#0c0f13;border:1px solid var(--line);border-radius:6px;padding:10px;
  margin:6px 0;overflow-x:auto;color:#eee}
.latexsrc{font-family:var(--mono);font-size:11px;color:var(--accent);background:#0c0f13;
  border:1px solid var(--line);border-radius:6px;padding:8px;white-space:pre-wrap;word-break:break-word}
.cropimg{max-width:100%;border:1px solid var(--line);border-radius:4px;background:#fff;margin-top:6px}
.txtprev{color:var(--dim);white-space:pre-wrap;max-height:160px;overflow:auto;
  border-left:2px solid var(--line);padding-left:8px}
.jump{margin-left:auto;font-size:11px;color:var(--accent)}
.hint{padding:6px 12px;color:var(--faint);font-size:11px;border-top:1px solid var(--line)}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">doc<span class="k">inspect</span></div>
  <div class="crumb"><b id="cb-key"></b> · <span id="cb-sub"></span></div>
  <div class="spacer"></div>
  <button class="inspectbtn" id="inspectToggle" title="Pick an element on the page">
    <span>⌖</span><span>Inspect</span>
  </button>
  <div class="seg" id="viewSeg">
    <button data-v="page" class="on">Page</button>
    <button data-v="reflow">Reflow</button>
  </div>
  <div class="tool">Page
    <select id="pageSel"></select>
  </div>
</div>

<div class="wrap">
  <div class="stagewrap" id="stagewrap"></div>
  <div class="dragbar" id="dragbar"></div>
  <aside class="side">
    <h4>Elements <span class="count" id="elCount"></span></h4>
    <div class="filterbar"><input id="filter" placeholder="filter by type or text…"></div>
    <div class="treewrap" id="tree"></div>
    <div class="inspector">
      <div class="insphead"><span class="badge" id="ihBadge">—</span>
        <span class="t" id="ihTitle">Inspector</span>
        <button class="jump" id="jumpBtn" style="display:none">reveal ▸</button>
      </div>
      <div class="inspbody" id="inspBody"><div class="empty">Select an element to inspect it.</div></div>
    </div>
  </aside>
</div>

__KATEX_SCRIPT__
<script>
const DATA = __DATA__;
const IMG = {}; DATA.pages && Object.entries(DATA.pages).forEach(([k,v])=>IMG[k]=v);
const PMETA = {}; DATA.pages_meta.forEach(p=>PMETA[p.page]=p);
const EL = DATA.elements;
const byId = {}; EL.forEach(e=>byId[e.id]=e);
const IMAGE_CATS = new Set(["Picture","Diagram","Chart"]);
let curPage = (DATA.pages_meta[0]||{}).page || 1;
let curView = "page";
let selId = null, inspectMode=false;

/* ---------- KaTeX helper ---------- */
function renderMath(tex, display, into){
  if(window.__noKatex || !window.katex){
    into.innerHTML = '<span class="katex-missing">'+esc(tex)+'</span>'; return;
  }
  try{ window.katex.render(tex, into, {displayMode:!!display, throwOnError:false}); }
  catch(e){ into.innerHTML = '<span class="katex-missing">'+esc(tex)+'</span>'; }
}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

/* ---------- page geometry ---------- */
function pageScale(pn){
  // pixels-per-point for the DISPLAYED image; overlay uses % so we only need ratio.
  const pm = PMETA[pn]||{}; const im = IMG[pn]||{};
  return {ptW: pm.pt_w, ptH: pm.pt_h, imgW: im.img_w, imgH: im.img_h, src: im.src};
}

/* ================= element hook contract =================================
   The thing an arXiv/LaTeXML render can't give us: every visible element —
   a reflow node, a page-overlay box, a tree row — carries a LIVE hook back
   to its docmodel object id, so a debugger / drillui / TiddlyWiki can
   address, highlight and inspect any of them. One index, one event bus. */
const NODES = {};                 // obj id -> [dom nodes] across all surfaces
const LISTEN = {select:[], hover:[]};
function emit(ev, ...a){ (LISTEN[ev]||[]).forEach(f=>{try{f(...a);}catch(_){} }); }
function nodesOf(id){ return (NODES[id]||[]).filter(n=>n.isConnected); }
function attachHooks(node, e){
  node.dataset.objId=e.id; node.dataset.objType=e.type; node.classList.add('hooked');
  node.addEventListener('mouseenter',()=>emit('hover',e.id,true));
  node.addEventListener('mouseleave',()=>emit('hover',e.id,false));
  node.addEventListener('click',ev=>{ev.stopPropagation();emit('select',e.id);});
  (NODES[e.id]=NODES[e.id]||[]).push(node);
  if(e.id===selId) node.classList.add('sel');
  return node;
}

/* ================= renderer registry (one module per object type) =========
   Mirrors src/docmodel/modules/. To support a new object type, register a
   module {type, render(e)->node, detail(e)->html}. The base '*' module
   renders a plain paragraph — the project's starting point — and every other
   type layers on independently. */
const REG = {};
function register(mod){ (Array.isArray(mod.type)?mod.type:[mod.type]).forEach(t=>REG[t]=mod); }
function rendererFor(t){ return REG[t] || REG['*']; }

// helpers shared by modules
function el(tag,cls){ const n=document.createElement(tag); if(cls)n.className=cls; return n; }
function sec(t){ return '<div class="sec">'+esc(t)+'</div>'; }
function kv(k,v){ return '<div class="kv"><span class="k">'+esc(k)+'</span><span class="v">'+esc(v)+'</span></div>'; }
function txt(s){ return '<div class="txtprev">'+esc(s||'')+'</div>'; }
function eqBlock(latex){ return sec('rendered')+'<div class="eqrender" data-eq="'+esc(latex||'')+'"></div>'; }
function latexSrc(latex){ return sec('latex')+'<div class="latexsrc">'+esc(latex||'')+'</div>'; }
function cropTag(){ return '<img class="cropimg" data-crop="1">'; }
function fillDeferred(host, e){   // resolve data-eq / data-crop placeholders post-insert
  host.querySelectorAll('[data-eq]').forEach(n=>renderMath(n.getAttribute('data-eq')||'',true,n));
  host.querySelectorAll('[data-crop]').forEach(n=>{ if(DATA.image_mode==='embed') cropFromPage(e,n); else if(e.cdn_url) n.src=e.cdn_url; });
}

function cropFromPage(el0, imgEl){          // client-side figure crop from the page image
  const g = pageScale(el0.page); if(!g.src) return;
  const im = new Image();
  im.onload=()=>{ const sx=im.naturalWidth/g.ptW, sy=im.naturalHeight/g.ptH;
    const b=el0.bbox||regionOf(el0); if(!b){ imgEl.src=g.src; return; }
    const c=document.createElement('canvas'); c.width=Math.max(1,b.w*sx); c.height=Math.max(1,b.h*sy);
    c.getContext('2d').drawImage(im, b.x*sx,b.y*sy,b.w*sx,b.h*sy, 0,0,c.width,c.height);
    imgEl.src=c.toDataURL('image/png'); };
  im.src=g.src;
}
function regionOf(e){ const r=(e.props||{}).region; if(!r)return null;
  return {x:+r.top_left_x,y:+r.top_left_y,w:+r.width,h:+r.height}; }

// ---- base: Paragraph / ListItem / Footnote / Sidenote / generic prose ----
register({ type:'*',
  render(e){ const n=el(e.type==='Paragraph'?'p':'div'); n.textContent=e.text||e.preview||''; return n; },
  detail(e){ return sec('text')+txt(e.text||e.preview); } });

register({ type:'Section',
  render(e){ const lv=Math.min(3,Math.max(1,e.level||1)); const n=el(lv===1?'h2':'h3'); n.textContent=e.caption||e.label; return n; },
  detail(e){ return kv('level',e.level)+sec('caption')+txt(e.caption); } });

register({ type:'Abstract',
  render(e){ const n=el('div','abstract'); n.appendChild(el('b')).textContent='Abstract';
    n.appendChild(document.createTextNode(e.text||e.preview||'')); return n; },
  detail(e){ return sec('text')+txt(e.text||e.preview); } });

register({ type:'Equation',       // numbered display equation (arXiv-style)
  render(e){ const n=el('div','eqblock numbered'); const m=el('div','eqmath'); renderMath(e.latex||'',true,m); n.appendChild(m);
    if(e.refnum!=null){ const t=el('span','eqnum'); t.textContent='('+e.refnum+')'; n.appendChild(t);} return n; },
  detail(e){ let h=''; if(e.refnum!=null)h+=kv('equation','('+e.refnum+')');
    h+=eqBlock(e.latex)+latexSrc(e.latex)+kv('display','block');
    if(e.cdn_url)h+=sec('mathpix crop')+cropTag()+'<div class="latexsrc" style="margin-top:6px">'+esc(e.cdn_url)+'</div>'; return h; } });

register({ type:'Formula',        // inline or block math per its display flag
  render(e){ if(e.display){ const n=el('div','eqblock'); renderMath(e.latex||'',true,n); return n; }
    const s=el('span'); renderMath(e.latex||'',false,s); s.style.margin='0 3px'; return s; },
  detail(e){ let h=eqBlock(e.latex)+latexSrc(e.latex)+kv('display',e.display?'block':'inline');
    if(e.cdn_url)h+=sec('mathpix crop')+cropTag(); return h; } });

register({ type:['Picture','Diagram','Chart'],
  render(e){ const fig=el('figure'); const img=el('img');
    if(DATA.image_mode==='embed') cropFromPage(e,img); else if(e.cdn_url) img.src=e.cdn_url; fig.appendChild(img);
    if(e.caption){ const c=el('figcaption'); c.textContent=(e.refnum?('Figure '+e.refnum+'. '):'')+e.caption; fig.appendChild(c);} return fig; },
  detail(e){ let h=''; if(e.caption)h+=sec('caption')+txt(e.caption);
    if(e.refnum!=null)h+=kv('figure',e.refnum); if(e.image_id)h+=kv('image_id',e.image_id);
    h+=sec('crop')+cropTag(); if(e.cdn_url)h+='<div class="latexsrc" style="margin-top:6px">'+esc(e.cdn_url)+'</div>'; return h; } });

register({ type:'Table',
  render(e){ const n=el('pre','table'); n.textContent=e.raw_text||e.preview||''; return n; },
  detail(e){ return sec('raw text')+txt(e.raw_text||e.preview); } });

/* ---------- STAGE: page view (boxes are hooked elements too) ---------- */
function renderPage(){
  const wrap=document.getElementById('stagewrap'); wrap.innerHTML='';
  const g=pageScale(curPage); const stage=el('div','stage');
  if(!g.src){ stage.innerHTML='<div style="padding:40px;color:#888;font:13px monospace">No image for page '+curPage+'</div>'; wrap.appendChild(stage); return; }
  const img=el('img'); img.src=g.src; stage.appendChild(img);
  const ov=el('div','overlay'); stage.appendChild(ov);
  const W=g.ptW, H=g.ptH;
  EL.filter(e=>e.page===curPage && e.bbox).forEach(e=>{
    const d=el('div','box'); d.dataset.cat=IMAGE_CATS.has(e.type)?'image':'text';
    const b=e.bbox;
    d.style.left=(100*b.x/W)+'%'; d.style.top=(100*b.y/H)+'%';
    d.style.width=(100*b.w/W)+'%'; d.style.height=(100*b.h/H)+'%';
    const tag=el('div','tag'); tag.textContent=e.type+(e.refnum?(' '+e.refnum):''); d.appendChild(tag);
    attachHooks(d,e); ov.appendChild(d);
  });
  wrap.appendChild(stage);
}

/* ---------- STAGE: reflow view — page-windowed virtualization ------------
   The flow (reading order) is chunked into page-aligned windows; only chunks
   near the viewport are hydrated (DOM built, KaTeX rendered, figures cropped).
   Far chunks collapse back to a measured-height spacer, so a 500-page document
   keeps a bounded DOM. Page is the window key — reliable from MathPix + the
   pdfminer.six merge. */
const MAX_CHUNK=40, KEEP=6;          // elements per chunk; hydrated window each side
let CHUNKS=[], CHUNK_OF={}, RIO=null, visChunks=new Set();

function buildChunks(){
  CHUNKS=[]; CHUNK_OF={};
  const flow=EL.filter(e=>e.flow!=null).sort((a,b)=>a.flow-b.flow);
  let cur=null;
  flow.forEach(e=>{
    const pageBreak = cur && e.page!=null && e.page!==cur.p1;   // break at page boundary
    if(!cur || cur.els.length>=MAX_CHUNK || pageBreak){ cur={p0:e.page,p1:e.page,els:[],h:0}; CHUNKS.push(cur); }
    cur.els.push(e); if(e.page!=null) cur.p1=e.page;
    CHUNK_OF[e.id]=CHUNKS.length-1;
  });
}
function chunkLabel(ch){ return ch.p0==null?'':(ch.p0===ch.p1?('page '+ch.p0):('pages '+ch.p0+'–'+ch.p1)); }
function estimateH(ch){ return 30*ch.els.length+30; }

function renderReflow(){
  const wrap=document.getElementById('stagewrap'); wrap.innerHTML='';
  const doc=el('div','reflow'); buildChunks(); visChunks.clear();
  if(RIO) RIO.disconnect();
  RIO=new IntersectionObserver(onReflowIO,{root:wrap,rootMargin:'1400px 0px'});
  CHUNKS.forEach((ch,i)=>{
    const s=el('div','chunk'); s.dataset.chunk=i;
    if(ch.p0!=null){ const lab=el('div','pagebreak'); lab.textContent=chunkLabel(ch); s.appendChild(lab); }
    s.style.minHeight=(ch.h||estimateH(ch))+'px';
    ch.node=s; ch.hydrated=false; doc.appendChild(s); RIO.observe(s);
  });
  wrap.appendChild(doc);
}
function hydrateChunk(i){
  const ch=CHUNKS[i]; if(!ch||ch.hydrated) return; ch.hydrated=true;
  const frag=document.createDocumentFragment();
  ch.els.forEach(e=>{ const node=rendererFor(e.type).render(e); if(!node)return;
    node.classList.add('reflow-el'); attachHooks(node,e); frag.appendChild(node); });
  ch.node.appendChild(frag); ch.node.style.minHeight=''; ch.h=ch.node.offsetHeight;
}
function dehydrateChunk(i){
  const ch=CHUNKS[i]; if(!ch||!ch.hydrated) return;
  if(CHUNKS.length<=2*KEEP+2) return;                 // small docs: keep everything live
  ch.h=ch.node.offsetHeight;
  ch.els.forEach(e=>{ NODES[e.id]=(NODES[e.id]||[]).filter(n=>!ch.node.contains(n)); });
  ch.node.innerHTML=''; ch.hydrated=false;
  if(ch.p0!=null){ const lab=el('div','pagebreak'); lab.textContent=chunkLabel(ch); ch.node.appendChild(lab); }
  ch.node.style.minHeight=ch.h+'px';
}
function onReflowIO(entries){
  entries.forEach(en=>{ const i=+en.target.dataset.chunk;
    if(en.isIntersecting){ visChunks.add(i); hydrateChunk(i); } else visChunks.delete(i); });
  if(!visChunks.size) return;
  const lo=Math.min(...visChunks)-KEEP, hi=Math.max(...visChunks)+KEEP;
  CHUNKS.forEach((ch,i)=>{ if(ch.hydrated && (i<lo||i>hi)) dehydrateChunk(i); });
}

/* ---------- TREE — lazy children, auto-collapse for long documents ---------- */
const TREE_EAGER=20;                 // pages: below this, expand all; above, collapse
let PAGE_NODE={};
function buildTree(filter){
  const host=document.getElementById('tree'); host.innerHTML=''; PAGE_NODE={};
  for(const id in NODES){ NODES[id]=NODES[id].filter(n=>!n.classList.contains('row')); }
  const f=(filter||'').toLowerCase();
  const eagerAll = DATA.num_pages<=TREE_EAGER || !!f;
  DATA.pages_meta.map(p=>p.page).forEach(pn=>{
    const kids=EL.filter(e=>e.page===pn && e.type!=='Page' &&
      (!f || e.type.toLowerCase().includes(f) || (e.label||'').toLowerCase().includes(f)));
    if(f && kids.length===0) return;
    const pnode=el('div','node'); const prow=el('div','row');
    prow.innerHTML='<span class="tw"></span><span class="badge b-Page">Page</span>'+
      '<span class="lbl lblmono">'+pn+' · '+kids.length+' el</span>';
    const cont=el('div'); cont.style.paddingLeft='16px';
    let built=false;
    function buildKids(){ if(built)return; built=true;
      kids.sort((a,b)=>(a.flow??1e9)-(b.flow??1e9)).forEach(e=>{
        const r=el('div','row'); const mono=e.type==='Formula'?' lblmono':'';
        r.innerHTML='<span class="tw"></span><span class="badge b-'+e.type+'">'+e.type.slice(0,4)+'</span>'+
          '<span class="lbl'+mono+'">'+esc(e.label||'')+'</span>';
        attachHooks(r,e); cont.appendChild(r); }); }
    const tw=prow.querySelector('.tw'); let open=false;
    function setOpen(o){ open=o; if(open) buildKids(); cont.style.display=open?'':'none'; tw.textContent=open?'▾':'▸'; }
    tw.addEventListener('click',ev=>{ev.stopPropagation(); setOpen(!open);});
    prow.addEventListener('click',()=>{curPage=pn;syncPageSel();refreshStage();});
    pnode.appendChild(prow); pnode.appendChild(cont); host.appendChild(pnode);
    PAGE_NODE[pn]={setOpen}; setOpen(eagerAll);
  });
}
function revealInTree(id){ const e=byId[id]; if(!e||e.page==null)return; const p=PAGE_NODE[e.page]; if(p)p.setOpen(true); }

/* ---------- bus: one hover + one select handler drive every surface ---------- */
function onHover(id,on){ nodesOf(id).forEach(n=>n.classList.toggle('hl', on)); }
function onSelect(id){
  const e=byId[id]; if(!e) return; selId=id;
  if(e.page && e.page!==curPage && curView==='page'){ curPage=e.page; syncPageSel(); refreshStage(); }
  if(curView==='reflow' && CHUNK_OF[id]!=null) hydrateChunk(CHUNK_OF[id]);  // ensure the node exists
  revealInTree(id);                                                          // build+expand its tree page
  document.querySelectorAll('.sel').forEach(n=>{ if((n.dataset.objId)!==id) n.classList.remove('sel'); });
  nodesOf(id).forEach(n=>n.classList.add('sel'));
  const ns=nodesOf(id);
  const box=ns.find(n=>n.classList.contains('box')); if(box) box.scrollIntoView({block:'center',inline:'center'});
  const rn=ns.find(n=>n.classList.contains('reflow-el')); if(rn && curView==='reflow') rn.scrollIntoView({block:'center'});
  const row=ns.find(n=>n.classList.contains('row')); if(row) row.scrollIntoView({block:'nearest'});
  renderInspector(e);
}

LISTEN.hover.push(onHover); LISTEN.select.push(onSelect);
function select(id){ emit('select',id); }           // back-compat wrapper

/* ---------- public API: address any element like a debugger ---------- */
window.docinspect = {
  version:'1', data:DATA, elements:EL, byId,
  select:(id)=>emit('select',id),
  highlight:(id,on=true)=>onHover(id,on),
  nodes:nodesOf,
  on:(ev,cb)=>{ (LISTEN[ev]=LISTEN[ev]||[]).push(cb); },
  register, rendererFor,
};

/* ---------- INSPECTOR (detail delegated to the type's module) ---------- */
function renderInspector(e){
  const badge=document.getElementById('ihBadge'); badge.textContent=e.type; badge.className='badge b-'+e.type;
  document.getElementById('ihTitle').textContent=e.label||e.type;
  const jb=document.getElementById('jumpBtn'); jb.style.display='';
  jb.onclick=()=>{ if(curView!=='page') setView('page'); curPage=e.page; syncPageSel(); refreshStage(); setTimeout(()=>select(e.id),0); };
  const b=e.bbox, pm=PMETA[e.page]||{}, g=pageScale(e.page);
  let px=''; if(b && g.imgW && pm.pt_w){ const s=g.imgW/pm.pt_w; px=' → '+Math.round(b.w*s)+'×'+Math.round(b.h*s)+' px @img'; }
  let h=kv('id',e.id)+kv('type',e.type)+kv('page',e.page);
  if(b) h+='<div class="kv"><span class="k">region pt</span><span class="v">x '+b.x+' · y '+b.y+' · w '+b.w+' · h '+b.h+px+'</span></div>';
  const body=document.getElementById('inspBody');
  body.innerHTML=h+rendererFor(e.type).detail(e)+provenance(e);
  fillDeferred(body, e);
}
function provenance(e){
  let h=sec('realizations')+'<div>';
  (e.realizations||[]).forEach(r=>{ h+='<span class="chip">'+esc(r.stream)+(r.role?(' · '+r.role):'')+'</span>'; });
  h+='</div>';
  if(e.n_align) h+=sec('alignments')+'<div><span class="chip">'+e.n_align+' cross-stream links</span></div>';
  const shown=new Set(['page','region','latex','display','caption','refnum','cdn_url','url','image_id','raw_text','text','level','bibkey']);
  const extra=Object.entries(e.props||{}).filter(([k,v])=>!shown.has(k)&&v!=null&&v!==''&&typeof v!=='object');
  if(extra.length){ h+=sec('props'); extra.forEach(([k,v])=>{ h+=kv(k,v); }); }
  return h;
}


/* ---------- view / page controls ---------- */
function setView(v){ curView=v;
  document.querySelectorAll('#viewSeg button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  document.querySelector('.tool').style.opacity = v==='page'?1:.4;
  refreshStage();
}
function refreshStage(){
  // drop stage nodes from the hook index before re-rendering (tree persists)
  for(const id in NODES){ NODES[id]=NODES[id].filter(n=>!n.classList.contains('box')&&!n.classList.contains('reflow-el')); }
  curView==='page'?renderPage():renderReflow();
}
function syncPageSel(){ document.getElementById('pageSel').value=curPage; }

/* ---------- init ---------- */
function init(){
  document.getElementById('cb-key').textContent=DATA.bibkey||DATA.title;
  document.getElementById('cb-sub').textContent=DATA.__SUB__||'';
  document.getElementById('elCount').textContent=EL.filter(e=>e.type!=='Page').length;
  const sel=document.getElementById('pageSel');
  DATA.pages_meta.forEach(p=>{const o=document.createElement('option');o.value=p.page;o.textContent='p'+p.page;sel.appendChild(o);});
  sel.value=curPage;
  sel.addEventListener('change',()=>{curPage=+sel.value;refreshStage();});
  document.querySelectorAll('#viewSeg button').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.v)));
  document.getElementById('filter').addEventListener('input',ev=>buildTree(ev.target.value));
  document.getElementById('inspectToggle').addEventListener('click',function(){
    inspectMode=!inspectMode; this.classList.toggle('on',inspectMode);
    document.getElementById('stagewrap').style.cursor=inspectMode?'crosshair':'';
  });
  // resizer
  const bar=document.getElementById('dragbar'), side=document.querySelector('.side');
  let drag=false; bar.addEventListener('mousedown',()=>{drag=true;document.body.style.userSelect='none';});
  window.addEventListener('mouseup',()=>{drag=false;document.body.style.userSelect='';});
  window.addEventListener('mousemove',e=>{ if(!drag)return;
    const w=Math.min(window.innerWidth*0.6,Math.max(300,window.innerWidth-e.clientX));
    side.style.width=w+'px'; });
  buildTree(''); renderPage();
}
DATA.__SUB__="__SUBTITLE__";
init();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_from_paths(
    model_path: str,
    *,
    out: Optional[str] = None,
    tiddlers: Optional[str] = None,
    pages_dir: Optional[str] = None,
    image_base: Optional[str] = None,
    embed: bool = False,
    embed_dpi: int = 120,
    src_dpi: int = 600,
    title: Optional[str] = None,
    katex_dir: Optional[str] = None,
) -> tuple[str, int, int, str]:
    """Reusable core behind the CLI and `pdfdrill inspect`: load the model,
    resolve the image source, and return (html, n_pages, n_elements, mode).
    When `out` is given the html is also written there. No image source and no
    sibling viewer/pages → falls back to `embed` with missing PNGs (boxes-only,
    the tree/inspector still work), so it never hard-fails on a headless model."""
    model = load_json(model_path)
    _, pages_meta = collect_elements(model, build_stream_index(model))

    if image_base:
        mode = "image-base"
    elif embed:
        mode = "embed"
    elif pages_dir:
        mode = "pages-dir"
    else:
        guess = os.path.join(os.path.dirname(model_path), "viewer", "pages")
        if os.path.isdir(guess):
            pages_dir, mode = guess, "pages-dir"
        else:
            pages_dir, mode = guess, "embed"   # boxes-only if the folder is absent

    if mode in ("embed", "pages-dir") and not pages_dir:
        pages_dir = os.path.join(os.path.dirname(model_path), "viewer", "pages")

    pages = prepare_pages(
        pages_meta, mode=mode, pages_dir=pages_dir, image_base=image_base,
        embed_dpi=embed_dpi, src_dpi=src_dpi,
    )

    katex_inline = vendor_katex(katex_dir) if katex_dir else None

    ttl = title or model["meta"].get("bibkey", "docinspect")
    html_doc = build_inspector_html(model, pages=pages, title=ttl, image_mode=mode,
                                    katex_inline=katex_inline)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
    n_el = sum(1 for o in model["objects"] if o["type"] != "Page")
    return html_doc, len(pages), n_el, mode


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build a DevTools-style docmodel inspector HTML.")
    ap.add_argument("model", help="path to model.docmodel.json")
    ap.add_argument("--tiddlers", help="optional tiddlers json (rendered content)")
    ap.add_argument("--pages-dir", help="folder of 600-DPI page images p{N}.png")
    ap.add_argument("--image-base", help="mathpix_server.py origin, e.g. http://localhost:8000")
    ap.add_argument("--embed", action="store_true", help="inline downscaled page images (self-contained)")
    ap.add_argument("--embed-dpi", type=int, default=120, help="target DPI for inlined pages (default 120)")
    ap.add_argument("--src-dpi", type=int, default=600, help="DPI the page PNGs were rendered at (default 600)")
    ap.add_argument("-o", "--out", help="output html path")
    ap.add_argument("--title", help="title (defaults to bibkey)")
    ap.add_argument("--vendor-katex", metavar="DIR",
                    help="a KaTeX dist folder (katex.min.js/.css + fonts/) to inline "
                         "for fully offline math; default uses the cdnjs CDN")
    args = ap.parse_args(argv)

    # keep the CLI's original "no image source" hard error (build_from_paths is
    # lenient — it falls back to boxes-only — but the CLI historically refused).
    if not (args.image_base or args.embed or args.pages_dir):
        guess = os.path.join(os.path.dirname(args.model), "viewer", "pages")
        if not os.path.isdir(guess):
            print("No image source: pass --pages-dir, --image-base, or --embed.",
                  file=sys.stderr)
            return 2

    out = args.out or (os.path.splitext(args.model)[0] + ".inspect.html")
    doc, n_pages, n_el, mode = build_from_paths(
        args.model, out=out, tiddlers=args.tiddlers, pages_dir=args.pages_dir,
        image_base=args.image_base, embed=args.embed, embed_dpi=args.embed_dpi,
        src_dpi=args.src_dpi, title=args.title, katex_dir=args.vendor_katex)
    print(f"Wrote {out} ({len(doc)//1024} KB) — {n_el} elements, "
          f"{n_pages} pages, image mode: {mode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
