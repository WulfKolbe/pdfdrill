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
from .common import flow_ordered_content, equation_label, theorem_head

#: The types this projector renders beyond `common.CONTENT_TYPES`, named here
#: because `_render` has a branch for each. See `CONTENT_TYPES`.
_EXTRA_FLOW_TYPES = ("Theorem", "Proof", "Algorithm")


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

        for obj in flow_ordered_content(doc, types=_EXTRA_FLOW_TYPES):
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
        if t in ("Theorem", "Proof"):
            body = str(p.get("statement") or "").strip()
            if not body:
                return ""
            head = (str(p.get("name") or "").strip().rstrip(".") or "Proof"
                    ) if t == "Proof" else theorem_head(obj)
            # `[CODE py p4]`'s shape: the TAG upper-cased, the detail as the
            # document writes it. Upper-casing the whole head would rewrite the
            # author's own bracket title ("(Hirzebruch)" → "(HIRZEBRUCH)").
            kind, _, rest = head.partition(" ")
            tag = kind.upper() + (f" {rest}" if rest else "")
            return f"[{tag}]\n{body}"
        if t == "Algorithm":
            return self._algorithm(obj, doc)
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
            if p.get("subtype") == "code":
                lang = p.get("language") or ""
                return f"[CODE{(' ' + lang) if lang else ''} p{p.get('page')}]\n{p.get('code', '')}"
            return f"[DIAGRAM p{p.get('page')}]"
        if t == "Footnote":
            return f"[FN {p.get('refnum')}]: {p.get('content', '')}"
        if t == "Sidenote":
            return f"[SIDENOTE p{p.get('page')}] {p.get('content', '')}"
        if t == "ListItem":
            marker = p.get("marker") or "-"
            return f"  {marker} {p.get('content', '')}"
        if t == "Toc":
            # 262 — KEPT deliberately. This projection is a faithful dump of
            # what the page holds, and the page holds a table of contents.
            # (TiddlyWiki omits it and rebuilds by filter; see toc.py.)
            # 263 — render from `rows` so the page number survives the leader
            # being stripped. `entries` alone would drop it.
            rows = p.get("rows")
            if rows:
                out = []
                for r in rows:
                    title = (r.get("title") or "").strip()
                    loc = (r.get("locator") or "").strip()
                    if not title and not loc:
                        continue
                    out.append(f"{title}  {loc}".strip() if loc else title)
                return "[TABLE OF CONTENTS]\n" + "\n".join(out)
            return "[TABLE OF CONTENTS]\n" + "\n".join(p.get("entries", []))
        return ""

    def _algorithm(self, obj, doc: Document) -> str:
        """`[ALGORITHM 1 Label it]` and its steps, indented by nesting depth.

        The steps are reached through `children`, else by their own `parent`:
        `cmd_algorithms` and `latex_source` both build them, and an Algorithm
        whose steps arrived by only one of those routes is still an Algorithm.
        Depth is kept because a nested step is a step OF the step above it —
        flattening them loses the loop body.
        """
        p = obj.props
        num = str(p.get("number") or "").strip()
        title = str(p.get("title") or p.get("caption") or "").strip()
        head = " ".join(x for x in ("ALGORITHM", num, title) if x)
        steps = [doc.objects[i] for i in (obj.children or [])
                 if i in doc.objects and doc.objects[i].type == "AlgorithmStep"]
        if not steps:
            steps = [o for o in doc.objects.values()
                     if o.type == "AlgorithmStep"
                     and getattr(o, "parent", None) == obj.id]
        rows: list[str] = []
        for st in steps:
            body = str(st.props.get("text") or st.props.get("content")
                       or "").strip()
            if not body:
                continue
            try:
                depth = max(0, int(st.props.get("depth") or 0))
            except (TypeError, ValueError):
                depth = 0
            rows.append(f"{'  ' * (depth + 1)}{len(rows) + 1}. {body}")
        return f"[{head}]" + ("\n" + "\n".join(rows) if rows else "")
