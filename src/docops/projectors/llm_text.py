"""
LLMTextProjector — a flat, delimiter-separated dump for an LLM.

One unit per paragraph and per formula, in document (flow) order. Each unit is

    <tiddler-style title>
    <content>

and units are separated by a configurable delimiter (default ``%%%%``). The
content is the paragraph TEXT or the formula LATEX — nothing else (no markup,
no transclusion tokens, no provenance), so an LLM sees clean, addressable
units it can quote by title.

Two corpus-quality rules baked in:
  * **A LaTeX paragraph is ONE block.** MathPix sometimes returns several
    logical paragraphs (double-line-break separated) as a single object; with
    ``split_paragraphs`` (default True) each block becomes its own unit, the
    title suffixed ``#1``/``#2`` so it stays addressable.
  * **Empty/null formulas are skipped.** A formula whose latex is ``""``/
    ``null``/``None`` carries only a CDN crop — nothing to read; emitting its
    title with no body would be noise.

Titles match the TiddlyWiki projector (``<bibkey>_PARA_<NNNN>`` /
``<bibkey>_EQ<NNNN>_p<NNN>`` / ``<bibkey>_FO<NNNN>``) so a unit here points at
the same tiddler.

params: ``delimiter`` (default ``%%%%``), ``split_paragraphs`` (default True).
"""
from __future__ import annotations

import re

from docmodel.core import Document
from ..base import BaseProjector

_DBL = re.compile(r"\n\s*\n")
_NULLISH = {"", "null", "none"}


def _is_empty_latex(latex) -> bool:
    return latex is None or str(latex).strip().lower() in _NULLISH


class LLMTextProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".llm.txt"

    def _titles(self, doc: Document) -> dict[str, str]:
        """Tiddler-compatible titles, per-type 1-based in flow order."""
        bib = doc.meta.get("bibkey", "DOC")
        flow = lambda o: o.props.get("flow_index") or 0
        title: dict[str, str] = {}
        for i, p in enumerate(sorted(doc.objects_of_type("Paragraph"), key=flow), 1):
            title[p.id] = f"{bib}_PARA_{i:04d}"
        for i, e in enumerate(sorted(doc.objects_of_type("Equation"), key=flow), 1):
            title[e.id] = f"{bib}_EQ{i:04d}_p{int(e.props.get('page') or 0):03d}"
        for i, f in enumerate(sorted(doc.objects_of_type("Formula"), key=flow), 1):
            title[f.id] = f"{bib}_FO{i:04d}"
        return title

    def project(self, doc: Document) -> str:
        delimiter = self.params.get("delimiter", "%%%%")
        split = self.params.get("split_paragraphs", True)
        titles = self._titles(doc)

        units: list[tuple[float, str, str]] = []   # (flow_index, title, content)
        for o in doc.objects.values():
            fi = o.props.get("flow_index") or 0
            if o.type == "Paragraph":
                text = (o.props.get("text") or "").strip()
                if not text:
                    continue
                blocks = [b.strip() for b in _DBL.split(text) if b.strip()] if split \
                    else [text]
                if len(blocks) == 1:
                    units.append((fi, titles[o.id], blocks[0]))
                else:
                    for k, b in enumerate(blocks, 1):
                        units.append((fi, f"{titles[o.id]}#{k}", b))
            elif o.type in ("Equation", "Formula"):
                latex = o.props.get("latex")
                if _is_empty_latex(latex):
                    continue
                units.append((fi, titles[o.id], str(latex).strip()))

        units.sort(key=lambda u: (u[0], u[1]))
        sep = f"\n{delimiter}\n"
        return sep.join(f"{t}\n{c}" for _fi, t, c in units)
