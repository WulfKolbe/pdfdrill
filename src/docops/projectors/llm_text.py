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


#: The types this dump names, in the order it numbers them.
_TITLED_TYPES = ("Paragraph", "Equation", "Formula", "Section", "Diagram",
                 "Picture", "Table")


def _title_map(objs, bibkey: str, key=None) -> dict:
    """`{object id: tiddler title}` in flow order, per type.

    644 — the SHAPES come from `TITLE_SHAPES` via `title_for`, not from format
    strings here. The copy that lived here had `{b}_H{i}` for a Section, which
    the projector stopped emitting at 566 (it pads to four digits, so `_H10`
    sorts after `_H2`): every Section pointer this dump produced named a
    tiddler that does not exist.
    """
    from .tiddlywiki import title_for

    if key is None:
        def key(o):                                  # flow_index may be str ("190")
            try:
                return float(o.props.get("flow_index") or 0)
            except (TypeError, ValueError):
                return 0.0
    objs = list(objs)
    out: dict = {}
    for typ in _TITLED_TYPES:
        for i, o in enumerate(sorted((x for x in objs if x.type == typ),
                                     key=key), 1):
            out[o.id] = title_for(bibkey, typ, i)
    return out


def build_llm_text(objects, meta, *, delimiter: str = "%%%%",
                   split_paragraphs: bool = True) -> str:
    """Pure core: render the LLM dump from any iterable of nodes exposing
    `.type` / `.id` / `.props` — satisfied by BOTH `DocObject` (full model) and
    `DocGraph.GraphNode` (the lazy packed read-path), so the fast loader and the
    canonical loader produce byte-identical output."""
    objs = list(objects)
    bib = (meta or {}).get("bibkey", "DOC")

    def flow(o):                                     # flow_index may be str ("190")
        try:
            return float(o.props.get("flow_index") or 0)
        except (TypeError, ValueError):
            return 0.0

    title = _title_map(objs, bib, key=flow)

    units: list[tuple[float, str, str]] = []
    for o in objs:
        fi = flow(o)
        if o.type == "Section":
            cap = (o.props.get("caption") or o.props.get("title") or "").strip()
            if not cap:
                continue
            refnum = str(o.props.get("refnum") or "").strip()
            units.append((fi, title[o.id], f"# {(refnum + ' ' + cap).strip()}"))
        elif o.type in ("Diagram", "Picture", "Table"):
            # figures/tables/algorithms are referenceable: caption + the readable
            # body (a code-subtype Diagram is a MathPix 'Algorithm N' box).
            cap = (o.props.get("caption") or "").strip()
            body = ""
            if o.props.get("subtype") == "code" and o.props.get("code"):
                lang = o.props.get("language") or ""
                body = f"```{lang}\n{str(o.props['code']).strip()}\n```"
            elif str(o.props.get("latex_code") or "").strip():
                body = str(o.props["latex_code"]).strip()
            elif str(o.props.get("raw_text") or "").strip():
                body = str(o.props["raw_text"]).strip()
            elif o.props.get("cdn_url"):
                body = f"[image: {o.props['cdn_url']}]"
            content = "\n".join(x for x in (cap, body) if x)
            if content:
                units.append((fi, title[o.id], content))
        elif o.type == "Paragraph":
            text = (o.props.get("text") or "").strip()
            if not text:
                continue
            blocks = [b.strip() for b in _DBL.split(text) if b.strip()] if split_paragraphs \
                else [text]
            if len(blocks) == 1:
                units.append((fi, title[o.id], blocks[0]))
            else:
                for k, b in enumerate(blocks, 1):
                    units.append((fi, f"{title[o.id]}#{k}", b))
        elif o.type in ("Equation", "Formula"):
            latex = o.props.get("latex")
            if _is_empty_latex(latex):
                continue
            units.append((fi, title[o.id], str(latex).strip()))

    units.sort(key=lambda u: (u[0], u[1]))
    sep = f"\n{delimiter}\n"
    return sep.join(f"{t}\n{c}" for _fi, t, c in units)


class LLMTextProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".llm.txt"

    def project(self, doc: Document) -> str:
        return build_llm_text(doc.objects.values(), doc.meta,
                              delimiter=self.params.get("delimiter", "%%%%"),
                              split_paragraphs=self.params.get("split_paragraphs", True))
