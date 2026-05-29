"""
FormulaProcessor (procOrder 12).

Inline math fragments inside text lines: `$ ... $`, `\\( ... \\)`,
`$$ ... $$`, `\\[ ... \\]`. Each becomes a Formula DocObject with a
character-level LaTeX stream, just like Equation but without the equation
number / standalone-line treatment.

Sub-line position is preserved on the realization via offset/length props
(same pattern as CitationProcessor). De-duplication: identical LaTeX content
yields one Formula DocObject with multiple realizations.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


# Longest patterns first so $$..$$ is not mistaken as $..$.
_MATH_RE = re.compile(
    r"\\\[[\s\S]*?\\\]"          # \[ ... \]
    r"|\$\$[\s\S]*?\$\$"         # $$ ... $$
    r"|\\\([\s\S]*?\\\)"         # \( ... \)
    r"|\$(?:[^$\n]|\\\$)*?\$"    # $ ... $
)


def _strip_delims(s: str) -> tuple[str, bool]:
    """Return (latex_body, is_display)."""
    if s.startswith("\\[") and s.endswith("\\]"):
        return s[2:-2], True
    if s.startswith("$$") and s.endswith("$$"):
        return s[2:-2], True
    if s.startswith("\\(") and s.endswith("\\)"):
        return s[2:-2], False
    if s.startswith("$") and s.endswith("$"):
        return s[1:-1], False
    return s, False


class FormulaProcessor(BaseModule):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # canonical latex -> Formula DocObject (for de-duplication).
        self._dedupe: dict[str, DocObject] = {}

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            ltype = payload.get("type")
            # Skip display equations (handled by EquationProcessor).
            if ltype in ("equation", "math"):
                continue
            text = payload.get("text_display") or payload.get("text") or ""
            if not text:
                continue
            for m in _MATH_RE.finditer(text):
                body, is_display = _strip_delims(m.group(0))
                body = re.sub(r"\s+", " ", body).strip()
                if not body:
                    continue
                items.append({
                    "anchor": anchor,
                    "latex": body,
                    "display": is_display,
                    "offset": m.start(),
                    "length": m.end() - m.start(),
                    "page": payload.get("_page"),
                })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        latex = item["latex"]
        if latex in self._dedupe:
            existing = self._dedupe[latex]
            # Just add an extra realization for this location.
            existing.add_realization(Realization(
                stream=self.LINES_STREAM,
                start=item["anchor"], end=item["anchor"],
                role="surface",
                props={"offset": item["offset"], "length": item["length"]},
            ))
            return None  # don't re-add

        fo_no = self.bump("formulas_created")
        latex_stream_name = f"latex_fo_{fo_no:04d}"
        latex_stream = doc.ensure_stream(latex_stream_name)
        char_anchors = [latex_stream.append(codepoint=ch) for ch in latex]

        obj = DocObject(
            type="Formula",
            props={
                "latex": latex,
                "display": item["display"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
            props={"offset": item["offset"], "length": item["length"]},
        ))
        if char_anchors:
            obj.add_realization(Realization(
                stream=latex_stream_name,
                start=char_anchors[0], end=char_anchors[-1],
                role="latex_source",
            ))
        self._dedupe[latex] = obj
        return obj
