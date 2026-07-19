"""
BeamerProjector — project the docmodel to a LaTeX **beamer** slide deck.

One frame per Section, `[allowframebreaks]` so long content auto-continues onto
follow-on slides (nothing dropped). A title frame, an outline (`\\tableofcontents`)
frame, and a References frame round it out. Content — prose, lists, equations,
figures — is rendered by the shared `LaTeXProjector` machinery, so transclusion
markers (`{{id||FO}}` → `\\Expr{i}`), citations (`[N]` → `\\cite`), and ListItem
grouping all work inside frames.

Compile with **xelatex** (beamer + raw Unicode). Distinct from `latex` (an article
projection) — same docmodel, a slide deck instead of a paper.
"""
from __future__ import annotations

from docmodel.core import Document
from .common import flow_ordered_content
from .latex import LaTeXProjector, _escape_text
from . import latex_pipeline as _pipe

_BEAMER_PREAMBLE = (
    "\\documentclass{beamer}\n"
    "\\usetheme{Madrid}\n"
    "\\usepackage{amsmath,amssymb,graphicx,booktabs}\n"
    "\\setbeamertemplate{navigation symbols}{}\n"
    "\\setbeamertemplate{caption}[numbered]"
)


class BeamerProjector(LaTeXProjector):

    def output_extension(self) -> str:
        return ".tex"

    def project(self, doc: Document) -> str:
        meta = doc.meta
        self._prepare(doc)                        # transclusion array / cite map / skips
        out: list[str] = [_BEAMER_PREAMBLE, ""]
        if self._formula_preamble:                # the readarray formula array
            out += ["% formula transclusion array (filecontents + readarray):",
                    self._formula_preamble, ""]

        title = str(meta.get("title") or "").strip()
        authors = meta.get("authors") or []
        if title:
            out.append(f"\\title{{{_escape_text(title)}}}")
        if authors:
            out.append("\\author{%s}"
                       % " \\and ".join(_escape_text(str(a)) for a in authors))
        out.append("\\begin{document}")
        out.append("")

        # title frame
        if title:
            out += ["\\begin{frame}[plain]", "  \\titlepage", "\\end{frame}", ""]
        # outline frame
        out += ["\\begin{frame}{Outline}", "  \\tableofcontents", "\\end{frame}", ""]

        # content frames: one per Section (allowframebreaks); orphan content
        # before the first Section gets its own frame so nothing sits loose.
        items = [o for o in flow_ordered_content(doc) if o.id not in self._skip_ids]
        for section, content in self._group_by_section(items):
            out += self._frame(section, content)

        # References frame (the bibliography lives on its own slide)
        bib = _pipe.bibliography_block(doc)
        if bib:
            out += ["\\begin{frame}[allowframebreaks]{References}",
                    "  \\footnotesize", bib, "\\end{frame}", ""]

        out.append("\\end{document}")
        return "\n".join(out).rstrip() + "\n"

    # ── frame assembly ───────────────────────────────────────────────────────

    def _group_by_section(self, items):
        """Yield `(section-or-None, [content objects])` — a new group starts at
        each Section; leading non-Section content is a group with section None."""
        section = None
        bucket: list = []
        for obj in items:
            if obj.type == "Section":
                if section is not None or bucket:
                    yield section, bucket
                section, bucket = obj, []
            else:
                bucket.append(obj)
        if section is not None or bucket:
            yield section, bucket

    def _frame(self, section, content) -> list[str]:
        cap = _escape_text(str(section.props.get("caption") or "").strip()) \
            if section is not None else ""
        out: list[str] = []
        # a top-level section drives the TOC/navigation
        if section is not None and int(section.props.get("level", 1)) <= 1 and cap:
            out.append(f"\\section{{{cap}}}")
        body = self._render_flow(content)
        if not any(b.strip() for b in body):
            body = ["  \\ " if not cap else ""]     # avoid an empty frame error
        title = f"{{{cap}}}" if cap else ""
        out.append(f"\\begin{{frame}}[allowframebreaks]{title}")
        out += body
        out.append("\\end{frame}")
        out.append("")
        return out
