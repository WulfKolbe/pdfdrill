"""HTML rendering of evidence rows: KaTeX client-side, lazy-loaded images.

An HTML rendering is a convenience, not evidence (530): KaTeX has no
preamble. The caveat banner says so on every page.
"""
from __future__ import annotations

import html as _h
from pathlib import Path

from docops.katex_notice import KATEX_WARNING_HTML
from .. import report_tex as rt
from ..svg_ids import inline_body, safe_token
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
    .svg svg {{ max-width: 100%; height: auto; }}
    .refused {{ color: #a33; font-size: .9rem; }}
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


def _refined_mark(r: EvidenceRow) -> str:
    """669 -- the HTML twin of `report_tex.refined_flag` (233): a row whose
    `latex` is a VERIFIED refinement, not MathPix's own reading, says so
    beside its identifier rather than by disagreeing silently with the
    rendered cell."""
    info = getattr(r, "refined_info", None)
    if not info:
        return ""
    basis = info.get("basis") or info.get("verified_by") or "?"
    return ' <span class="note">[refined: %s]</span>' % _h.escape(str(basis))


def _graphic(r: EvidenceRow, doc_dir: Path, author_preamble: str) -> "str | None":
    r"""The Rendered cell for a row whose LaTeX is a PICTURE, or None when this
    row is not one and KaTeX should have it.

    2026-10-27, the owner's words: "show props['svg'] where it exists,
    otherwise the standalone PNG", and a failure says "(not rendered)" and
    gives the error — the same rule as the PDF half, which is why both ask
    `rt.needs_own_document` and share `rt.standalone_png`.

    The SVG comes first because it already exists: `pdfdrill svg` compiled it
    with the document's own preamble, and it is vector. The PNG is the fallback
    for the rows `svg` never ran on, or failed on. KaTeX is never asked — it
    has no TikZ at all, and `throwOnError: false` would put its own complaint
    into the cell as red text rather than let the page notice.
    """
    svg = getattr(r, "svg", "") or ""
    if svg:
        # Namespaced: dvisvgm restarts its glyph ids at g0-1 per file and this
        # page inlines every row's drawing — 112 of 336 references drew a glyph
        # from a different figure before `svg_ids` existed.
        body = inline_body(svg, safe_token(r.identifier))
        if body:
            return '<div class="svg">%s</div>' % body
    if not (r.latex and rt.needs_own_document(r.latex)):
        return None
    png, err = rt.standalone_png(r.latex, r.identifier, Path(doc_dir),
                                 author_preamble=author_preamble)
    if png is not None:
        return '<img src="%s/%s" loading="lazy" alt="%s">' % (
            rt.STANDALONE_DIR, _h.escape(png.name, quote=True),
            _h.escape(r.identifier, quote=True))
    # Both reasons, where there are two: `svg_error` is what `pdfdrill svg`
    # recorded and `err` is this compile's. Hiding either leaves a row whose
    # cell says nothing a reader can act on.
    why = " · ".join(x.strip() for x in (err, getattr(r, "svg_error", "") or "")
                     if x and x.strip())
    return ('<span class="refused">(not rendered)%s</span>'
            % ((" " + _h.escape(why[:200])) if why else ""))


def _row(r: EvidenceRow, doc_dir: Path, display: bool, ink_codes: bool = False,
         author_preamble: str = "") -> str:
    latex = r.latex or ""
    rendered = _graphic(r, doc_dir, author_preamble)
    if rendered is None:
        rendered = ('<span class="math-render" data-latex="%s" data-display="%s"></span>'
                    % (_h.escape(latex, quote=True), "true" if display else "false")
                    ) if latex else "---"
    ident = "<td>%s%s</td>" % (
        "---" if not r.identifier else _h.escape(r.identifier), _refined_mark(r))
    return ("<tr>%s%s%s<td class=\"src\">%s</td><td>%s</td>%s</tr>\n"
            % (ident, _cell(r.shown_page), _conf(r, ink_codes),
               _h.escape(latex) if latex else "---", rendered,
               _img(r, doc_dir)))


def render_section(rows: list, kind: str, *, doc_dir, caption=None,
                   ink_codes: bool = False, author_preamble: str = "") -> str:
    """`<h2>…</h2>` + `<table>…</table>` for one section — no DOCTYPE, no
    head, no body wrapper. `page_shell` supplies those; `render_section` is
    the part that is safe to concatenate with other sections before the
    shell goes on once (562: slicing a full `render_page` per section put
    the DOCTYPE/head wherever the first slice happened to end)."""
    doc_dir = Path(doc_dir)
    out = ["<h2>%s (%d)</h2>\n" % (_h.escape(caption or CAPTIONS[kind]),
                                   len(rows))]
    if kind == "formula":
        out.append('<p class="note">%s</p>\n' % _h.escape(HOST_LINE_SENTENCE, quote=False))
    out.append("<table>\n<thead><tr>%s</tr></thead>\n<tbody>\n"
               % "".join("<th>%s</th>" % c for c in COLUMNS))
    for r in rows:
        out.append(_row(r, doc_dir, display=(kind == "equation"),
                        ink_codes=ink_codes, author_preamble=author_preamble))
    out.append("</tbody></table>\n")
    return "".join(out)


def page_shell(title: str, body: str, *, meta_lines=()) -> str:
    """The complete document: head (KaTeX, CSS, caveat, meta lines) once,
    `body` verbatim, then the closing tags. `body` is one or more
    `render_section` fragments (or anything else HTML-shaped) concatenated
    by the caller."""
    meta = "".join('<p class="note">%s</p>\n' % _h.escape(m) for m in meta_lines)
    return (_HEAD.format(title=_h.escape(title), kv=_KV,
                         caveat=KATEX_WARNING_HTML, meta=meta)
            + body + "</body></html>\n")


def render_page(rows: list, kind: str, *, title: str, doc_dir,
                meta_lines=(), caption=None, ink_codes: bool = False,
                author_preamble: str = "") -> str:
    return page_shell(title, render_section(rows, kind, doc_dir=doc_dir,
                                            caption=caption,
                                            ink_codes=ink_codes,
                                            author_preamble=author_preamble),
                      meta_lines=meta_lines)
