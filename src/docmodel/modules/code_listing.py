"""
CodeProcessor (procOrder 7).

`type='code'` is 44,689 lines across 205 documents — by line count the biggest
type the type contract listed as unread. It was not, quite: 43,933 of those
lines are children of a `diagram` line, and DiagramProcessor already joins its
children's text and pulls a fenced block out of it, so 43,553 lines survive
today as a Diagram's `code` prop. The contract's claim that they were "dropped
entirely" was wrong, and 259 corrects it.

What is genuinely lost is smaller and in two parts:

  380 lines under 51 diagrams whose joined text is not a fenced block, so
      `_extract_code` returns None and the listing falls back to being treated
      as a graphic;
  756 lines whose parent is not a diagram at all — 502 under `column`, 241 with
      no parent, 8 under `list_item`, 5 under `chart` — which no processor
      looks at.

And a listing that survives only as a string prop on a Diagram is not a code
object: it has no anchors of its own, so nothing can point at a line of it.

This module reads the `code` lines DIRECTLY. It takes MathPix's own text for
each line verbatim and joins the lines of a run in order — it does not re-parse
a fence to recover a body it was already given line by line. Fence lines
(```` ``` ````/`~~~`) are MathPix's delimiters, not content, so they are dropped
and the info string on an opening fence supplies `language` when it has one.

A run is a maximal group of consecutive `code` lines on a page. Run lengths in
the corpus go from 1 (1,896 runs) to 20+ (575 runs).

The Diagram `code` prop is left exactly as it was: consumers depend on it, and
a CodeListing realizes the code CHILD anchors while the Diagram realizes the
diagram line, so no anchor is claimed twice.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization

#: MathPix's own fence markers. A line that is only a fence is a delimiter.
_FENCES = ("```", "~~~")


def _fence_info(line: str) -> Optional[str]:
    """If `line` is a fence, return its info string ('' when bare); else None."""
    s = line.strip()
    if not s.startswith(_FENCES):
        return None
    return s.lstrip("`~").strip()


def _language(info_strings: list[str]) -> str:
    """The language MathPix wrote on an opening fence, if it wrote one."""
    for info in info_strings:
        token = info.split()[0] if info.split() else ""
        if token.isalnum():
            return token
    return ""


class CodeProcessor(BaseModule):
    """One CodeListing per maximal run of consecutive `code` lines."""

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)

        items: list[dict[str, Any]] = []
        run: list[Any] = []
        run_page = None

        def flush():
            # list(run), NOT run: `_build` stores the anchors it is handed, and
            # the caller clears this list immediately afterwards. Passing the
            # live list aliased every item's realization to whatever the NEXT
            # run held — and emptied the last one, so create_object raised
            # IndexError on the first real document. The unit tests missed it
            # because they assert on `code`, a string built inside `_build`,
            # which is correct either way.
            if run:
                items.append(self._build(list(run), stream, by_id, run_page))

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            page = payload.get("_page")
            if payload.get("type") == "code":
                # A page break ends a run: two listings on facing pages are two
                # listings, and their line numbers do not continue.
                if run and page != run_page:
                    flush()
                    run.clear()
                run_page = page
                run.append(anchor)
            elif run:
                flush()
                run.clear()
        flush()
        return items

    def _build(self, anchors, stream, by_id, page) -> dict[str, Any]:
        body: list[str] = []
        infos: list[str] = []
        for a in anchors:
            payload = stream.payload[a]
            text = payload.get("text_display") or payload.get("text") or ""
            # MathPix prefixes each of these lines with a single "\n". That is
            # its line terminator, not a blank line in the listing — dropping
            # exactly one leading newline keeps a genuinely blank interior line
            # (which IS content) while not doubling every line of every listing.
            if text.startswith("\n"):
                text = text[1:]
            # Indentation is content; only the line terminator is stripped.
            for raw in text.split("\n"):
                info = _fence_info(raw)
                if info is not None:
                    infos.append(info)
                    continue
                body.append(raw.rstrip())
        # Leading/trailing blank lines are fence padding, not the listing.
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()

        first = stream.payload[anchors[0]]
        parent_id = first.get("parent_id") or ""
        parent = by_id.get(parent_id) or {}
        return {
            "anchors": anchors,
            "page": page,
            "code": "\n".join(body),
            "language": _language(infos),
            "line_count": len(body),
            "parent_id": parent_id,
            "parent_type": parent.get("type", ""),
        }

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        if not item["code"].strip():
            self.bump("empty_listings_skipped")
            return None
        obj = DocObject(
            type="CodeListing",
            props={
                "code": item["code"],
                "language": item["language"],
                "line_count": item["line_count"],
                "page": item["page"],
                # Where the listing sat. `diagram` for 43,933 of the corpus's
                # code lines, and that parent also carries the same text in its
                # own `code` prop — the two are the same content, addressed
                # differently, not a duplicate object.
                "parent_id": item["parent_id"],
                "parent_type": item["parent_type"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchors"][0],
            end=item["anchors"][-1],
            role="surface",
        ))
        self.bump("code_listings_created")
        self.bump("code_lines_read", len(item["anchors"]))
        return obj
