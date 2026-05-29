"""
LLMCompactProjector — token-optimized markdown for LLM ingestion.

The strategy is to keep the prose intact, but replace every LaTeX-bearing
fragment (Formulas, Equations) with a short numeric placeholder. A glossary
at the end of the document maps placeholders back to the original LaTeX.

For a typical mathematical paper this can cut the LLM-side token cost by
20–40% because long formulas appear once in the glossary instead of being
re-encoded everywhere they occur.

Tunable params (in `params` on the config entry):
  - `formula_placeholder`:   prefix for inline formulas, default 'F'
  - `equation_placeholder`:  prefix for display equations, default 'E'
  - `repeat_threshold`:      formulas appearing fewer than this many times
                             are inlined instead of placehold (default 1,
                             i.e. always placeholderize; set to 2 to inline
                             one-shot formulas).
  - `include_glossary`:      whether to append the glossary (default True)
  - `include_meta`:          whether to add a small front-matter (default True)
"""
from __future__ import annotations

from docmodel.core import Document, DocObject
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label


class LLMCompactProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".md"

    def project(self, doc: Document) -> str:
        formula_prefix = self.params.get("formula_placeholder", "F")
        equation_prefix = self.params.get("equation_placeholder", "E")
        repeat_threshold = int(self.params.get("repeat_threshold", 1))
        include_glossary = bool(self.params.get("include_glossary", True))
        include_meta = bool(self.params.get("include_meta", True))

        # First pass: assign placeholders by deduplicated LaTeX content.
        # Formulas already deduplicate during conversion, but we still index
        # by `latex` here so that two identical fragments share a placeholder
        # even if they came from different DocObjects.
        formula_map: dict[str, str] = {}        # latex -> placeholder
        formula_uses: dict[str, int] = {}       # placeholder -> count
        equation_map: dict[str, str] = {}       # eq.id -> placeholder
        equation_latex: dict[str, str] = {}     # placeholder -> latex

        for obj in flow_ordered_content(doc):
            if obj.type == "Formula":
                latex = obj.props.get("latex", "")
                if not latex:
                    continue
                if latex not in formula_map:
                    formula_map[latex] = f"{formula_prefix}{len(formula_map) + 1}"
                ph = formula_map[latex]
                formula_uses[ph] = formula_uses.get(ph, 0) + 1
            elif obj.type == "Equation":
                ph = f"{equation_prefix}{len(equation_map) + 1}"
                equation_map[obj.id] = ph
                equation_latex[ph] = obj.props.get("latex", "")

        # Second pass: render in flow order.
        out: list[str] = []
        if include_meta:
            meta = doc.meta
            out.append(f"# {meta.get('bibkey', 'Document')}")
            if meta.get("num_pages"):
                out.append(f"_{meta['num_pages']} pages_")
            out.append("")

        # Track which placeholders we've shown inline so the glossary can
        # skip those that are 0-shot (shouldn't happen but defensive).
        seen_placeholders: set[str] = set()
        seen_equations: set[str] = set()

        for obj in flow_ordered_content(doc):
            block = self._render_block(
                obj, doc,
                formula_map=formula_map, formula_uses=formula_uses,
                repeat_threshold=repeat_threshold,
                equation_map=equation_map,
                seen_placeholders=seen_placeholders,
                seen_equations=seen_equations,
            )
            if block:
                out.append(block)
                out.append("")
            self.bump(f"emitted_{obj.type}")

        if include_glossary:
            out.append(self._render_glossary(
                formula_map, formula_uses, equation_map, equation_latex,
                repeat_threshold=repeat_threshold,
            ))
        return "\n".join(out).rstrip() + "\n"

    def _render_block(
        self, obj: DocObject, doc: Document, *,
        formula_map: dict[str, str], formula_uses: dict[str, int],
        repeat_threshold: int,
        equation_map: dict[str, str],
        seen_placeholders: set[str], seen_equations: set[str],
    ) -> str:
        t = obj.type
        p = obj.props
        if t == "Section":
            depth = p.get("level", 1)
            num = p.get("section_number") or ""
            cap = p.get("caption") or ""
            return f"{'#' * max(1, min(6, depth))} {num} {cap}".strip()
        if t == "Abstract":
            return "**Abstract.** " + p.get("text", "")
        if t == "Paragraph":
            return p.get("text") or ""
        if t == "Equation":
            ph = equation_map.get(obj.id, "?")
            ref = equation_label(obj)
            ref_part = f" ({ref})" if ref else ""
            seen_equations.add(ph)
            return f"[{ph}]{ref_part}"
        if t == "Formula":
            latex = p.get("latex", "")
            ph = formula_map.get(latex)
            if ph and formula_uses.get(ph, 0) >= repeat_threshold:
                seen_placeholders.add(ph)
                return f"[{ph}]"
            # Inline rare formulas.
            return f"`{latex}`"
        if t == "ListItem":
            marker = p.get("marker") or "-"
            content = p.get("content", "")
            # Bullet/numbered markers render as a plain "- "; keep an explicit
            # marker (e.g. "a)") verbatim.
            is_bullet_or_numbered = marker.isalnum() or marker[:1] in "123456789"
            return f"- {content}" if is_bullet_or_numbered else f"{marker} {content}"
        if t == "Table":
            return f"_table on p{p.get('page')}_\n```\n{p.get('raw_text', '')}\n```"
        if t == "Picture":
            cap = p.get("caption") or ""
            label = (cap or f"figure on p{p.get('page')}").strip()
            return f"_({label})_"
        if t == "Diagram":
            return f"_(diagram on p{p.get('page')})_"
        if t == "Footnote":
            return f"^{p.get('refnum')}: {p.get('content', '')}"
        if t == "Sidenote":
            return f"_sidenote: {p.get('content', '')}_"
        if t == "Toc":
            return ""  # TOC is redundant in the compact view
        return ""

    def _render_glossary(
        self,
        formula_map: dict[str, str],
        formula_uses: dict[str, int],
        equation_map: dict[str, str],
        equation_latex: dict[str, str],
        *, repeat_threshold: int,
    ) -> str:
        lines: list[str] = ["---", "## Glossary"]
        if formula_map:
            lines.append("\n### Inline formulas")
            # Sort by placeholder number so the glossary is stable.
            for latex, ph in sorted(formula_map.items(), key=lambda kv: int(kv[1][1:])):
                if formula_uses.get(ph, 0) < repeat_threshold:
                    continue
                uses = formula_uses.get(ph, 0)
                lines.append(f"- **{ph}** ({uses}×): `{latex}`")
        if equation_map:
            lines.append("\n### Display equations")
            for eq_id, ph in sorted(equation_map.items(), key=lambda kv: int(kv[1][1:])):
                lines.append(f"- **{ph}**: `{equation_latex.get(ph, '')}`")
        return "\n".join(lines)
