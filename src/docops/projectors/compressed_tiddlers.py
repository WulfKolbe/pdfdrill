"""
CompressedTiddlersProjector — token-optimized tiddler-like format.

Produces a single text file of records separated by `%%%%`. Each record is:

    %%%%
    <title>
    <body>

The `body` preserves all `{{title||TEMPLATE}}` transclusions from the
TiddlyWiki output, but field metadata (created/modified/tags/page/...) is
stripped. The result reads naturally as text yet is fully addressable by
title — every transclusion target appears as its own block.

For an LLM, this format is roughly 4× more token-efficient than the JSON
tiddlers, because all the structural overhead of JSON (`"text":`, escaped
newlines, field repetition) goes away. Anything the LLM might want to
"follow" — a citation, a formula, a footnote — is just one block away,
addressed by name, no JSON traversal required.

Internally this projector calls `TiddlyWikiProjector` to do the heavy
lifting (transclusion substitution, synthetic-formula extraction,
title-scheme assignment), then re-serializes the result. That keeps the
two projectors in lockstep: if the tiddler logic improves, the compressed
form benefits automatically.

Tunable params (in `params` on the config entry):

    delimiter           Record separator. Default '%%%%'.
    sep_newlines        Newlines between delimiter and title. Default 1.
    include_kinds       Tiddler kinds to include. Default: a curated list
                        (paragraph, formula, equation, citation, footnote,
                        synthetic, picture, diagram, table, listitem,
                        section, abstract, toc, sidenote, document).
                        Pages and templates are excluded by default.
    formula_as_latex    For formula/equation tiddlers, render the LaTeX
                        body directly instead of the `<$latex .../>` macro.
                        Default True — this is the form most LLMs prefer.
    body_strip          Strip leading/trailing whitespace from each body.
                        Default True.
    drop_empty          Skip tiddlers whose body is empty. Default True.
"""
from __future__ import annotations

import json

from docmodel.core import Document
from ..base import BaseProjector, OperatorConfig
from .tiddlywiki import TiddlyWikiProjector


_DEFAULT_KINDS = {
    "paragraph", "formula", "equation", "citation", "footnote",
    "synthetic", "picture", "diagram", "table", "listitem",
    "section", "abstract", "toc", "sidenote", "document",
}

# Kinds where the !!latex field is the substance.
_LATEX_KINDS = {"formula", "equation"}


class CompressedTiddlersProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".tiddlers.txt"

    def project(self, doc: Document) -> str:
        delimiter = self.params.get("delimiter", "%%%%")
        sep_newlines = int(self.params.get("sep_newlines", 1))
        include_kinds = set(self.params.get("include_kinds", _DEFAULT_KINDS))
        formula_as_latex = bool(self.params.get("formula_as_latex", True))
        body_strip = bool(self.params.get("body_strip", True))
        drop_empty = bool(self.params.get("drop_empty", True))

        # Reuse the TiddlyWiki projector: it builds the tiddler array
        # (titles, transclusions, synthetic formulas) and we re-serialize.
        tw = TiddlyWikiProjector(OperatorConfig(
            op="projector", classname="TiddlyWikiProjector", title="_internal_tw",
        ))
        tiddlers = json.loads(tw.project(doc))

        # Emit in a deterministic order: paragraphs in flow order first
        # (the bulk of the prose), then formulas/equations/citations/footnotes
        # grouped together (so an LLM finds related blocks near each other),
        # then everything else.
        ordered = self._order_tiddlers(tiddlers)

        sep = delimiter + ("\n" * sep_newlines)
        out_parts: list[str] = []
        emitted = 0

        for t in ordered:
            kind = self._first_kind(t)
            if kind not in include_kinds:
                self.bump(f"skipped_{kind or 'untagged'}")
                continue

            body = self._render_body(t, kind, formula_as_latex)
            if body_strip:
                body = body.strip()
            if drop_empty and not body:
                self.bump(f"empty_{kind}")
                continue

            out_parts.append(sep + t["title"] + "\n" + body + "\n")
            emitted += 1
            self.bump(f"emitted_{kind}")

        # Trailing delimiter so every block is bracketed cleanly.
        out_parts.append(delimiter + "\n")
        self.bump("total_records", emitted)
        return "".join(out_parts)

    # ----- ordering -----

    @staticmethod
    def _first_kind(t: dict) -> str:
        tags = t.get("tags") or ""
        parts = tags.split()
        return parts[0] if parts else ""

    @staticmethod
    def _order_tiddlers(tiddlers: list[dict]) -> list[dict]:
        """Group by kind, with paragraphs first (the prose flow), then
        the targets that paragraphs transclude (formulas/citations/...),
        then everything else. Within a group, preserve input order so that
        flow_index-derived sort survives."""
        priority = {
            "document":  0,
            "section":   1,
            "abstract":  2,
            "toc":       3,
            "paragraph": 4,
            "formula":   5,   # includes 'formula synthetic'
            "equation":  6,
            "citation":  7,
            "footnote":  8,
            "sidenote":  9,
            "listitem": 10,
            "table":    11,
            "picture":  12,
            "diagram":  13,
        }
        kind_of = CompressedTiddlersProjector._first_kind
        return [
            t for _, t in sorted(
                enumerate(tiddlers),
                key=lambda iv: (priority.get(kind_of(iv[1]), 99), iv[0]),
            )
        ]

    # ----- body rendering -----

    @staticmethod
    def _render_body(t: dict, kind: str, formula_as_latex: bool) -> str:
        """
        Render the body for one tiddler.

        For paragraph/section/abstract/listitem/etc., the natural text body
        is already in `text` and contains the transclusion macros from the
        TiddlyWiki projector.

        For formula/equation, we replace the `<$latex .../>` macro body with
        the raw LaTeX (wrapped in `$...$` or `$$...$$` so it's still readable
        as math by an LLM) — this is far more token-efficient and lets the
        LLM see the actual mathematical content directly.

        For citation placeholders, emit just the citekey.

        For footnote, the text already holds the resolved footnote content
        (parsed `\\footnotetext{...}` body).
        """
        if kind in _LATEX_KINDS and formula_as_latex:
            latex = t.get("latex", "")
            if not latex:
                return ""
            display = (t.get("displayMode") == "true") or (kind == "equation")
            refnum = (t.get("refnum") or "").strip()
            # Strip stray TeX backslashes / parens that may have come from
            # MathPix's `text_display` field for equation numbers.
            refnum = refnum.replace("\\(", "").replace("\\)", "")
            refnum = refnum.replace("\\[", "").replace("\\]", "")
            refnum = refnum.replace("\\", "").strip("() \t")
            if display:
                # $$ ... $$ for display; append refnum like (1.1) if known.
                if refnum:
                    return f"$$ {latex} $$ ({refnum})"
                return f"$$ {latex} $$"
            return f"${latex}$"

        if kind == "citation":
            return (t.get("citekey") or "").strip()

        if kind == "picture" or kind == "diagram":
            uri = t.get("canonical_uri") or ""
            cap = t.get("caption") or ""
            label_bits = []
            if cap:
                label_bits.append(cap)
            if uri:
                label_bits.append(f"<{uri}>")
            return " ".join(label_bits) or t.get("text", "")

        # Default: use the text field. This is where paragraphs carry their
        # transclusion-rich prose.
        return t.get("text", "")
