"""
LaTeXProjector — project a drilled Document to a compilable `.tex` document.

The LaTeX analog of the Markdown projector: sections → `\\section`/`\\subsection`,
prose paragraphs (their materialized text, inline math kept as `$…$`), display
equations → an `equation` environment carrying the object's `\\label`, tables →
their gold `latex_code` when present (else the raw grid), figures/diagrams noted.

This is the OUTPUT direction. `injectlatex` is the INPUT one (pull the author's
`.tex` source in as gold provenance). `pdfdrill latex` drives this projector.

Deliberately format-faithful, not semantic: it renders what the model holds. For
enriched LaTeX (acronyms/glossary/index, ORKG metadata) see `stex` / `scikgtex`.
"""
from __future__ import annotations

from docmodel.core import Document
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label
from . import latex_pipeline as _pipe

# level → sectioning command (1-indexed; clamped)
_SECTION_CMDS = ["section", "section", "subsection", "subsubsection",
                 "paragraph", "subparagraph"]

_DEFAULT_PREAMBLE = (
    "\\documentclass[11pt]{article}\n"
    "\\usepackage[utf8]{inputenc}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}\n"
)


def _escape_text(s: str) -> str:
    """Escape the LaTeX specials that appear in PROSE. Deliberately conservative:
    `$`, `\\`, `{`, `}`, `^` are left alone so inline math / already-LaTeX spans
    the model carries survive (the model's prose keeps `$…$` inline math)."""
    for a, b in (("&", "\\&"), ("%", "\\%"), ("#", "\\#"), ("_", "\\_"),
                 ("~", "\\textasciitilde{}")):
        s = s.replace(a, b)
    return s


class LaTeXProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".tex"

    def project(self, doc: Document) -> str:
        meta = doc.meta
        # STAGE 0: the transclusion array — every `{{id||FO}}` marker in the
        # prose resolves to the formula's `$…​$` by lookup, so a MathPix/scan
        # doc's body is real LaTeX, not "Markdown with a LaTeX header".
        self._lut = _pipe.transclusion_lookup(doc)
        # a document-specific preamble captured by `injectlatex` wins (macros the
        # equations need); else a sane default. It may be stored as a plain string
        # OR as a dict ({"expanded"/"standalone": …}); coerce to a usable string.
        pre = meta.get("latex_preamble")
        if isinstance(pre, dict):
            pre = pre.get("expanded") or pre.get("standalone") or pre.get("preamble")
        preamble = pre if isinstance(pre, str) and pre.strip() else _DEFAULT_PREAMBLE
        out: list[str] = [preamble.rstrip(), ""]

        title = meta.get("title")
        authors = meta.get("authors") or []
        if title:
            out.append(f"\\title{{{_escape_text(str(title))}}}")
        if authors:
            names = " \\and ".join(_escape_text(str(a)) for a in authors)
            out.append(f"\\author{{{names}}}")
        out.append("\\begin{document}")
        if title:
            out.append("\\maketitle")
        out.append("")

        for obj in flow_ordered_content(doc):
            block = self._render(obj)
            if block:
                out.append(block)
                out.append("")

        # STAGE 2: bibliography — printed `\bibitem`s from the model's References
        # (a real `.bib` for entries carrying BibTeX is emitted alongside by the
        # pipeline's dump; \bibliography wiring lands with stage 3).
        bib = _pipe.bibliography_block(doc)
        if bib:
            out.append(bib)
            out.append("")

        out.append("\\end{document}")
        return "\n".join(out).rstrip() + "\n"

    def _prose(self, text: str) -> str:
        """Resolve a prose block to LaTeX: transclusion markers → `$…​$` (array
        lookup), leaked Markdown headings → `\\section`. Line-wise so a heading
        mid-paragraph still converts."""
        lut = getattr(self, "_lut", {})
        text = _pipe.resolve_transclusions(text, lut)
        return "\n".join(_pipe.resolve_headings(ln) for ln in text.split("\n"))

    def _render(self, obj) -> str:
        t, p = obj.type, obj.props
        if t == "Section":
            cmd = _SECTION_CMDS[max(1, min(len(_SECTION_CMDS) - 1,
                                           int(p.get("level", 1))))]
            cap = _escape_text(str(p.get("caption") or "").strip())
            if not cap:
                return ""
            s = f"\\{cmd}{{{cap}}}"
            label = p.get("label")
            return s + (f"\n\\label{{{label}}}" if label else "")
        if t in ("Paragraph", "Abstract"):
            text = self._prose((p.get("text") or "").strip())
            if not text.strip():
                return ""
            if t == "Abstract":
                return f"\\begin{{abstract}}\n{text}\n\\end{{abstract}}"
            return text
        if t == "Equation":
            latex = (p.get("latex") or "").strip()
            if not latex:                                 # CDN-crop-only — nothing to typeset
                return ""
            label = p.get("label") or equation_label(obj)
            lab = f"\n\\label{{{label}}}" if label else ""
            return f"\\begin{{equation}}\n{latex}{lab}\n\\end{{equation}}"
        if t == "Formula":
            latex = (p.get("latex") or "").strip()
            return f"${latex}$" if latex else ""
        if t == "Table":
            code = (p.get("latex_code") or "").strip()
            if code:
                return code
            raw = (p.get("raw_text") or "").strip()
            return f"% table p{p.get('page')}\n\\begin{{verbatim}}\n{raw}\n\\end{{verbatim}}" if raw else ""
        if t in ("Picture", "Diagram"):
            code = (p.get("latex_code") or "").strip()
            if code:
                return code
            cap = _escape_text(str(p.get("caption") or "").strip())
            return f"% figure p{p.get('page')}" + (f": {cap}" if cap else "")
        if t == "ListItem":
            return f"\\item {_escape_text(str(p.get('content') or ''))}"
        if t == "Footnote":
            return f"\\footnotetext{{{_escape_text(str(p.get('content') or ''))}}}"
        return ""
