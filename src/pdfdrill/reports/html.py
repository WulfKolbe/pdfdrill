"""HTML rendering of evidence rows: KaTeX client-side, lazy-loaded images.

An HTML rendering is a convenience, not evidence (530): KaTeX has no
preamble. The caveat banner says so on every page.
"""
from __future__ import annotations

import html as _h
from pathlib import Path

from docops.katex_notice import KATEX_WARNING_HTML
from . import COLUMNS
from .rows import EvidenceRow, EquationRow
from .tex import CAPTIONS, HOST_LINE_SENTENCE

_KV = "0.16.11"

_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #bbb; padding: .3rem .5rem; vertical-align: top; }}
    td.src {{ font-family: ui-monospace, monospace; font-size: .8rem; white-space: pre-wrap; }}
    img {{ max-width: 100%; height: auto; }}
    .note {{ color: #555; font-size: .9rem; }}
  </style>
  <script>
    document.addEventListener("DOMContentLoaded", function () {{
      document.querySelectorAll(".math-render").forEach(function (el) {{
        try {{ katex.render(el.dataset.latex, el,
              {{ displayMode: el.dataset.display === "true", throwOnError: false }}); }}
        catch (e) {{ el.textContent = "(not rendered)"; }}
      }});
    }});
  </script>
</head>
<body>
<h1>{title}</h1>
{caveat}
{meta}
"""


def _cell(v) -> str:
    return "<td>%s</td>" % ("---" if v in (None, "") else _h.escape(str(v)))


def _conf(r: EvidenceRow, ink_codes: bool = False) -> str:
    c = r.shown_confidence
    if c is None:
        base = "---"
    else:
        base = "%.3f" % c
    if ink_codes and isinstance(r, EquationRow) and r.ink_code:
        base += " <code>%s</code>" % _h.escape(r.ink_code)
    return "<td>%s</td>" % base


def _img(r: EvidenceRow, doc_dir: Path) -> str:
    if r.crop is None:
        return "<td>---</td>"
    try:
        rel = r.crop.relative_to(doc_dir)
    except ValueError:
        rel = r.crop
    return '<td><img src="%s" loading="lazy" alt="%s"></td>' % (
        _h.escape(str(rel).replace("\\", "/")), _h.escape(r.identifier))


def _row(r: EvidenceRow, doc_dir: Path, display: bool, ink_codes: bool = False) -> str:
    latex = r.latex or ""
    rendered = ('<span class="math-render" data-latex="%s" data-display="%s"></span>'
                % (_h.escape(latex, quote=True), "true" if display else "false")
                ) if latex else "---"
    return ("<tr>%s%s%s<td class=\"src\">%s</td><td>%s</td>%s</tr>\n"
            % (_cell(r.identifier), _cell(r.shown_page), _conf(r, ink_codes),
               _h.escape(latex) if latex else "---", rendered,
               _img(r, doc_dir)))


def render_page(rows: list, kind: str, *, title: str, doc_dir,
                meta_lines=(), caption=None, ink_codes: bool = False) -> str:
    doc_dir = Path(doc_dir)
    meta = "".join('<p class="note">%s</p>\n' % _h.escape(m) for m in meta_lines)
    out = [_HEAD.format(title=_h.escape(title), kv=_KV,
                        caveat=KATEX_WARNING_HTML, meta=meta)]
    out.append("<h2>%s (%d)</h2>\n" % (_h.escape(caption or CAPTIONS[kind]),
                                       len(rows)))
    if kind == "formula":
        out.append('<p class="note">%s</p>\n' % _h.escape(HOST_LINE_SENTENCE, quote=False))
    out.append("<table>\n<thead><tr>%s</tr></thead>\n<tbody>\n"
               % "".join("<th>%s</th>" % c for c in COLUMNS))
    for r in rows:
        out.append(_row(r, doc_dir, display=(kind == "equation"), ink_codes=ink_codes))
    out.append("</tbody></table>\n</body></html>\n")
    return "".join(out)
