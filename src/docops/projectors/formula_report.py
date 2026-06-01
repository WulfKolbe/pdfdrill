"""
FormulaReportProjector — a full inline + display math report (standalone HTML).

Two sections: every inline `Formula` (title link · LaTeX source · KaTeX
render), then every display `Equation` (· MathPix CDN image · equation
number). Titles mirror the TiddlyWiki scheme so the anchors line up with the
tiddler output. KaTeX renders client-side from `data-latex`/`data-display`
attributes on DOMContentLoaded (same approach as the reference report).
"""
from __future__ import annotations

import html

from docmodel.core import Document
from docmodel.mathpix import page_url
from ..base import BaseProjector
from .common import embed_image

_KV = "0.16.11"

_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Formula Report — {title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
    h1 {{ font-size: 1.4rem; }}
    h2 {{ font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc; }}
    .formula-table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    .formula-table th, .formula-table td {{ border: 1px solid #ddd; padding: .4rem .6rem; vertical-align: top; }}
    .formula-table th {{ background: #f0f0f0; }}
    td.title {{ white-space: nowrap; font-size: .8rem; }}
    td.latex code {{ font-size: .75rem; white-space: pre-wrap; word-break: break-all; }}
    td.katex {{ min-width: 8rem; }}
    td.cdn img {{ max-width: 200px; max-height: 80px; }}
    .svg svg {{ max-width: 320px; max-height: 220px; height: auto; }}
    td.cdn-missing {{ color: #aaa; text-align: center; }}
    .eq-num {{ font-size: .8rem; color: #666; margin-left: .4rem; }}
    a {{ color: #1a0dab; }}
  </style>
  <script>
    document.addEventListener("DOMContentLoaded", function() {{
      document.querySelectorAll(".math-render").forEach(function(el) {{
        var latex   = el.getAttribute("data-latex");
        var display = el.getAttribute("data-display") === "true";
        try {{ katex.render(latex, el, {{ displayMode: display, throwOnError: false }}); }}
        catch(e) {{ el.textContent = latex; }}
      }});
    }});
  </script>
</head>
<body>
  <h1>Formula Report</h1>
  <p><strong>Source:</strong> {source} &nbsp;|&nbsp;
     <strong>MathExpressions:</strong> {n_formulas} &nbsp;|&nbsp;
     <strong>Equations:</strong> {n_equations}</p>
"""


def _math_span(latex: str, display: bool) -> str:
    return (f'<span class="math-render" data-latex="{html.escape(latex, quote=True)}" '
            f'data-display="{"true" if display else "false"}"></span>')


class FormulaReportProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".formula-report.html"

    def project(self, doc: Document) -> str:
        bibkey = doc.meta.get("bibkey", "DOC")

        def flow(objs):
            return sorted(objs, key=lambda o: o.props.get("flow_index", 10**9))

        formulas = flow(doc.objects_of_type("Formula"))
        equations = flow(doc.objects_of_type("Equation"))

        parts = [_HEAD.format(
            kv=_KV,
            title=html.escape(str(doc.meta.get("source_path", bibkey))),
            source=html.escape(str(doc.meta.get("source_path", bibkey))),
            n_formulas=len(formulas),
            n_equations=len(equations),
        )]

        # ---- Inline math ----
        parts.append(f"  <h2>Inline Math — MathExpression tiddlers ({len(formulas)})</h2>")
        parts.append('<table class="formula-table"><thead><tr>'
                     "<th>Tiddler</th><th>LaTeX source</th><th>Rendered (KaTeX)</th>"
                     "</tr></thead><tbody>")
        for i, f in enumerate(formulas, 1):
            tid = f"{bibkey}_FO{i:04d}"
            latex = f.props.get("latex", "")
            parts.append(
                "<tr>"
                f'<td class="title"><a href="#{tid}" id="{tid}" title="{tid}">{tid}</a></td>'
                f'<td class="latex"><code>{html.escape(latex)}</code></td>'
                f'<td class="katex">{_math_span(latex, False)}</td>'
                "</tr>")
            self.bump("inline_rows")
        parts.append("</tbody></table>")

        # ---- Display equations ----
        parts.append(f"  <h2>Display Equations ({len(equations)})</h2>")
        parts.append('<table class="formula-table"><thead><tr>'
                     "<th>Tiddler</th><th>LaTeX source</th><th>Rendered (KaTeX)</th>"
                     "<th>MathPix image</th></tr></thead><tbody>")
        for i, e in enumerate(equations, 1):
            page = int(e.props.get("page") or 0)
            tid = f"{bibkey}_EQ{i:04d}_p{page:03d}"
            latex = e.props.get("latex", "")
            eqnum = e.props.get("equation_number") or ""
            num_html = f'<span class="eq-num">{html.escape(eqnum)}</span>' if eqnum else ""
            cdn = e.props.get("cdn_url") or ""
            if cdn:
                src = embed_image(cdn) if self.params.get("embed") else cdn
                # Link the crop to the full page it was taken from (the crop is
                # always embeddable; the page link stays a live CDN URL).
                page_link = page_url(cdn)
                img_tag = (f'<img loading="lazy" alt="crop" '
                           f'src="{html.escape(src, quote=True)}">')
                if page_link:
                    img_tag = (f'<a href="{html.escape(page_link, quote=True)}" '
                               f'target="_blank" rel="noopener" '
                               f'title="full page {page}">{img_tag}</a>')
                img = f'<td class="cdn">{img_tag}</td>'
            else:
                img = '<td class="cdn-missing">—</td>'
            parts.append(
                "<tr>"
                f'<td class="title"><a href="#{tid}" id="{tid}" title="{tid}">{tid}</a>{num_html}</td>'
                f'<td class="latex"><code>{html.escape(latex)}</code></td>'
                f'<td class="katex">{_math_span(latex, True)}</td>'
                f"{img}"
                "</tr>")
            self.bump("equation_rows")
        parts.append("</tbody></table>")

        # ---- TikZ diagrams + tables (SVG, where rendered) ----
        graphics = flow(doc.objects_of_type("Diagram") + doc.objects_of_type("Table"))
        graphics = [g for g in graphics
                    if g.props.get("svg") or g.props.get("latex_code") or g.props.get("cdn_url")]
        if graphics:
            n_svg = sum(1 for g in graphics if g.props.get("svg"))
            parts.append(f"  <h2>TikZ &amp; Tables ({len(graphics)}; {n_svg} rendered to SVG)</h2>")
            parts.append('<table class="formula-table"><thead><tr>'
                         "<th>#</th><th>type</th><th>caption</th>"
                         "<th>LaTeX source</th><th>SVG render</th></tr></thead><tbody>")
            for i, g in enumerate(graphics, 1):
                code = g.props.get("latex_code") or ""
                label = " ".join(x for x in (g.props.get("kind"), g.props.get("refnum")) if x)
                cap_body = g.props.get("caption") or ""
                cap = html.escape((f"{label}: " if label else "") + cap_body) if (label or cap_body) else ""
                svg = g.props.get("svg")
                if svg:
                    cell = f'<div class="svg">{svg}</div>'
                elif g.props.get("cdn_url"):
                    cell = (f'<img loading="lazy" alt="crop" '
                            f'src="{html.escape(g.props["cdn_url"], quote=True)}">')
                else:
                    err = g.props.get("svg_error")
                    cell = (f'<span class="cdn-missing">not rendered'
                            + (f' ({html.escape(err[:60])})' if err else '')
                            + ' — run <code>pdfdrill svg</code></span>')
                parts.append(
                    "<tr>"
                    f'<td class="num">{i}</td>'
                    f'<td>{g.type}</td><td>{cap}</td>'
                    f'<td class="latex"><code>{html.escape(code[:400])}</code></td>'
                    f"<td>{cell}</td></tr>")
                self.bump("graphic_rows")
            parts.append("</tbody></table>")

        parts.append("\n</body>\n</html>\n")
        return "\n".join(parts)
