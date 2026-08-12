"""
PageProcessor (procOrder 1).

This is the foundational module: it ingests the raw MathPix lines.json and
builds the primary `mathpix_lines` stream, where each anchor corresponds to
one OCR line and carries that line's full payload (text, region, font_size,
type, page, column, image_id, ...).

It also creates a `Page` DocObject per page, with a realization spanning all
of that page's line anchors. Subsequent modules consume the stream and add
their own DocObjects on top.

Unlike the TypeScript version, this module is also responsible for the
initial *ingestion* step (reading the raw JSON into the Document): see
`ingest_lines_json`, which populates the `mathpix_lines` stream and the
page-level metadata on `doc.meta`.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


# How far into a document a title page can sit. A paper puts its title on page
# 1; a book puts a half-title and a series page in front of it (WDorg4: title
# page = 3). Bounded, because past the front matter a "title" line is a chapter.
_FRONT_PAGES = 5

# The empty-typed-title fallback is deliberately narrow: a title page carries a
# few short lines, so these caps keep a text-heavy page from becoming a title.
_TITLE_FALLBACK_MAX_LINES = 6
_TITLE_FALLBACK_MAX_CHARS = 200


def _extract_title(lines_json: dict) -> str:
    """Best-effort document title from the leading `type:"title"` line(s) of the
    front matter.

    MathPix often nests the title text in child lines (the parent title line's
    own `text` is empty), so resolve `children_ids`. When the typed title line
    is empty AND has no children — a scanned book whose title is set in a
    display face — the title text is the other short text lines on that same
    page, which is where it visibly is. Returns "" when there is no title line
    at all (e.g. the keyless tesseract path emits only `text`).
    """
    for page in lines_json.get("pages", [])[:_FRONT_PAGES]:
        lines = page.get("lines", [])
        by_id = {l.get("id"): l for l in lines if l.get("id")}
        parts: list[str] = []
        saw_title_line = False
        for l in lines:
            if l.get("type") != "title":
                continue
            saw_title_line = True
            txt = (l.get("text") or "").strip()
            if not txt and l.get("children_ids"):
                txt = " ".join((by_id.get(cid, {}).get("text") or "")
                               for cid in l["children_ids"])
            txt = " ".join(txt.split())
            if txt and not re.fullmatch(r"abstract", txt, re.I):
                parts.append(txt)
        if parts:
            return " ".join(parts).strip()
        if saw_title_line:
            t = _title_from_page_body(lines)
            if t:
                return t
    return ""


def _title_from_page_body(lines: list) -> str:
    """The title-page body: plain text lines, stopping at the first `page_info`
    (the publisher/imprint line sits below the title and is not part of it)."""
    parts: list[str] = []
    for l in lines:
        typ = l.get("type")
        if typ == "page_info":
            break                              # publisher / imprint line
        if typ != "text":
            continue                           # authors, title, anything typed
        txt = " ".join((l.get("text") or "").split())
        if txt:
            parts.append(txt)
    if not parts or len(parts) > _TITLE_FALLBACK_MAX_LINES:
        return ""
    out = " ".join(parts).strip()
    return out if len(out) <= _TITLE_FALLBACK_MAX_CHARS else ""


def _extract_authors(lines_json: dict) -> str:
    """The front matter's `authors`-typed line, verbatim.

    MathPix types it and nothing read it, so every scanned book came out
    authorless — `bibtex` reported `@misc{unknown}` for a book whose own title
    page names both authors.
    """
    for page in lines_json.get("pages", [])[:_FRONT_PAGES]:
        for l in page.get("lines", []):
            if l.get("type") != "authors":
                continue
            txt = " ".join((l.get("text") or "").split())
            if txt:
                return txt
    return ""


# `© 1996 by ...` / `Copyright (c) 2004 ...` — the year a book states about
# itself on its imprint page. A bare year in prose is NOT this: without the
# copyright marker a front-matter sentence like "written between 1975 and 1980"
# would supply the record's year.
_COPYRIGHT_YEAR = re.compile(
    r"(?:©|\(c\)|\bcopyright\b)[^0-9]{0,20}((?:19|20)\d{2})", re.I)


def _extract_pub_year(lines_json: dict) -> str:
    """The publication year from the front matter's copyright line.

    The EARLIEST such year wins: a reprint page lists the reprint alongside the
    original, and the work's year is the first one.
    """
    years: list[str] = []
    for page in lines_json.get("pages", [])[:_FRONT_PAGES]:
        for l in page.get("lines", []):
            m = _COPYRIGHT_YEAR.search(" ".join((l.get("text") or "").split()))
            if m:
                years.append(m.group(1))
    return min(years) if years else ""


# The imprint line names the publisher: `© 1996 by Andreas Resch Verlag,
# Innsbruck`. Deliberately NOT the PDF Producer — that is a tool (pdfTeX,
# Word, a scanner driver), which is why derive_bibtex already refuses it.
_IMPRINT = re.compile(
    r"(?:©|\(c\)|\bcopyright\b)\s*(?:19|20)\d{2}\s*(?:by|bei)?\s*(.+)", re.I)

# A place is a short trailing element. Longer than this and the comma was
# separating a clause, not a city, so the whole thing stays in the name.
_PLACE_MAX_WORDS = 4
_TRAILING_YEAR = re.compile(r"[\s,]*(?:19|20)\d{2}\.?$")


def _extract_publisher(lines_json: dict) -> tuple:
    """(publisher, address) from the front matter's copyright line, or ("", "").

    The last comma separates the two — but only when what follows reads like a
    place. `Some Press, all rights reserved worldwide ...` is one name followed
    by a clause, not a publisher in a city.
    """
    for page in lines_json.get("pages", [])[:_FRONT_PAGES]:
        for l in page.get("lines", []):
            m = _IMPRINT.search(" ".join((l.get("text") or "").split()))
            if not m:
                continue
            rest = _TRAILING_YEAR.sub("", m.group(1).strip()).strip(" .,")
            if not rest:
                continue
            publisher, address = rest, ""
            if "," in rest:
                head, _, tail = rest.rpartition(",")
                tail = _TRAILING_YEAR.sub("", tail.strip()).strip(" .")
                if head.strip() and 0 < len(tail.split()) <= _PLACE_MAX_WORDS:
                    publisher, address = head.strip(), tail
            return publisher, address
    return "", ""


def ingest_lines_json(doc: Document, lines_json: dict) -> None:
    """
    Populate the `mathpix_lines` stream and store page-level metadata on
    `doc.meta`. Called by main.py before any processor runs.

    The payload of each anchor includes ALL fields of the original line
    (so no information is lost), plus a synthetic `_page` and `_line_index`
    for convenience (the OCR `line` field is sometimes ambiguous).
    """
    stream = doc.ensure_stream(BaseModule.LINES_STREAM)
    pages_meta: list[dict] = []
    for page in lines_json.get("pages", []):
        page_no = page.get("page")
        pages_meta.append({
            "page": page_no,
            "image_id": page.get("image_id"),
            "page_height": page.get("page_height"),
            "page_width": page.get("page_width"),
            "languages_detected": page.get("languages_detected", []),
        })
        for line_index, line in enumerate(page.get("lines", [])):
            payload = dict(line)  # shallow copy of MathPix line
            payload["_page"] = page_no
            payload["_line_index"] = line_index
            payload["_image_id"] = page.get("image_id")
            stream.append(**payload)
    doc.meta["pages"] = pages_meta
    doc.meta["num_pages"] = len(pages_meta)
    # Capture the document title (for the tiddler `caption`, scikgtex, the
    # llm_compact YAML header, …) — the PDF path never stored it before.
    if not doc.meta.get("title"):
        t = _extract_title(lines_json)
        if t:
            doc.meta["title"] = t
    if not doc.meta.get("authors"):
        a = _extract_authors(lines_json)
        if a:
            doc.meta["authors"] = a
    if not doc.meta.get("year"):
        y = _extract_pub_year(lines_json)
        if y:
            doc.meta["year"] = y
    if not doc.meta.get("publisher"):
        pub, addr = _extract_publisher(lines_json)
        if pub:
            doc.meta["publisher"] = pub
        if addr:
            doc.meta["address"] = addr


class PageProcessor(BaseModule):
    """Create one Page DocObject per page, spanning that page's lines."""

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)

        # First pass: group existing line anchors by page number.
        anchors_by_page: dict[int, list] = {}
        for anchor in stream.anchors:
            pg = stream.payload[anchor].get("_page")
            anchors_by_page.setdefault(pg, []).append(anchor)

        # Drive the Page list from doc.meta['pages'] (set during ingest), so
        # that pages with zero OCR lines (blank pages) still get a Page object.
        items: list[dict[str, Any]] = []
        for page_meta in doc.meta.get("pages", []):
            pg = page_meta["page"]
            page_anchors = anchors_by_page.get(pg, [])
            items.append({
                "page": pg,
                "image_id": page_meta.get("image_id"),
                "page_height": page_meta.get("page_height"),
                "page_width": page_meta.get("page_width"),
                "languages_detected": page_meta.get("languages_detected", []),
                "start_anchor": page_anchors[0] if page_anchors else None,
                "end_anchor": page_anchors[-1] if page_anchors else None,
                "is_blank": len(page_anchors) == 0,
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Page",
            props={
                "page_number": item["page"],
                "image_id": item["image_id"],
                "page_height": item["page_height"],
                "page_width": item["page_width"],
                "languages_detected": item["languages_detected"],
                "is_blank": item["is_blank"],
                "bibkey": self.bibkey,
            },
        )
        if not item["is_blank"]:
            obj.add_realization(Realization(
                stream=self.LINES_STREAM,
                start=item["start_anchor"],
                end=item["end_anchor"],
                role="surface",
            ))
        self.bump("pages_created")
        if item["is_blank"]:
            self.bump("pages_blank")
        return obj
