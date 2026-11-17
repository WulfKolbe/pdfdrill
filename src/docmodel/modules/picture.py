"""
PictureProcessor (procOrder 9).

Picks up figures and inline image URLs.

**Image links — Markdown only.** MathPix encodes the same image two ways:

  - Markdown form: `![](<cdn>)` where `<cdn>` is the *page* image
    (`cropped/<process-id>-<page>.jpg`) plus a rectangle in the query string
    (`height/width/top_left_y/top_left_x`). This is identical to what
    `mathpix.crop_url(image_id, region)` reconstructs from the line's own
    `image_id` + `region`.
  - LaTeX form: `\\begin{figure}\\includegraphics[...]{...}\\end{figure}`. In the
    `tex.zip` export the `\\includegraphics` target is a *per-picture* numbered
    local file (process-id, page, then a picture index) — a different
    addressing scheme that would need image matching to relate back to a full
    page. We therefore do NOT use `\\includegraphics` URLs at all; we take the
    Markdown link (the embedded `![]()` / bare CDN URL, or `crop_url`).

What this processor captures:

- Lines of type='figure': image URL from `crop_url(image_id, region)`, caption
  from a child of type='caption' or the line's own `\\caption{}`. **No producer
  emits either type** — see the note on `_NO_PRODUCER` below; this path is
  exercised only by synthetic fixtures.
- Inline Markdown images (`![]()`) / bare CDN URLs embedded in text lines.

`type='diagram'` lines are intentionally NOT handled here — they are owned by
`DiagramProcessor` (procOrder 7), which also uses the Markdown `crop_url` link.
The TS reference removed diagram lines from the document before PictureProcessor
ran; our source streams are immutable, so we skip the type instead to avoid one
image becoming both a Diagram and a Picture.

Each becomes a Picture DocObject with a CDN realization plus a surface
realization into the source line, carrying caption / kind / refnum.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ._captions import (FIGURE_KINDS, TABLE_KINDS, extract_figure_caption,
                        parse_caption)
from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..mathpix import (crop_url, image_ref, region_from_url,
                       crop_region, quad, is_axis_aligned)


# Markdown image link. Group 1 is the ALT text, group 2 the URL: the alt text
# is what survives when the URL is refused below.
_MD_IMG = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)")

#: WHICH INLINE IMAGE URL THIS MODULE TRUSTS.
#:
#: The contract at the top of this file is a MathPix crop of a page we have:
#: `![](<cdn>)` with `height/width/top_left_y/top_left_x` in the query string.
#: `_MD_IMG` accepted any `http(s)` URL instead, and a Gemma reading of 0864
#: wrote a body text line as `![Figure 1: ...](https://example.com/figure1.png)`.
#: That became a Picture whose only anchor is the text line, so the inspector
#: drew a box labelled "Picture" across the sentence "e.g., [Huhtala et al.,
#: 1999; ...], ne-" -- the owner found it there -- and stored a URL nothing had
#: ever fetched as the image.
#:
#: The rectangle is the test, and it is the same one the docstring states. With
#: it the URL addresses a region of the page, so the Picture is real and
#: placeable. Without it pdfdrill has neither the file nor anywhere to put it,
#: and a box over body text plus an invented URL is worse than keeping nothing.
#: What is kept is the alt text, as a caption candidate: on that document it
#: reads "Figure 1: Dependency-by-chance. ..." while the page's real Diagram
#: carries no caption at all.
_CDN_HOST = re.compile(r"^https?://cdn\.mathpix\.com/")


def _is_placeable(url: str) -> bool:
    """True when the URL carries its own rectangle, or is a MathPix CDN crop
    (which carries one by construction)."""
    return bool(region_from_url(url)) or bool(_CDN_HOST.match(url))
# Bare MathPix CDN crop URL (page image + rectangle params) embedded in text —
# also a Markdown-style link.
_CDN_URL = re.compile(r"(https?://cdn\.mathpix\.com/cropped/[^\s\}>\])\"]+)")

# Line types whose images are owned by another processor.
_SKIP_TYPES = {"diagram"}

#: 259 — types that reach `_from_inline` through the else-branch and are fully
#: handled there, named explicitly because a catch-all is invisible to anyone
#: (and to any check) reading this file for a type. `"molecule"` — 10 lines in
#: 4 documents, a rendered chemical structure — carries a plain Markdown CDN
#: link and has always produced a Picture. The type contract listed it as a GAP
#: on the assumption that a type needs a branch to be read; it does not.
_COVERED_BY_INLINE = ("molecule",)

#: 249 saw zero `figure` / `caption` lines in the corpus but kept the branch,
#: because that scan read MathPix `*.lines.json` only and a second producer
#: (visionocr) had already been caught supplying a "dead" literal. 253 checked
#: the producers rather than the corpus: **nothing in this repo emits a line of
#: type `figure` or `caption`** — not mathpix, not visionocr, not pdf_lines. The
#: branch below is reachable from test fixtures alone, and `tiddlywiki.py`
#: consumes a `from_line_type == "figure"` that is therefore never set.
#:
#: 253 also retired the replacement shape this comment used to assert. MathPix's
#: `figure_label` (22,638 lines) is NOT the caption: all 49 of the ones parented
#: to a diagram/chart are in-figure text — axis labels ("GATE VOLTAGE (V)"),
#: chord names, code-listing titles, three empty strings. The caption is carried
#: by `\\caption{}` inside the diagram/chart line's OWN text (12,632 corpus-wide,
#: 83% of them matching `Figure N:`), which `DiagramProcessor` and `_from_inline`
#: already read. Kept as a named tuple so the next reader inherits the check
#: instead of re-running it.
_NO_PRODUCER = ("figure", "caption")


def _skew_quad(payload) -> list:
    """The four corners, but only when they are NOT an upright rectangle —
    otherwise they restate `region` and would bloat every model file."""
    c = quad(payload)
    return [] if (not c or is_axis_aligned(c)) else c


class PictureProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        source = doc.meta.get("source", "mathpix")
        items: list[dict[str, Any]] = []
        #: Alt texts of refused inline images — see `_is_placeable`.
        cands: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            ltype = payload.get("type")
            if ltype in _SKIP_TYPES:
                continue
            if ltype == "figure":
                items.extend(self._from_figure_line(anchor, payload, by_id, source))
            else:
                items.extend(self._from_inline(anchor, payload, cands))
        if cands:
            doc.meta["image_caption_candidates"] = cands
        return items

    @staticmethod
    def _from_figure_line(anchor, payload, by_id, source="mathpix") -> list[dict[str, Any]]:
        text = payload.get("text_display") or payload.get("text") or ""
        # Caption from a child of type='caption', else from a \caption{} in the
        # line's own figure-env text.
        caption = ""
        for cid in payload.get("children_ids", []) or []:
            child = by_id.get(cid)
            if child and child.get("type") == "caption":
                caption = child.get("text_display") or child.get("text") or ""
                break
        if not caption:
            caption = extract_figure_caption(text)
        # Markdown link only: the page image + rectangle from this line's own
        # region (NOT the \includegraphics target). 259 — where `cnt` says the
        # line is rotated, its bbox is used instead: a box round rotated text is
        # wider than the text.
        region = crop_region(payload)
        url = image_ref(payload.get("_image_id"), region, source)
        if not url:
            return []
        return [{
            "anchor": anchor,
            "url": url,
            "caption": caption,
            "page": payload.get("_page"),
            "region": region,
            "from_line_type": "figure",
            "mathpix_subtype": payload.get("subtype", ""),
            "quad": _skew_quad(payload),
        }]

    def _from_inline(self, anchor, payload,
                     cands: Optional[list] = None) -> list[dict[str, Any]]:
        text = payload.get("text_display") or payload.get("text") or ""
        if not text:
            return []
        # Caption from a figure-env in the line text (Markdown `![]()` form has
        # no caption). One caption per line is the realistic case.
        caption = extract_figure_caption(text) if "\\begin{figure}" in text else ""
        urls: list[str] = []
        # Markdown image links, then bare CDN crop URLs — both page+rectangle.
        # MathPix LaTeX-escapes query `&` as `\&` inside table-cell `![]()`;
        # unescape so the stored URL is directly fetchable (no 400 downstream).
        for m in _MD_IMG.finditer(text):
            url = m.group(2).strip().replace("\\&", "&")
            if not _is_placeable(url):
                # Refused. The alt text is kept; the URL is not, here or anywhere.
                alt = " ".join((m.group(1) or "").split())
                if alt and cands is not None:
                    kind, refnum, body = parse_caption(alt)
                    cands.append({"anchor": anchor, "page": payload.get("_page"),
                                  "alt": alt, "kind": kind, "refnum": refnum,
                                  "caption": body})
                continue
            urls.append(url)
        for m in _CDN_URL.finditer(text):
            urls.append(m.group(1).strip().replace("\\&", "&"))
        # De-duplicate within this line while preserving order.
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        out = []
        for i, url in enumerate(unique):
            out.append({
                "anchor": anchor,
                "url": url,
                # Attach the caption to the first image only.
                "caption": caption if i == 0 else "",
                "page": payload.get("_page"),
                "region": region_from_url(url),
                "from_line_type": payload.get("type"),
                # 260 — MathPix's own subtype. A chart line reaches here and
                # says which KIND of chart it is (line 967, analytical 445,
                # column 315, scatter 265, bar 60, area 4, pie 1 — 2,057 lines
                # in 320 documents). The value was read off the line and thrown
                # away one statement later.
                "mathpix_subtype": payload.get("subtype", ""),
                # The URL already carries its own rectangle; the quad is extra
                # information about the same line, not a competing crop.
                "quad": _skew_quad(payload),
            })
        return out

    #: What a refused image's alt text may caption, BY THE LABEL IT CARRIES.
    #: Measured on 0864: page 3 holds a captionless Table AND a captionless
    #: Diagram, and the alt text reads "Figure 2: Base transformation example".
    #: A first version matched on the page alone and gave that figure caption to
    #: the Table, because the Table object happens to be created first — a
    #: caption on the wrong object, which is the class of error this whole task
    #: is about. The label says which it belongs to.
    _IMAGEY = ("Diagram", "Picture", "Figure", "Image", "Chart")
    _TABLEY = ("Table",)

    def process_document(self, doc: Document) -> None:
        super().process_document(doc)
        self._apply_caption_candidates(doc)

    def _apply_caption_candidates(self, doc: Document) -> None:
        """Give each refused image's alt text to a captionless image on its page.

        Conservative on purpose: it fills an EMPTY caption only, never replaces
        one the reading supplied, and matches on the page alone — the refused
        line has no rectangle, so there is nothing finer to match on.
        """
        cands = doc.meta.get("image_caption_candidates") or []
        if not cands:
            return
        used: set = set()
        for cand in cands:
            if not cand.get("caption") and not cand.get("alt"):
                continue
            kind = cand.get("kind")
            if kind in TABLE_KINDS:
                want = self._TABLEY
            elif kind in FIGURE_KINDS or not kind:
                want = self._IMAGEY
            else:
                continue
            for obj in doc.objects.values():
                if obj.type not in want or id(obj) in used:
                    continue
                props = obj.props or {}
                if props.get("page") != cand.get("page"):
                    continue
                if (props.get("caption") or "").strip():
                    continue
                props["caption"] = cand.get("caption") or cand.get("alt")
                if not props.get("kind") and cand.get("kind"):
                    props["kind"] = cand["kind"]
                if props.get("refnum") in (None, "") and cand.get("refnum") not in (None, ""):
                    props["refnum"] = cand["refnum"]
                used.add(id(obj))
                break

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        kind, refnum, cap_body = parse_caption(item["caption"])
        obj = DocObject(
            type="Picture",
            props={
                "url": item["url"],
                "caption": cap_body,
                "kind": kind,           # 'Figure' / 'Picture' / 'Sketch' / ... / None
                "refnum": refnum,
                "page": item["page"],
                "region": item["region"],
                "from_line_type": item["from_line_type"],
                "mathpix_subtype": item.get("mathpix_subtype", ""),
                # 259 — MathPix's four corners, carried ONLY when they say
                # something a rectangle cannot. Empty for the 99.86% of lines
                # that are upright.
                "quad": item.get("quad", []),
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        obj.add_realization(Realization(
            stream="cdn",
            role="image",
            props={"url": item["url"]},
        ))
        self.bump("pictures_created")
        return obj
