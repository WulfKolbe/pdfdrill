"""
PlainTextProjector — emit a flowed plaintext rendering of the document.

For sanity-checking and for downstream tools that want a single linear
representation. Sections become headers, paragraphs become wrapped prose,
display equations become `[ EQ ref: latex ]`, inline formulas stay as their
LaTeX, citations stay as `[citekey]`, tables become a simple text grid.
"""
from __future__ import annotations

from docmodel.core import Document
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label


class PlainTextProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".txt"

    def project(self, doc: Document) -> str:
        lines: list[str] = []
        meta = doc.meta
        lines.append(f"# {meta.get('bibkey', 'Document')}")
        if meta.get("source_path"):
            lines.append(f"source: {meta['source_path']}")
        lines.append(f"pages: {meta.get('num_pages')}")
        lines.append("")

        for obj in flow_ordered_content(doc):
            block = self._render(obj, doc)
            if block:
                lines.append(block)
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render(self, obj, doc: Document) -> str:
        t = obj.type
        p = obj.props
        if t == "Section":
            depth = p.get("level", 1)
            num = p.get("section_number") or ""
            cap = p.get("caption") or ""
            prefix = "#" * max(1, min(6, depth))
            return f"{prefix} {num} {cap}".strip()
        if t == "Paragraph":
            return p.get("text") or ""
        if t == "Abstract":
            return f"[ABSTRACT]\n{p.get('text', '')}"
        if t == "Equation":
            ref = equation_label(obj)
            ref_part = f" ({ref})" if ref else ""
            return f"[EQ{ref_part}: {p.get('latex', '')} ]"
        if t == "Formula":
            return f"[F: {p.get('latex', '')} ]"
        if t == "Table":
            return f"[TABLE p{p.get('page')}]\n{p.get('raw_text', '')}"
        if t == "Picture":
            cap = p.get("caption") or ""
            return f"[PICTURE p{p.get('page')}]" + (f" {cap}" if cap else "")
        if t == "Diagram":
            return f"[DIAGRAM p{p.get('page')}]"
        if t == "Footnote":
            return f"[FN {p.get('refnum')}]: {p.get('content', '')}"
        if t == "Sidenote":
            return f"[SIDENOTE p{p.get('page')}] {p.get('content', '')}"
        if t == "ListItem":
            marker = p.get("marker") or "-"
            return f"  {marker} {p.get('content', '')}"
        if t == "Toc":
            return "[TABLE OF CONTENTS]\n" + "\n".join(p.get("entries", []))
        return ""
