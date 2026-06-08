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
  - `include_meta`:          whether to prepend a YAML front-matter header with
                             title/author/date/tags/description + pdfdrill status
                             info (bibkey, arxiv id, pages, element counts)
                             (default True)
"""
from __future__ import annotations

import re

from docmodel.core import Document, DocObject
from ..base import BaseProjector
from .common import flow_ordered_content, equation_label


def _yaml_scalar(v) -> str:
    """Render a scalar as safe YAML: quote it when it could be misparsed."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = (
        s == ""
        or s.strip() != s
        or s[0] in "!&*?|>%@`\"'#-[{ "
        or bool(re.search(r'[:#\[\]{},\n]', s))
        or s.lower() in ("true", "false", "null", "yes", "no", "~")
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


# Prose object type -> the field that carries a `<field>_source` backup when the
# model has been translated in place (so the projector can render both layers).
_BILAYER_FIELD = {
    "Paragraph": "text", "Abstract": "text",
    "Footnote": "content", "Sidenote": "content", "ListItem": "content",
    "Section": "caption",
}


def _bilayer_header(src_lang: str, tgt_lang: str) -> str:
    """Raw HTML/CSS for a browser show/hide toggle of the source layer. Default
    is translation-only (clean reading); the button reveals the source."""
    src = src_lang or "source"
    return (
        "<style>\n"
        ".seg.source{display:none;opacity:.75;border-left:3px solid #bbb;"
        "padding-left:.6em;margin:.3em 0}\n"
        "body.show-source .seg.source{display:block}\n"
        "</style>\n"
        "<button onclick=\"document.body.classList.toggle('show-source')\">"
        f"Toggle {src} source</button>"
    )


class LLMCompactProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".md"

    def project(self, doc: Document) -> str:
        formula_prefix = self.params.get("formula_placeholder", "F")
        equation_prefix = self.params.get("equation_placeholder", "E")
        repeat_threshold = int(self.params.get("repeat_threshold", 1))
        include_glossary = bool(self.params.get("include_glossary", True))
        include_meta = bool(self.params.get("include_meta", True))
        # Bi-layer: when the model was translated in place (prose objects carry a
        # `<field>_source` backup), render BOTH the translation and the source,
        # wrapped in HTML divs a CSS/JS toggle can show/hide.
        bilayer = bool(self.params.get("bilayer", False))
        src_lang = self.params.get("source_lang") or ""
        tgt_lang = self.params.get("target_lang") or ""
        # Opt-in (test path): rewrite in-text "(N)" refs to the equation's
        # compact placeholder. Off by default so the markdown stays clean.
        eq_refs = bool(self.params.get("eq_refs", False))

        # First pass: assign placeholders by deduplicated LaTeX content.
        # Formulas already deduplicate during conversion, but we still index
        # by `latex` here so that two identical fragments share a placeholder
        # even if they came from different DocObjects.
        formula_map: dict[str, str] = {}        # latex -> placeholder
        formula_uses: dict[str, int] = {}       # placeholder -> count
        equation_map: dict[str, str] = {}       # eq.id -> placeholder
        equation_latex: dict[str, str] = {}     # placeholder -> latex (expanded)
        # placeholder -> verbatim author source (only when it differs from the
        # expanded form, i.e. the formula used a private macro).
        macro_orig: dict[str, str] = {}

        for obj in flow_ordered_content(doc):
            if obj.type == "Formula":
                latex = obj.props.get("latex", "")
                if not latex:
                    continue
                if latex not in formula_map:
                    formula_map[latex] = f"{formula_prefix}{len(formula_map) + 1}"
                ph = formula_map[latex]
                formula_uses[ph] = formula_uses.get(ph, 0) + 1
                orig = obj.props.get("latex_original", "")
                if orig and orig.strip() != latex.strip():
                    macro_orig.setdefault(ph, orig)
            elif obj.type == "Equation":
                ph = f"{equation_prefix}{len(equation_map) + 1}"
                equation_map[obj.id] = ph
                equation_latex[ph] = obj.props.get("latex", "")
                orig = obj.props.get("latex_original", "")
                if orig and orig.strip() != obj.props.get("latex", "").strip():
                    macro_orig[ph] = orig

        # Map "(N)" -> equation placeholder for in-text reference rewriting.
        eqref_to_ph: list[tuple[str, str]] = []
        if eq_refs:
            for obj in doc.objects.values():
                if obj.type == "Equation" and obj.props.get("equation_number"):
                    ph = equation_map.get(obj.id)
                    if ph:
                        eqref_to_ph.append((obj.props["equation_number"], ph))
            eqref_to_ph.sort(key=lambda kv: -len(kv[0]))

        # Second pass: render in flow order.
        out: list[str] = []
        if include_meta:
            out.append(self._front_matter(doc))
            out.append("")
        if bilayer:
            out.append(_bilayer_header(src_lang, tgt_lang))
            out.append("")

        # Track which placeholders we've shown inline so the glossary can
        # skip those that are 0-shot (shouldn't happen but defensive).
        seen_placeholders: set[str] = set()
        seen_equations: set[str] = set()

        for obj in flow_ordered_content(doc):
            kw = dict(
                formula_map=formula_map, formula_uses=formula_uses,
                repeat_threshold=repeat_threshold,
                equation_map=equation_map,
                seen_placeholders=seen_placeholders,
                seen_equations=seen_equations,
                eqref_to_ph=eqref_to_ph,
            )
            field = _BILAYER_FIELD.get(obj.type)
            if bilayer and field and (field + "_source") in obj.props:
                # render the translation (props[field]) and the source backup
                trans = self._render_block(obj, doc, **kw)
                keep = obj.props[field]
                obj.props[field] = obj.props[field + "_source"]
                source = self._render_block(obj, doc, **kw)
                obj.props[field] = keep
                block = (
                    f'<div class="seg trans" lang="{tgt_lang}">\n\n{trans}\n\n</div>\n'
                    f'<div class="seg source" lang="{src_lang}">\n\n{source}\n\n</div>'
                )
            else:
                block = self._render_block(obj, doc, **kw)
            if block:
                out.append(block)
                out.append("")
            self.bump(f"emitted_{obj.type}")

        if include_glossary:
            out.append(self._render_glossary(
                formula_map, formula_uses, equation_map, equation_latex,
                repeat_threshold=repeat_threshold, macro_orig=macro_orig,
            ))
        return "\n".join(out).rstrip() + "\n"

    def _front_matter(self, doc: Document) -> str:
        """A YAML front-matter block: bibliographic fields (title/author/date/
        tags/description) plus pdfdrill status info (bibkey, arxiv id, pages, and
        per-type element counts). Emitted at the very top so the markdown is a
        valid YAML-front-matter document."""
        from collections import Counter
        meta = doc.meta
        counts = Counter(o.type for o in doc.objects.values())

        title = meta.get("title") or meta.get("bibkey") or "Document"
        authors = meta.get("authors")
        if isinstance(authors, (list, tuple)):
            authors = ", ".join(str(a) for a in authors)
        # description ← the document's Abstract (single line, truncated)
        desc = ""
        for o in doc.objects.values():
            if o.type == "Abstract":
                desc = " ".join((o.props.get("text") or "").split())[:240]
                break
        tags = ["pdfdrill"]
        for t in (meta.get("primary_category"), meta.get("bibkey")):
            if t and t not in tags:
                tags.append(t)

        lines = ["---"]

        def emit(key, val):
            if val not in (None, "", []):
                lines.append(f"{key}: {_yaml_scalar(val)}")

        emit("title", title)
        emit("author", authors)
        emit("date", meta.get("date") or meta.get("year"))
        lines.append("tags: [" + ", ".join(_yaml_scalar(t) for t in tags) + "]")
        emit("description", desc)
        # --- pdfdrill status info ---
        emit("bibkey", meta.get("bibkey"))
        emit("arxiv_id", meta.get("arxiv_id"))
        emit("primary_category", meta.get("primary_category"))
        emit("pages", meta.get("num_pages") or meta.get("pages"))
        for typ, label in (("Section", "sections"), ("Equation", "equations"),
                           ("Formula", "formulas"), ("Picture", "figures"),
                           ("Table", "tables"), ("Reference", "references")):
            if counts.get(typ):
                lines.append(f"{label}: {counts[typ]}")
        lines.append("generator: pdfdrill")
        lines.append("---")
        return "\n".join(lines)

    def _render_block(
        self, obj: DocObject, doc: Document, *,
        formula_map: dict[str, str], formula_uses: dict[str, int],
        repeat_threshold: int,
        equation_map: dict[str, str],
        seen_placeholders: set[str], seen_equations: set[str],
        eqref_to_ph: list = (),
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
            text = p.get("text") or ""
            for eqnum, ph in eqref_to_ph:
                if eqnum in text:
                    text = text.replace(eqnum, f"[{ph}]")
                    self.bump("eq_ref_subs")
            return text
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
            if p.get("subtype") == "code":
                lang = p.get("language") or ""
                return f"```{lang}\n{p.get('code', '')}\n```"
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
        *, repeat_threshold: int, macro_orig: dict[str, str] | None = None,
    ) -> str:
        macro_orig = macro_orig or {}

        def _src(ph: str) -> str:
            # show the verbatim macro source after the expanded form, when the
            # formula used a private macro (so both versions survive the projection)
            o = macro_orig.get(ph)
            return f"  · macro source: `{o}`" if o else ""

        lines: list[str] = ["---", "## Glossary"]
        if formula_map:
            lines.append("\n### Inline formulas")
            # Sort by placeholder number so the glossary is stable.
            for latex, ph in sorted(formula_map.items(), key=lambda kv: int(kv[1][1:])):
                if formula_uses.get(ph, 0) < repeat_threshold:
                    continue
                uses = formula_uses.get(ph, 0)
                lines.append(f"- **{ph}** ({uses}×): `{latex}`{_src(ph)}")
        if equation_map:
            lines.append("\n### Display equations")
            for eq_id, ph in sorted(equation_map.items(), key=lambda kv: int(kv[1][1:])):
                lines.append(f"- **{ph}**: `{equation_latex.get(ph, '')}`{_src(ph)}")
        return "\n".join(lines)
