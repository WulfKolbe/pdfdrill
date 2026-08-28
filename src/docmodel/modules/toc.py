"""
TocProcessor (procOrder 6).

Collects all `table_of_contents_*` lines (container, row, item, number) and
emits a single Toc DocObject containing the concatenated entries, with
realizations into each contributing line.

**262 — a Toc is DERIVED content.** Every entry duplicates a `section_header`
that exists elsewhere in the same document; the TOC is the book's own index of
itself. The TypeScript predecessor deleted TOC lines outright for that reason,
which loses the fact that the page HAS one.

So the model keeps it and marks it: `derived: True`. What the page contains is
a question for the model; what a reader should see is a question for the
projection, and the two are answered in different places — the same separation
`latex_refined` uses. A projection that shows the page as it is (inspect.html,
report.tex, plaintext) keeps the Toc; a projection that can rebuild the table
from the section headers themselves (TiddlyWiki, by filter) omits it rather
than freezing a copy that cannot follow the sections it points at.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


#: 263 — the dot leader. The ONLY leader character MathPix emits in this corpus
#: is `.` (34,021 of 54,240 entry strings carry a run of 4+; no ·, …, _ or dash
#: leader occurs at all — checked, not assumed). A leader is typography: it
#: joins a title to its page number and belongs to neither.
#:
#: `table_of_contents_number` is its own type, so the number is separately
#: identifiable and does not have to be recovered from the string. But a ROW's
#: entry is the join of its children — "1.1. Cayley algebra … ..... 1" — so on
#: that line the three parts do arrive fused, and this is where they come back
#: apart. Stripping the leader alone would weld the page number onto the title
#: ("Cayley algebra 1"), which is worse than leaving it.
_LEADER = re.compile(r"\s*\.{2,}\s*")
#: What may follow a leader and still be a locator: an arabic or roman page
#: number, a dotted section number (3.1.2.1 — some indexes point at sections,
#: not pages), a range, or a number with a letter suffix. Anything else is text
#: that happened to sit after dots.
_LOCATOR = re.compile(
    r"^[0-9]+(?:\.[0-9]+)*[a-z]?(?:[-\u2013][0-9]+[a-z]?)?$"
    r"|^[ivxlcdm]+$|^[IVXLCDM]+$")


def split_leader(text: str) -> tuple[str, str]:
    """Split a TOC entry into (title, locator) at its dot leader.

    ("", "1")     for an entry that is ONLY a leader and a number — the
                  `table_of_contents_number` lines, which have no title by
                  construction.
    (text, "")    when there is no leader.

    A row's joined children can carry more than a title and a page: a
    proceedings TOC row reads "Title ..... 57 \\n Author, Author". The authors
    are part of the entry and are kept with the title; only the leader and the
    locator come off. Stripping the leader WITHOUT lifting the locator out
    would weld the page number into the title ("… Quad-Graphs 57 Alexander I.
    Bobenko"), which is worse than leaving the dots alone.
    """
    t = (text or "").strip()
    if not t:
        return "", ""
    parts = _LEADER.split(t)
    if len(parts) < 2:
        return t, ""
    head = _LEADER.sub(" ", " ".join(parts[:-1])).strip()
    tail = parts[-1]
    # The locator, if there is one, is what sits between the leader and the
    # first line break; anything past that break is further entry text.
    first, sep, rest = tail.partition("\n")
    if _LOCATOR.match(first.strip()):
        rest = rest.strip()
        title = f"{head}\n{rest}".strip() if rest else head
        return title, first.strip()
    return _LEADER.sub(" ", t).strip(), ""


_TOC_TYPES = {
    "table_of_contents_container",
    "table_of_contents_row",
    "table_of_contents_item",
    "table_of_contents_number",
}


class TocProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)

        toc_anchors = []
        entry_strings: list[str] = []
        rows: list[dict[str, str]] = []
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") not in _TOC_TYPES:
                continue
            toc_anchors.append(anchor)
            if payload.get("children_ids"):
                parts = []
                for cid in payload["children_ids"]:
                    child = by_id.get(cid)
                    if not child:
                        continue
                    parts.append(child.get("text_display") or child.get("text") or "")
                raw = " ".join(parts).strip()
            else:
                raw = (payload.get("text_display") or payload.get("text") or "").strip()
            if not raw:
                continue
            # 263 — the leader comes off here, once, rather than in each
            # consumer. 33,946 of the corpus's 54,240 entries carry one.
            title, locator = split_leader(raw)
            # No `or raw` fallback: a leader-only line HAS no title, and
            # falling back would put "..... 7" back into `entries` — which is
            # exactly the junk entry 261 found being counted as one.
            entry_strings.append(title)
            rows.append({"title": title, "locator": locator, "raw": raw,
                         "line_type": payload.get("type", "")})

        if not toc_anchors:
            return []
        return [{
            "anchors": toc_anchors,
            "entries": entry_strings,
            "rows": rows,
        }]

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Toc",
            props={
                # Titles, leader-stripped. 16,870 corpus entries reduce to ""
                # here because they ARE only a leader and a page number — the
                # `table_of_contents_number` lines, which have no title by
                # construction. They keep their raw form in `rows`.
                "entries": [e for e in item["entries"] if e],
                # 263 — title / locator / raw, separately addressable, so a
                # consumer never has to parse dots out of a string again.
                "rows": item["rows"],
                # 262 — every entry duplicates a section_header elsewhere in
                # this document. Projections decide what to do about it; the
                # model only states that it is so.
                "derived": True,
                "derived_from": "section_header",
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchors"][0], end=item["anchors"][-1],
            role="surface",
        ))
        self.bump("toc_created")
        return obj
