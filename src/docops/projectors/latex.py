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

import re

from docmodel.core import Document
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label
from . import latex_pipeline as _pipe

# level → sectioning command (1-indexed; clamped)
_SECTION_CMDS = ["section", "section", "subsection", "subsubsection",
                 "paragraph", "subparagraph"]

_DEFAULT_PREAMBLE = (
    "\\documentclass[11pt]{article}\n"
    # Compiled with XELATEX (see cmd_latex): it is natively UTF-8, so NO
    # inputenc/fontenc — `\\usepackage[utf8]{inputenc}` actively CLASHES with
    # xelatex and the model can carry raw Unicode inputenc/pdflatex would reject.
    # amsmath/symb/fonts + bm (\bm), mathtools, xcolor/url (leaked commands),
    # booktabs/multirow (tables) — the packages a projected paper commonly needs.
    "\\usepackage{amsmath,amssymb,amsfonts,mathtools,bm}\n"
    "\\usepackage{graphicx,booktabs,multirow,xcolor,url,hyperref}\n"
)


def _escape_text(s: str) -> str:
    """Escape the LaTeX specials in a caption/title/author. IDEMPOTENT (`(?<!\\\\)`):
    an already-escaped `C\\#` from the source is NOT doubled into `C\\\\#` (which is
    a line break + a bare `#` → error). `$`, `\\`, `{`, `}`, `^` are left alone so
    inline math / already-LaTeX spans the model carries survive."""
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    s = re.sub(r"(?<!\\)_", r"\\_", s)
    s = re.sub(r"(?<!\\)~", r"\\textasciitilde{}", s)
    return s


class LaTeXProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".tex"

    def project(self, doc: Document) -> str:
        meta = doc.meta
        self._prepare(doc)
        preamble = self._doc_preamble(meta)
        out: list[str] = [preamble.rstrip(), ""]
        if self._formula_preamble:                # the formula ARRAY (readarray)
            out += ["% formula transclusion array (filecontents + readarray):",
                    self._formula_preamble, ""]

        title = meta.get("title") or self._leaked_title(doc)
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

        # STAGE 3: the Acronyms list (front matter)
        gloss = _pipe.glossary_block(self._acronyms)
        if gloss:
            out += [gloss, ""]

        items = [o for o in flow_ordered_content(doc) if o.id not in self._skip_ids]
        out += self._render_flow(items)

        # STAGE 2: bibliography — printed `\bibitem`s from the model's References.
        bib = _pipe.bibliography_block(doc)
        if bib:
            out.append(bib)
            out.append("")

        out.append("\\end{document}")
        return "\n".join(out).rstrip() + "\n"

    # ── shared setup + rendering (reused by the beamer projector) ────────────

    def _prepare(self, doc: Document) -> None:
        """Set up the pipeline state used by the content renderers: the
        transclusion ARRAY (`{{id||FO}}`→`\\Expr{i}`), the citation reference map
        (`[N]`→`\\cite`), and the References-section skip set."""
        key = str(doc.meta.get("bibkey") or "DOC")
        self._order, self._title_index = _pipe.formula_array(doc)
        self._formula_preamble = _pipe.formula_preamble(
            self._order, f"{key}.formulas.dat")
        self._ref_map = _pipe.reference_map(doc)
        self._skip_ids = _pipe.reference_section_ids(doc) if self._ref_map else set()
        # STAGE 3: acronyms / glossary from the named-concept layer (lazy — the
        # `semantic` package; degrade to none if unavailable).
        self._acronyms: list = []
        try:
            from semantic import concepts as _concepts
            self._acronyms = [(r.get("name"), r.get("expansion"))
                              for r in _concepts.concept_records(doc)
                              if r.get("name") and r.get("expansion")]
        except Exception:                                 # noqa: BLE001
            self._acronyms = []

    def _leaked_title(self, doc) -> str | None:
        """When the model carries no `meta['title']` (common on a LaTeX-source
        build), recover a `\\title{…}` the builder left in body prose, so the
        projection gets a real `\\title` instead of a `\\maketitle` with none."""
        for obj in doc.objects.values():
            if obj.type in ("Paragraph", "Abstract"):
                t = _pipe.leaked_title(str(obj.props.get("text") or ""))
                if t:
                    return t
        return None

    def _doc_preamble(self, meta) -> str:
        """A document-specific preamble captured by `injectlatex` (macros the
        equations need) wins; else a sane default. May be a plain string OR a dict
        ({"expanded"/"standalone": …}); coerce to a usable string.

        A `standalone` preamble is REJECTED: it typesets the body in a box (LR
        mode) for CROPPING figures in the SVG step, so `\\section` errors 'Not
        allowed in LR mode' in a full document. Fall back to the article default."""
        pre = meta.get("latex_preamble")
        if isinstance(pre, dict):
            pre = pre.get("expanded") or pre.get("standalone") or pre.get("preamble")
        if not (isinstance(pre, str) and pre.strip()):
            return _DEFAULT_PREAMBLE
        if re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{\s*standalone\s*\}", pre):
            return _DEFAULT_PREAMBLE                 # figure-crop preamble → not a document
        return pre

    def _render_flow(self, items) -> list[str]:
        """Render a flat list of objects to LaTeX blocks, grouping consecutive
        ListItems into one `itemize` (bare `\\item` is invalid). Returns blocks
        (each followed by a blank line)."""
        out: list[str] = []
        i = 0
        while i < len(items):
            obj = items[i]
            if obj.type == "ListItem":
                run = []
                while i < len(items) and items[i].type == "ListItem":
                    run.append(items[i]); i += 1
                out.append(self._render_list(run))
                out.append("")
                continue
            block = self._render(obj)
            if block:
                out.append(block)
                out.append("")
            i += 1
        return out

    def _render_list(self, run) -> str:
        """A run of ListItems → one `itemize`; each item keeps its source marker
        as the `[label]` (braced so a bracket in the marker is safe), and its
        content passes through `_prose` (transclusions / citations resolve)."""
        lines = ["\\begin{itemize}"]
        for it in run:
            content = self._prose(str(it.props.get("content") or "").strip())
            marker = str(it.props.get("marker") or "").strip()
            label = f"[{{{marker}}}]" if marker else ""
            lines.append(f"  \\item{label} {content}".rstrip())
        lines.append("\\end{itemize}")
        return "\n".join(lines)

    def _prose(self, text: str) -> str:
        """Resolve a prose block to LaTeX: transclusion markers → `\\Expr{<index>}`
        (readarray lookup), leaked Markdown headings → `\\section`. Line-wise so a
        heading mid-paragraph still converts."""
        ti = getattr(self, "_title_index", {})
        text = _pipe.clean_prose(text)                # ligatures + leaked \bibliography
        text = _pipe.resolve_transclusions(text, ti)
        text = _pipe.resolve_citations(text, getattr(self, "_ref_map", {}))
        # contain any runaway inline math (a dropped `\)`/`$`) to THIS block, so
        # it can't swallow the next \section ("Not allowed in LR mode").
        text = _pipe.balance_math(text)
        # headings FIRST (so a leaked `## X` still matches — escaping `#` would
        # break it), THEN escape prose specials (`#`/`%`/`&` outside math).
        lines = (_pipe.resolve_headings(ln) for ln in text.split("\n"))
        return "\n".join(_pipe.escape_prose_specials(ln) for ln in lines)

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
            latex = _pipe.sanitize_math((p.get("latex") or "").strip())
            if not latex:                                 # CDN-crop-only — nothing to typeset
                return ""
            label = p.get("label") or equation_label(obj)
            lab = f"\n\\label{{{label}}}" if label else ""
            return f"\\begin{{equation}}\n{latex}{lab}\n\\end{{equation}}"
        if t == "Formula":
            latex = _pipe.sanitize_math((p.get("latex") or "").strip())
            return f"${latex}$" if latex else ""
        if t == "Table":
            code = (p.get("latex_code") or "").strip()
            if code:
                # a tabular can carry `\citep{…}` (undefined here) — normalise to
                # `\cite`; keep the table's own `&`/`\\` untouched.
                return _pipe.normalize_cite_commands(code)
            raw = (p.get("raw_text") or "").strip()
            return f"% table p{p.get('page')}\n\\begin{{verbatim}}\n{raw}\n\\end{{verbatim}}" if raw else ""
        if t in ("Picture", "Diagram"):
            code = (p.get("latex_code") or "").strip()
            if code:
                return code
            cap = _escape_text(str(p.get("caption") or "").strip())
            return f"% figure p{p.get('page')}" + (f": {cap}" if cap else "")
        if t == "ListItem":
            # a lone ListItem (not part of a run) — still needs an environment
            return self._render_list([obj])
        if t == "Footnote":
            return f"\\footnotetext{{{_escape_text(str(p.get('content') or ''))}}}"
        return ""
