"""
DistillReaderProjector — a distill-structured reading view (<bibkey>.distill.html).

The document skeleton of an Anthropic/Distill v2 article (named-column CSS
grid, runtime TOC from the heading flow, late-bound `??` figure references,
hover citations and footnotes), rebuilt as a pdfdrill projection: one
self-contained file, no template JS, KaTeX from data-latex (house pattern),
tiddler-scheme anchors on every addressable unit.

params: ``embed`` (default False) — base64-inline every CDN crop.
"""
from __future__ import annotations

import html
import re

from docmodel.core import Document, DocObject
from docmodel.mathpix import page_url
from ..base import BaseProjector
from ..transclusion_render import TW_TRANSCLUSION, num_from_title
from .common import embed_image, flow_ordered_content

_KV = "0.16.11"
_NULLISH = {"", "null", "none"}


def _empty(latex) -> bool:
    return latex is None or str(latex).strip().lower() in _NULLISH


def _math(latex: str, display: bool) -> str:
    return (f'<span class="math-render" data-latex="{html.escape(str(latex), quote=True)}" '
            f'data-display="{"true" if display else "false"}"></span>')


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "sec"


_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
<style>
/* HARD DARK by default, regardless of the system setting. `color-scheme:dark`
   tells the UA + DarkReader it's already dark, so DarkReader leaves it alone. */
:root{{
  color-scheme:dark;
  --ink:#e6e6e6; --muted:#a2a8ae; --faint:#70757b;
  --line:rgba(255,255,255,.14); --accent:#5ab0d0; --wash:hsla(210,25%,80%,.05);
  --bg:#16181d; --card:#22252b; --chip:#2a2e35;
  /* figures/crops keep a light card so black-ink MathPix crops stay legible */
  --figbg:#f4f4f4;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,system-ui,'Segoe UI',sans-serif;
  --mono:ui-monospace,Menlo,Consolas,monospace;
}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:17px/1.65 var(--serif);-webkit-font-smoothing:antialiased}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}

/* distill-style named-column grid: every direct child defaults to `text` */
article.d{{display:grid;margin:0 0 90px;
  grid-template-columns:
    [screen-start] minmax(16px,1fr)
    [page-start]   minmax(0,180px)
    [text-start]   minmax(auto,720px)
    [text-end]     minmax(0,60px)
    [gutter-start] minmax(0,220px)
    [gutter-end page-end] minmax(16px,1fr)
    [screen-end];
  grid-column-gap:24px}}
article.d > *{{grid-column:text}}
article.d > .wide{{grid-column:page-start / gutter-end}}
article.d > .screen{{grid-column:screen}}
article.d > .gutter{{grid-column:gutter-start / gutter-end;
  font:12.5px/1.45 var(--sans);color:var(--muted)}}

/* title band, like the .real-title bar on the source page */
.titleband{{grid-column:screen;background:var(--wash);
  border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:34px 0 30px;margin-bottom:26px;display:grid;
  grid-template-columns:subgrid}}
.titleband h1{{grid-column:text;font:700 32px/1.2 var(--sans);margin:0}}
.titleband .byline{{grid-column:text;font:13px var(--sans);
  color:var(--muted);margin-top:12px}}

h2{{font:700 24px/1.25 var(--sans);margin:1.8em 0 .5em;
    border-bottom:1px solid var(--line);padding-bottom:6px}}
h3{{font:700 18px/1.3 var(--sans);margin:1.4em 0 .35em}}
p{{margin:.65em 0;text-align:justify;hyphens:auto}}
.abstract{{background:var(--wash);border-left:3px solid var(--accent);
  padding:14px 18px;margin:1.2em 0;font-size:15px}}
.abstract b{{font-family:var(--sans);display:block;margin-bottom:5px}}

/* toc — filled at runtime from the heading flow, d-contents style */
nav.toc{{border:1px solid var(--line);border-radius:4px;padding:14px 20px;
  margin:6px 0 24px;font:13.5px/1.7 var(--sans)}}
nav.toc .head{{font:600 11px/1 var(--sans);letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);margin-bottom:8px}}
nav.toc a{{display:block;color:var(--ink)}}
nav.toc a.l3{{padding-left:18px;color:var(--muted)}}

/* equations */
.eqblock{{display:flex;align-items:center;gap:14px;margin:1.1em 0}}
.eqblock .eqmath{{flex:1;text-align:center;overflow-x:auto;padding:2px 0}}
.eqblock .eqnum{{flex:none;font:14px var(--sans);color:var(--muted)}}
.prov{{display:inline-block;font:10px/1 var(--mono);color:var(--faint);
  background:var(--chip);border:1px solid var(--line);border-radius:999px;
  padding:3px 8px}}
.eqcrop{{text-align:center;margin:0 0 12px}}
.eqcrop img{{max-width:70%;border:1px solid var(--line)}}

/* figures — data-fignum + fig-ref late binding, per the source page */
figure{{margin:1.6em 0;text-align:center}}
figure img{{max-width:100%;border:1px solid var(--line);background:var(--figbg)}}
figure .svg svg{{max-width:100%;height:auto}}
/* dvisvgm bakes BLACK into an SVG (invisible on the dark page). A legacy SVG is
   inverted for dark (hue-rotate keeps any colours roughly right); a dvisvgm
   `--currentcolor` SVG is marked .cc and instead inherits the theme ink. */
figure .svg:not(.cc) svg{{filter:invert(1) hue-rotate(180deg)}}
figure .svg.cc{{color:var(--ink)}}
figcaption{{font:13.5px/1.5 var(--sans);color:var(--muted);
  margin-top:8px;text-align:left}}
figcaption .fig-num{{font-weight:700;color:var(--ink)}}
pre.table,pre.code{{font:12px/1.45 var(--mono);background:var(--wash);
  padding:12px;overflow-x:auto;border-radius:4px;text-align:left}}
a.fig-ref{{white-space:nowrap}}

/* citations + footnotes — d-cite / d-footnote style hover popovers */
.cite,.fnref{{position:relative;font:.8em var(--sans);
  color:var(--accent);cursor:pointer;vertical-align:super}}
.cite .pop,.fnref .pop{{visibility:hidden;opacity:0;transition:opacity .12s;
  position:absolute;bottom:1.6em;left:-40px;z-index:9;width:340px;
  background:var(--card);border:1px solid var(--line);border-radius:5px;
  box-shadow:0 6px 24px rgba(0,0,0,.14);padding:10px 13px;
  font:12.5px/1.5 var(--sans);color:var(--ink);text-align:left;
  vertical-align:baseline}}
.cite:hover .pop,.fnref:hover .pop{{visibility:visible;opacity:1}}
ol.refs,ol.fns{{font:13.5px/1.6 var(--sans);color:var(--muted)}}
ol.refs li,ol.fns li{{margin:.4em 0}}

ul{{margin:.6em 0 .6em 1.4em;padding:0}}
.tok{{font:11px/1 var(--mono);color:var(--muted);background:var(--chip);
  border:1px solid var(--line);border-radius:3px;padding:1px 5px}}

/* tiddler-title margin label on hover (house convention) */
[data-obj]{{border-radius:2px}}
[data-obj]:hover{{background:rgba(15,108,140,.06)}}
:target{{background:rgba(15,108,140,.12)}}
@media(max-width:900px){{article.d{{display:block;padding:0 18px}}
  .titleband{{display:block;padding:24px 18px}}}}
</style>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  /* 1. KaTeX from data-latex (house pattern) */
  document.querySelectorAll(".math-render").forEach(function (el) {{
    var t = el.getAttribute("data-latex") || "";
    var d = el.getAttribute("data-display") === "true";
    try {{ katex.render(t, el, {{ displayMode: d, throwOnError: false }}); }}
    catch (e) {{ el.textContent = t; }}
  }});
  /* 2. d-contents-style TOC from the heading flow */
  var toc = document.querySelector("nav.toc .body");
  if (toc) document.querySelectorAll("article.d h2[id],article.d h3[id]")
    .forEach(function (h) {{
      var a = document.createElement("a");
      a.href = "#" + h.id; a.textContent = h.textContent;
      if (h.tagName === "H3") a.className = "l3";
      toc.appendChild(a);
    }});
  /* 3. late-bound ?? references, exactly like the fig-ref mechanism */
  var num = {{}};
  document.querySelectorAll("figure[data-fignum]").forEach(function (f) {{
    num[f.id] = f.getAttribute("data-fignum");
  }});
  document.querySelectorAll("a.fig-ref").forEach(function (a) {{
    var id = (a.getAttribute("href") || "").slice(1);
    if (num[id]) a.textContent = "Figure " + num[id];
    else {{
      var t = document.getElementById(id);
      var eq = t && t.querySelector(".eqnum");
      a.textContent = eq ? eq.textContent : (t ? a.dataset.label || "ref" : "??");
    }}
  }});
}});
</script>
</head>
<body>
<article class="d">
<div class="titleband">
  <h1>{title}</h1>
  <div class="byline">pdfdrill · docmodel projection · {bibkey} · {stats}</div>
</div>
<nav class="toc"><div class="head">Contents</div><div class="body"></div></nav>
"""

_FOOT = """</article>
</body>
</html>
"""


class DistillReaderProjector(BaseProjector):
    """Project the docmodel to a distill-structured single-file article."""

    def output_extension(self) -> str:
        return ".distill.html"

    # ---- tiddler-scheme title map (mirrors tiddlywiki.py / llm_text.py) ---
    def _title_map(self, objs: "list[DocObject]", bibkey: str) -> "dict[str, str]":
        flow = lambda o: o.props.get("flow_index") or 0
        fmt = {"Paragraph": "{b}_PARA_{i:04d}", "Equation": "{b}_EQ{i:04d}",
               "Formula": "{b}_FO{i:04d}", "Diagram": "{b}_DIA_{i:04d}",
               "Picture": "{b}_PIC_{i:04d}", "Table": "{b}_TAB_{i:03d}",
               "Footnote": "{b}_FN_{i:03d}", "Sidenote": "{b}_SN_{i:03d}",
               "ListItem": "{b}_LI_{i:04d}"}
        titles: "dict[str, str]" = {}
        for typ, f in fmt.items():
            for i, o in enumerate(sorted((x for x in objs if x.type == typ),
                                         key=flow), 1):
                titles[o.id] = f.format(b=bibkey, i=i)
        return titles

    # ---- references (d-cite backing) --------------------------------------
    def _reference_index(self, doc: Document) -> "tuple[list[DocObject], dict[str, int]]":
        refs = sorted(doc.objects_of_type("Reference"),
                      key=lambda o: (o.props.get("refnum")
                                     or o.props.get("flow_index") or 0))
        by_num = {}
        for i, r in enumerate(refs, 1):
            n = str(r.props.get("refnum") or i)
            by_num[n] = i
        return refs, by_num

    @staticmethod
    def _ref_text(r: DocObject) -> str:
        return (r.props.get("text") or " ".join(
            str(r.props.get(k) or "") for k in ("author", "year", "title"))
            ).strip() or (r.props.get("citekey") or "reference")

    # ---- inline transclusion tokens ---------------------------------------
    def _prose(self, text: str, fo_latex: "dict[str, str]",
               fig_ids: "dict[str, str]", refs_text: "dict[str, str]") -> str:
        out, pos = [], 0
        for m in TW_TRANSCLUSION.finditer(text):
            out.append(html.escape(text[pos:m.start()]))
            pos = m.end()
            title, _, template = m.group(1).rpartition("||")
            template = template.strip()
            n = num_from_title(title)
            if template == "FO" and title in fo_latex:
                out.append(_math(fo_latex[title], False))
            elif template == "FREF":
                target = re.sub(r"_p\d+$", "", title)
                out.append(f'<a class="fig-ref" data-label="({n})" '
                           f'href="#{html.escape(target, quote=True)}">??</a>')
            elif template in ("DIA", "TAB", "PIC") and title in fig_ids:
                out.append(f'<a class="fig-ref" '
                           f'href="#{html.escape(fig_ids[title], quote=True)}">??</a>')
            elif template == "CIT":
                body = refs_text.get(n, "")
                label = n or "c"
                pop = (f'<span class="pop">{html.escape(body)}</span>'
                       if body else "")
                out.append(f'<span class="cite">[<a href="#ref-{label}">'
                           f'{html.escape(label)}</a>]{pop}</span>')
            elif template:
                out.append(f'<span class="tok">{html.escape(template)} '
                           f'{html.escape(n)}</span>')
            self.bump("tokens")
        out.append(html.escape(text[pos:]))
        return "".join(out)

    def _crop(self, obj: DocObject, css: str) -> str:
        cdn = obj.props.get("cdn_url") or ""
        if not cdn:
            return ""
        src = embed_image(cdn) if self.params.get("embed") else cdn
        img = f'<img loading="lazy" alt="crop" src="{html.escape(src, quote=True)}">'
        link = page_url(cdn)
        if link:
            img = (f'<a href="{html.escape(link, quote=True)}" target="_blank" '
                   f'rel="noopener">{img}</a>')
        return f'<div class="{css}">{img}</div>' if css else img

    # ---- main --------------------------------------------------------------
    def project(self, doc: Document) -> str:
        bibkey = doc.meta.get("bibkey", "DOC")
        content = flow_ordered_content(doc)
        titles = self._title_map(content, bibkey)

        fo_latex = {titles[o.id]: str(o.props.get("latex"))
                    for o in content if o.type == "Formula"
                    and o.id in titles and not _empty(o.props.get("latex"))}
        # tiddler title -> distill figure id, for ||DIA / ||TAB tokens
        fig_ids = {titles[o.id]: f"fig-{titles[o.id]}"
                   for o in content
                   if o.type in ("Diagram", "Picture", "Table") and o.id in titles}
        refs, _by = self._reference_index(doc)
        refs_text = {str(r.props.get("refnum") or i): self._ref_text(r)
                     for i, r in enumerate(refs, 1)}

        doc_title, body, counts = None, [], {}
        fignum, open_list = 0, False

        def close_list():
            nonlocal open_list
            if open_list:
                body.append("</ul>")
                open_list = False

        for obj in content:
            t = obj.type
            counts[t] = counts.get(t, 0) + 1
            tid = titles.get(obj.id, "")
            aid = f' id="{tid}" data-obj="{tid}"' if tid else ""
            if t != "ListItem":
                close_list()

            if t == "Section":
                title = (obj.props.get("title") or obj.props.get("text") or "").strip()
                if not title:
                    continue
                level = int(obj.props.get("level") or 1)
                numpfx = (obj.props.get("number") or "").strip()
                tag = "h2" if level <= 1 else "h3"
                sid = _slug((numpfx + " " + title).strip())
                body.append(f'<{tag} id="{sid}">'
                            f'{html.escape((numpfx + " " if numpfx else "") + title)}'
                            f"</{tag}>")

            elif t == "Abstract" or (
                    t == "Paragraph" and doc_title is not None
                    and (obj.props.get("text") or "").lower().startswith("abstract")):
                text = (obj.props.get("text") or "").strip()
                if t == "Paragraph":
                    text = text[len("abstract"):].lstrip(" .:—-\n")
                if text:
                    body.append(f'<div class="abstract"{aid}><b>Abstract</b>'
                                f"{self._prose(text, fo_latex, fig_ids, refs_text)}"
                                f"</div>")

            elif t == "Paragraph":
                text = (obj.props.get("text") or "").strip()
                if not text:
                    continue
                if doc_title is None:
                    doc_title = text.splitlines()[0].strip()
                    rest = text[len(text.splitlines()[0]):].strip()
                    if rest:
                        body.append(f"<p{aid}>"
                                    f"{self._prose(rest, fo_latex, fig_ids, refs_text)}</p>")
                    continue
                body.append(f"<p{aid}>"
                            f"{self._prose(text, fo_latex, fig_ids, refs_text)}</p>")

            elif t == "Equation":
                latex = obj.props.get("latex")
                if _empty(latex):
                    continue
                eqnum = (obj.props.get("equation_number")
                         or obj.props.get("refnum") or "").strip()
                if eqnum and not eqnum.startswith("("):
                    eqnum = f"({eqnum})"
                numsp = (f'<span class="eqnum">{html.escape(eqnum)}</span>'
                         if eqnum else "")
                body.append(f'<div class="eqblock"{aid}>'
                            f'<div class="eqmath">{_math(latex, True)}</div>'
                            f"{numsp}</div>")
                prov = obj.props.get("provenance") or obj.props.get("added_by") or ""
                if prov:
                    body.append(f'<div class="gutter"><span class="prov">'
                                f"{html.escape(prov)}</span></div>")
                crop = self._crop(obj, "eqcrop")
                if crop:
                    body.append(crop)

            elif t in ("Diagram", "Picture", "Table"):
                cap = (obj.props.get("caption") or "").strip()
                svg = obj.props.get("svg")
                if obj.props.get("subtype") == "code":
                    lang = obj.props.get("language") or ""
                    inner = (f'<pre class="code"><code>'
                             f'{html.escape(obj.props.get("code") or "")}</code></pre>')
                    cap = cap or f"code listing{(' (' + lang + ')') if lang else ''}"
                elif svg:
                    # `--currentcolor` SVGs carry `currentColor` → theme-native
                    # (class cc, inherits ink); legacy black SVGs get inverted.
                    cc = " cc" if "currentcolor" in svg.lower() else ""
                    inner = f'<div class="svg{cc}">{svg}</div>'
                elif obj.props.get("cdn_url"):
                    inner = self._crop(obj, "")
                elif obj.props.get("latex_code"):
                    inner = (f'<pre class="table"><code>'
                             f'{html.escape(obj.props["latex_code"])}</code></pre>')
                else:
                    continue
                fignum += 1
                figid = fig_ids.get(tid, f"fig-{tid or fignum}")
                capsp = (f'<figcaption><span class="fig-num">Figure {fignum}: '
                         f"</span>{html.escape(cap)}</figcaption>" if cap else
                         f'<figcaption><span class="fig-num">Figure {fignum}'
                         f"</span></figcaption>")
                body.append(f'<figure class="wide" id="{figid}" '
                            f'data-fignum="{fignum}" data-obj="{tid}">'
                            f"{inner}{capsp}</figure>")

            elif t in ("Footnote", "Sidenote"):
                text = (obj.props.get("text") or obj.props.get("content") or "").strip()
                if not text:
                    continue
                n = counts.get("Footnote", 0) + counts.get("Sidenote", 0)
                pop = self._prose(text, fo_latex, fig_ids, refs_text)
                body.append(f'<span class="fnref"{aid}>'
                            f'<a href="#fn-{n}">{n}</a>'
                            f'<span class="pop">{pop}</span></span>')
                self.bump("footnotes")

            elif t == "ListItem":
                text = (obj.props.get("content") or obj.props.get("text") or "").strip()
                if not text:
                    continue
                if not open_list:
                    body.append("<ul>")
                    open_list = True
                body.append(f"<li{aid}>"
                            f"{self._prose(text, fo_latex, fig_ids, refs_text)}</li>")

        close_list()

        # ---- appendix: footnote list + references (d-appendix analogue) ----
        fns = [o for o in content if o.type in ("Footnote", "Sidenote")
               and (o.props.get("text") or o.props.get("content"))]
        if fns:
            body.append("<h2 id=\"footnotes\">Footnotes</h2><ol class=\"fns\">")
            for i, o in enumerate(fns, 1):
                text = (o.props.get("text") or o.props.get("content") or "").strip()
                body.append(f'<li id="fn-{i}">'
                            f"{self._prose(text, fo_latex, fig_ids, refs_text)}</li>")
            body.append("</ol>")
        if refs:
            body.append("<h2 id=\"references\">References</h2><ol class=\"refs\">")
            for i, r in enumerate(refs, 1):
                n = str(r.props.get("refnum") or i)
                body.append(f'<li id="ref-{n}" value="{html.escape(n, quote=True)}">'
                            f"{html.escape(self._ref_text(r))}</li>")
            body.append("</ol>")

        stat_order = ["Section", "Paragraph", "Equation", "Formula",
                      "Table", "Diagram", "Picture"]
        stats = " · ".join(f"{counts[t]} {t.lower()}{'s' if counts[t] != 1 else ''}"
                           for t in stat_order if counts.get(t))
        head = _HEAD.format(
            kv=_KV,
            title=html.escape(str(doc_title or doc.meta.get("source_path", bibkey))),
            bibkey=html.escape(bibkey),
            stats=html.escape(stats),
        )
        self.bump("blocks", len(body))
        return head + "\n".join(body) + _FOOT
