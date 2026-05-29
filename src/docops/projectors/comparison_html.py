"""
ComparisonHtmlProjector — the QC table.

For every object that carries a MathPix CDN image (display `Equation`s), emit
one HTML row with three things side by side:

  1. the LaTeX MathPix produced (as source code),
  2. that LaTeX rendered by KaTeX in the browser, and
  3. the cropped image MathPix actually rendered (the CDN `<img>`).

This lets a human (and, later, a scorer) see at a glance whether MathPix's
LaTeX faithfully reproduces the image it was derived from. KaTeX is loaded
from a CDN and each cell is rendered via `katex.render` against a `data-tex`
attribute, so LaTeX delimiters in the body can't break the page.
"""
from __future__ import annotations

import html

from docmodel.core import Document
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label


_KATEX_VERSION = "0.16.11"

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LaTeX vs MathPix image — {title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
<style>
  body {{ font: 14px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ font-size: 1.2rem; }}
  .meta {{ color: #666; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 10px; vertical-align: top; }}
  th {{ background: #f5f5f5; text-align: left; position: sticky; top: 0; }}
  td.num {{ color: #999; white-space: nowrap; text-align: right; }}
  td.ref {{ white-space: nowrap; color: #444; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-word;
         font: 12px/1.4 ui-monospace, Menlo, Consolas, monospace; }}
  .katex-cell {{ min-width: 12rem; }}
  .render-error {{ color: #b00; font-family: monospace; white-space: pre-wrap; }}
  img.crop {{ max-width: 360px; height: auto; background: #fff;
              border: 1px solid #eee; }}
  td.noimg {{ color: #999; font-style: italic; }}
</style>
</head>
<body>
<h1>LaTeX vs MathPix image — {title}</h1>
<div class="meta">{source} · {count} expressions with a CDN crop</div>
<table>
<thead><tr>
  <th>#</th><th>ref</th><th>p</th>
  <th>LaTeX (MathPix)</th><th>KaTeX render</th><th>MathPix image</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
<script>
document.querySelectorAll(".katex-cell").forEach(function (el) {{
  var tex = el.getAttribute("data-tex") || "";
  try {{
    katex.render(tex, el, {{ displayMode: true, throwOnError: false }});
  }} catch (e) {{
    el.classList.add("render-error");
    el.textContent = String(e);
  }}
}});
</script>
</body>
</html>
"""


class ComparisonHtmlProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".compare.html"

    def project(self, doc: Document) -> str:
        row_html: list[str] = []
        n = 0
        for obj in flow_ordered_content(doc):
            cdn = obj.props.get("cdn_url") or ""
            latex = (obj.props.get("latex") or "").strip()
            # The comparison only means something where MathPix gave us an
            # image to compare the LaTeX against.
            if not cdn or not latex:
                continue
            n += 1
            self.bump("rows")
            ref = equation_label(obj)
            page = obj.props.get("page")
            esc = html.escape(latex)
            esc_attr = html.escape(latex, quote=True)
            img_cell = (
                f'<img class="crop" loading="lazy" alt="MathPix crop" '
                f'src="{html.escape(cdn, quote=True)}">'
            )
            row_html.append(
                "<tr>"
                f'<td class="num">{n}</td>'
                f'<td class="ref">{html.escape(ref)}</td>'
                f'<td class="num">{page if page is not None else ""}</td>'
                f"<td><pre>{esc}</pre></td>"
                f'<td><div class="katex-cell" data-tex="{esc_attr}"></div></td>'
                f"<td>{img_cell}</td>"
                "</tr>"
            )

        meta = doc.meta
        return _PAGE_TEMPLATE.format(
            kv=_KATEX_VERSION,
            title=html.escape(str(meta.get("bibkey", "document"))),
            source=html.escape(str(meta.get("source_path", ""))),
            count=n,
            rows="\n".join(row_html),
        )
