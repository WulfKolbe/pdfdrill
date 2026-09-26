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
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{"
)
_CMD_ONLY_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?"
)


def caption_in_braces(display: str, open_at: int) -> Optional[str]:
    r"""The text between `display`'s brace at `open_at-1` and its MATCHING close.

    811 — this used to be `\{([^}]*)\}`, which stops at the first inner brace.
    A heading with any braces in it — inline math, `\emph{}`, `\textbf{}` —
    was therefore cut at the first one: `\section*{\(\mathrm{RQ}_{1}\). Can
    the netskip architecture…}` yielded the caption `\(\mathrm{RQ`. Measured
    over the corpus's lines.json: 1,065 captions in 238 documents truncated
    this way, and it is silent — a short caption looks like a short heading.

    Returns None when the braces never close, which is not hypothetical:
    MathPix emits a bare `\section*{…` with no closing brace on a header whose
    text it cut (77 of the 1,065). A caller that gets None must fall back to
    the line's own `text`, which carries the whole caption in the clear.
    """
    depth = 1
    out: list = []
    i = open_at
    while i < len(display):
        c = display[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return "".join(out)
        out.append(c)
        i += 1
    return None

_LEVEL = {
    "section": 1, "subsection": 2, "subsubsection": 3,
    "paragraph": 4, "subparagraph": 5,
}

#: Back-matter headings MathPix routinely types as plain `text`. A CLOSED list,
#: matched in full — not a pattern, so it cannot drift into prose. Measured over
#: the corpus's lines.json: 807 such lines in 275 of 1,500 documents, every one
#: of them a heading that produced no Section, which is why a consumer finds the
#: bibliography sitting in prose (811).
_BACK_MATTER = frozenset({
    "references", "bibliography", "acknowledgement", "acknowledgements",
    "acknowledgment", "acknowledgments", "data availability", "appendix",
    "declaration of competing interest", "conflict of interest",
    "author contributions", "funding", "abbreviations", "nomenclature",
    "supplementary material", "supplementary materials",
    "credit authorship contribution statement",
})

#: A numbered heading: "4.2. Results", "2.1 Skip lists".
_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*)$")

#: Longest a promoted heading may be. A heading is a label, not a sentence, and
#: the cap is what keeps an enumerated list item ("1. the cost of deploying the
#: infrastructure may be unaffordable…") out of the numbered-gap route.
_PROMOTE_MAX_CHARS = 90


def _heading_number(text: str):
    """The stated number of a heading line ("4.2" from "4.2. Results"), else None."""
    m = _NUM_HEAD.match((text or "").strip())
    return m.group(1) if m else None


def promotable_headings(stream, by_id: dict) -> dict:
    """{anchor: (caption, level, basis)} for lines MathPix typed `text` that its
    OWN document proves are headings.

    Two routes, both evidence-backed, neither a cross-document threshold:

    **The number series.** If the document's own `section_header` lines state
    `4.1` and `4.3`, a `text` line beginning `4.2` between them is a heading —
    the document is the witness, not a guess about font or spacing. Measured: 34
    lines in 25 of 1,500 documents. Small, and it is the one that cannot be
    wrong, which is why it goes first.

    **The back-matter label.** A line whose whole text is one of `_BACK_MATTER`.
    Measured: 807 lines in 275 of 1,500 documents — `References` and
    `Bibliography` alone are 624 of them. This is the one a reader notices,
    because with no `References` heading the entire bibliography is prose.

    Neither route fires where the document already has a Section for that
    caption or that number: MathPix typing a heading correctly once is not a
    reason to invent a second one.
    """
    numbers, captions = set(), set()
    for a in stream.anchors:
        pl = stream.payload[a]
        if pl.get("type") != "section_header":
            continue
        kids = pl.get("children_ids") or []
        child = by_id.get(kids[0]) if kids else None
        own = str((child or pl).get("text") or "")
        captions.add(own.strip().lower().rstrip(".:").strip())
        num = _heading_number(own)
        if num:
            numbers.add(num)

    out: dict = {}
    for a in stream.anchors:
        pl = stream.payload[a]
        if pl.get("type") != "text" or (pl.get("children_ids") or []):
            continue
        text = str(pl.get("text") or "").strip()
        if not text or len(text) > _PROMOTE_MAX_CHARS:
            continue

        label = text.lower().rstrip(".:").strip()
        num = _heading_number(text)
        if num and "." in num and num not in numbers:
            base, _, last = num.rpartition(".")
            if last.isdigit():
                lo, hi = f"{base}.{int(last) - 1}", f"{base}.{int(last) + 1}"
                # BOTH neighbours, not either: one neighbour is a coincidence a
                # sentence beginning with a number can supply; two is the series.
                if lo in numbers and hi in numbers:
                    level = min(num.count(".") + 1, _MAX_SIZE_LEVEL)
                    out[a] = (text, level, "number_series_gap")
                    continue
        # A heading is capitalised. `references.` — lower-case, with a terminal
        # period — is the tail of a sentence that broke across lines, and it is
        # in the corpus (1905.08669). The label vocabulary alone would promote
        # it; the first character is what tells the two apart.
        if label in _BACK_MATTER and label not in captions and text[:1].isupper():
            out[a] = (text, 1, "back_matter_label")
    return out

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

        # 811 — the headings MathPix typed `text`. A consumer of
        # 1-s2.0-S2590118425000565-main reported "Data availability" and
        # "References" undetected (so the whole bibliography sat in prose) and
        # no "4.2" heading. All three are plain `text` lines in that document's
        # lines.json with no sectioning command anywhere, so
        # `clean_heading_residuals` — which SPLITS a leaked `\section{}` out of
        # a paragraph — has nothing to split. These are recovered from the
        # document's own evidence instead; see `promotable_headings`.
        for anchor, (caption, level, basis) in promotable_headings(stream, by_id).items():
            payload = stream.payload[anchor]
            # Keep it out of the prose run too: the line's TYPE is still `text`,
            # a prose type, so ParagraphProcessor (procOrder 13, after this one
            # at 8) would otherwise put the heading in a Paragraph as well —
            # the same double-counting 811 fixed for list items.
            payload["_promoted_heading"] = True
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "line_index": payload.get("_line_index"),
                "cmd": "section",
                "caption": caption,
                "level": level,
                "level_basis": basis,
                "font_size": payload.get("font_size"),
            })
            self.bump(f"headings_promoted_{basis}")
        items.sort(key=lambda it: (it.get("page") or 0, it.get("line_index") or 0))
        return items

    @staticmethod
    def _parse_header(text: str, display: str) -> tuple[str, str]:
        # Strategy 1: display contains a full \section*{Caption} pattern —
        # read to the MATCHING brace, so a caption containing braces survives.
        m = _CMD_RE.search(display)
        if m:
            caption = caption_in_braces(display, m.end())
            if caption is not None:
                return m.group(1), caption
            # Unterminated `\section*{` — MathPix cut the header. The line's
            # own `text` holds the caption with no LaTeX around it, so prefer
            # it; only if it is empty do we take the unclosed remainder.
            return m.group(1), text.strip() or display[m.end():].strip()
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
