"""
ComparisonHtmlProjector — the QC table.

One HTML row per display `Equation` that carries a MathPix CDN crop. The
baseline columns are the MathPix-PDF LaTeX, its KaTeX rendering, and the
cropped image MathPix produced. Whenever an equation also carries competing
`latex_candidate` realizations (e.g. provenance "snip" from MathPix /v3/text,
or "llm"), each distinct provenance adds its own LaTeX + KaTeX columns, with
the candidate's score shown inline. This lets a human — and, later, a scorer —
see at a glance how the readings agree and whether they match the image.

KaTeX is loaded from a CDN and each cell is rendered via `katex.render`
against a `data-tex` attribute, so LaTeX delimiters in the body can't break
the page.
"""
from __future__ import annotations

import html

from docmodel.core import Document
from ..base import BaseProjector
from docmodel.mathpix import page_url
from .common import flow_ordered_content, equation_label, embed_image


_KATEX_VERSION = "0.16.11"

# Preferred left-to-right order for competing-provenance columns.
_PROV_PREF = ["snip", "llm"]

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LaTeX vs MathPix image — {title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/contrib/mhchem.min.js"></script>
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
  .katex-cell {{ min-width: 11rem; }}
  .score {{ color: #888; font-size: 11px; margin-top: 4px; }}
  .render-error {{ color: #b00; font-family: monospace; white-space: pre-wrap; }}
  img.crop {{ max-width: 360px; height: auto; background: #fff;
              border: 1px solid #eee; }}
  td.empty {{ color: #ccc; text-align: center; }}
  tr.flagged {{ background: #fff5f5; }}
  td.score {{ white-space: nowrap; font-size: 12px; }}
  .flag {{ color: #b00; font-size: 11px; }}
</style>
</head>
<body>
<h1>LaTeX vs MathPix image — {title}</h1>
<div class="meta">{source} · {count} expressions · providers: {providers}</div>
<table>
<thead><tr>{head_cells}</tr></thead>
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
        rows_data: list[dict] = []
        provs: set[str] = set()
        for obj in flow_ordered_content(doc):
            cdn = obj.props.get("cdn_url") or ""
            mlatex = (obj.props.get("latex") or "").strip()
            if not cdn or not mlatex:
                continue
            cands: dict[str, dict] = {}
            for r in obj.realizations:
                if r.role != "latex_candidate":
                    continue
                lx = (r.props.get("latex") or "").strip()
                if not lx:
                    continue
                prov = r.provenance or "?"
                cands[prov] = {"latex": lx, "score": r.score}
                provs.add(prov)
            rows_data.append({
                "ref": equation_label(obj),
                "page": obj.props.get("page"),
                "mathpix": mlatex,
                "cdn": cdn,
                "cands": cands,
                "score": obj.props.get("score"),
            })
            self.bump("rows")

        ordered = [p for p in _PROV_PREF if p in provs] + \
                  sorted(p for p in provs if p not in _PROV_PREF)
        has_scores = any(rd.get("score") for rd in rows_data)

        head = ['<th>#</th>', '<th>ref</th>', '<th>p</th>']
        if has_scores:
            head.append('<th>score</th>')
        head += ['<th>LaTeX (mathpix)</th>', '<th>KaTeX (mathpix)</th>']
        for p in ordered:
            head.append(f'<th>LaTeX ({html.escape(p)})</th>')
            head.append(f'<th>KaTeX ({html.escape(p)})</th>')
        head.append('<th>MathPix image</th>')

        row_html: list[str] = []
        for i, rd in enumerate(rows_data, 1):
            sc = rd.get("score") or {}
            flagged = bool(sc.get("flags"))
            cells = [
                f'<td class="num">{i}</td>',
                f'<td class="ref">{html.escape(rd["ref"])}</td>',
                f'<td class="num">{rd["page"] if rd["page"] is not None else ""}</td>',
            ]
            if has_scores:
                cells.append(self._score_cell(sc))
            cells += self._latex_pair(rd["mathpix"])
            for p in ordered:
                c = rd["cands"].get(p)
                if c:
                    cells += self._latex_pair(c["latex"], score=c.get("score"))
                else:
                    cells += ['<td class="empty">—</td>', '<td class="empty">—</td>']
            cdn_src = embed_image(rd["cdn"]) if self.params.get("embed") else rd["cdn"]
            cells.append(f'<td>{self._img(cdn_src, page_link=page_url(rd["cdn"]))}</td>')
            tr = '<tr class="flagged">' if flagged else "<tr>"
            row_html.append(tr + "".join(cells) + "</tr>")

        meta = doc.meta
        return _PAGE_TEMPLATE.format(
            kv=_KATEX_VERSION,
            title=html.escape(str(meta.get("bibkey", "document"))),
            source=html.escape(str(meta.get("source_path", ""))),
            count=len(rows_data),
            providers=", ".join(["mathpix"] + ordered),
            head_cells="".join(head),
            rows="\n".join(row_html),
        )

    @staticmethod
    def _latex_pair(latex: str, score=None) -> list[str]:
        esc = html.escape(latex)
        esc_attr = html.escape(latex, quote=True)
        score_html = ""
        if isinstance(score, (int, float)):
            score_html = f'<div class="score">conf {score:.3f}</div>'
        return [
            f"<td><pre>{esc}</pre></td>",
            f'<td><div class="katex-cell" data-tex="{esc_attr}"></div>{score_html}</td>',
        ]

    @staticmethod
    def _score_cell(score: dict) -> str:
        if not score:
            return '<td class="empty">—</td>'
        parts = []
        ag = score.get("mean_agreement")
        if ag is not None:
            parts.append(f"agree {ag:.2f}")
        cf = score.get("snip_confidence")
        if cf is not None:
            parts.append(f"conf {cf:.2f}")
        flags = score.get("flags") or []
        flag_html = (f'<div class="flag">{html.escape(", ".join(flags))}</div>'
                     if flags else "")
        return f'<td class="score">{"<br>".join(parts)}{flag_html}</td>'

    @staticmethod
    def _img(cdn: str, page_link: str = "") -> str:
        tag = (f'<img class="crop" loading="lazy" alt="MathPix crop" '
               f'src="{html.escape(cdn, quote=True)}">')
        if page_link:
            tag = (f'<a href="{html.escape(page_link, quote=True)}" target="_blank" '
                   f'rel="noopener" title="full page">{tag}</a>')
        return tag
