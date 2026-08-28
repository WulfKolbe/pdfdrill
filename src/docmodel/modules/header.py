"""
HeaderProcessor (procOrder 8).

Lines of type='section_header' usually have a single child carrying both a
clean caption (`text`) and a LaTeX command (`text_display`, e.g.
`\\section*{...}`). We create one Section DocObject per header with level,
caption, and command kind.

**259 — the level comes from `font_size` when there is no command.** Only 9,032
of the corpus's 43,160 section_header lines carry a `\\section`-family command;
the other 34,128 (79%) hit Strategy 3 and were all assigned level 1, so four
fifths of every heading tree was flat. MathPix states a pixel height on every
one of them. Ranking a document's OWN distinct header sizes, largest first,
gives the level directly — no threshold, no regex, and no cross-document
constant, because a size means nothing except relative to the other headers of
the same document.

The LaTeX command still wins wherever it exists: it is the author's own
statement of depth, and a font size is an inference from it. Lines with neither
a command nor a font size keep level 1.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_CMD_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^}]*)\}"
)
_CMD_ONLY_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?"
)

_LEVEL = {
    "section": 1, "subsection": 2, "subsubsection": 3,
    "paragraph": 4, "subparagraph": 5,
}

#: Deepest level a font-size rank may produce. Matches _LEVEL's range, so a
#: size-derived level is never deeper than a command-derived one can be.
_MAX_SIZE_LEVEL = 5


def levels_by_font_size(sizes: list) -> dict:
    """{font_size: level} for one document, biggest size = level 1.

    Ranked WITHIN the document. A 31px heading is a chapter title in one paper
    and a running subsection in another, so any absolute threshold would be a
    constant with no population behind it.
    """
    distinct = sorted({s for s in sizes if isinstance(s, (int, float)) and s > 0},
                      reverse=True)
    return {s: min(i + 1, _MAX_SIZE_LEVEL) for i, s in enumerate(distinct)}


class HeaderProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        # 259 — rank this document's own header sizes before assigning any
        # level, so a size-derived level is relative to its own document.
        by_size = levels_by_font_size([
            stream.payload[a].get("font_size") for a in stream.anchors
            if stream.payload[a].get("type") == "section_header"
        ])

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "section_header":
                continue
            # 265 — a header WITHOUT children is still a header. This used to
            # `continue`, and 34,126 of the corpus's 43,160 section_header
            # lines (79%) have no children: 'REFERENCES', '1. Introduction',
            # '4. Spin-foam models and loop quantum gravity' — captions in the
            # line's OWN text, with a font_size, producing no Section at all.
            # 629 documents had section headers and not one Section object.
            #
            # That is what a consumer means by calling Section "noisy and
            # ignored": the set it sees is missing four fifths of the headings,
            # so it looks arbitrary. The LaTeX-command path is unchanged; this
            # only adds the lines that were being dropped.
            kids = payload.get("children_ids") or []
            child = by_id.get(kids[0]) if kids else None
            if child is not None:
                child_text = child.get("text") or ""
                child_display = child.get("text_display") or ""
            else:
                child_text = payload.get("text") or ""
                child_display = payload.get("text_display") or ""
            if not (child_text.strip() or child_display.strip()):
                self.bump("headers_without_text_skipped")
                continue

            cmd, caption = self._parse_header(child_text, child_display)
            stated = _CMD_ONLY_RE.search(child_display) or _CMD_RE.search(child_display)
            size = payload.get("font_size")
            if stated:
                level, basis = _LEVEL.get(cmd, 1), "latex_command"
            elif size in by_size:
                level, basis = by_size[size], "font_size"
                self.bump("levels_from_font_size")
            else:
                level, basis = 1, "default"
                self.bump("levels_defaulted")
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "line_index": payload.get("_line_index"),
                "cmd": cmd,
                "caption": caption,
                "level": level,
                # Which signal set the level: the author's command, MathPix's
                # font size, or nothing at all.
                "level_basis": basis,
                "font_size": size,
            })
        return items

    @staticmethod
    def _parse_header(text: str, display: str) -> tuple[str, str]:
        # Strategy 1: display contains a full \section*{Caption} pattern.
        m = _CMD_RE.search(display)
        if m:
            return m.group(1), m.group(2)
        # Strategy 2: display contains a bare \section* command and text has the caption.
        m2 = _CMD_ONLY_RE.search(display)
        if m2:
            return m2.group(1), text.strip()
        # Strategy 3: fall back to whatever text we have.
        return "section", text.strip() or display.strip()

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Section",
            props={
                "level": item["level"],
                "caption": item["caption"],
                "cmd": item["cmd"],
                "level_basis": item["level_basis"],
                "font_size": item.get("font_size"),
                "page": item["page"],
                "line_index": item["line_index"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        self.bump("sections_created")
        return obj
