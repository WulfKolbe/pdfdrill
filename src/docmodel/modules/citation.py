"""
CitationProcessor (procOrder 3).

Scans body text lines for `[citekey]` patterns (the MathPix convention for
citations) and creates Citation DocObjects. The realization for each citation
points to the line anchor in `mathpix_lines` PLUS offset/length props giving
the sub-line position. This avoids creating per-character anchors for the
entire body while still preserving exact location.

If you later promote body text to character-level anchors, the citation's
realization can be upgraded by replacing the offset/length props with explicit
start/end anchors — no surrounding structure has to change.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


# Matches [citekey], where citekey contains letters, digits, _, - and contains
# no LaTeX backslashes (avoids picking up `\cite[opt]{key}` artifacts).
_CITE = re.compile(r"\[([A-Za-z0-9_\-,;:\s]+?)\]")

# Inline/display math spans. A `[...]` inside one of these is math (e.g.
# `\([A x, B x]\)` — an interval, MathPix's render of `[A_x, B_x]`), NOT a
# citation. Longest delimiters first so `$$` isn't split as `$..$`.
_MATH_SPAN = re.compile(
    r"\\\[[\s\S]*?\\\]"          # \[ ... \]
    r"|\$\$[\s\S]*?\$\$"         # $$ ... $$
    r"|\\\([\s\S]*?\\\)"         # \( ... \)
    r"|\$(?:[^$\n]|\\\$)*?\$"    # $ ... $
)


def _math_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _MATH_SPAN.finditer(text)]


def _in_math(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in ranges)


def _is_valid_citekey(citekey: str) -> bool:
    """The TS heuristic, slightly relaxed for multi-citation comma lists."""
    if "\\" in citekey:
        return False
    if not citekey.strip():
        return False
    # Must contain at least one letter (so we skip [1], [2.3], pure-numeric refs
    # which are typically equation numbers handled elsewhere).
    if not re.search(r"[A-Za-z]", citekey):
        return False
    return True


class CitationProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") not in ("text", "title"):
                continue
            text = payload.get("text_display") or payload.get("text") or ""
            if not text:
                continue
            math = _math_ranges(text)
            for match in _CITE.finditer(text):
                # A `[...]` inside a math span is an interval/set, not a cite.
                if _in_math(match.start(), math):
                    continue
                key = match.group(1).strip()
                if not _is_valid_citekey(key):
                    continue
                # The pattern may be a comma-separated list (e.g. [smith,jones]).
                # We create one Citation per key; their realizations all point
                # to the same anchor + sub-range.
                offsets = self._split_offsets(key, match)
                for sub_key, sub_off, sub_len in offsets:
                    items.append({
                        "citekey": sub_key,
                        "anchor": anchor,
                        "offset": sub_off,
                        "length": sub_len,
                        "page": payload.get("_page"),
                        "line_id": payload.get("id"),
                    })
        return items

    @staticmethod
    def _split_offsets(group_text: str, match: re.Match) -> list[tuple[str, int, int]]:
        """Split a citation group `[a, b, c]` into individual (key, off, len)."""
        out: list[tuple[str, int, int]] = []
        base = match.start() + 1  # skip past '['
        cursor = 0
        for raw_part in group_text.split(","):
            stripped = raw_part.strip()
            if not stripped or "\\" in stripped:
                cursor += len(raw_part) + 1  # +1 for the comma we ate
                continue
            # find stripped's offset within raw_part
            lead = len(raw_part) - len(raw_part.lstrip())
            out.append((stripped, base + cursor + lead, len(stripped)))
            cursor += len(raw_part) + 1
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Citation",
            props={
                "citekey": item["citekey"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
            props={
                "offset": item["offset"],   # sub-anchor character position
                "length": item["length"],
            },
        ))
        self.bump("citations_created")
        return obj
