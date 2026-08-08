"""
EquationProcessor (procOrder 11).

Display equations (lines of type='equation' or type='math') get particularly
rich treatment, since equations are the canonical case for multi-stream
realizations:

  1. Surface realization in `mathpix_lines` — where the equation sits in OCR
     output (one anchor, the whole line).
  2. LaTeX-source realization in a per-equation character-level stream
     `latex_eq_<n>` — character anchors for each codepoint of the normalized
     LaTeX. This is the stream you'd address from a structural LaTeX parser
     (Fraction-of-1-over-2, etc.).
  3. CDN realization — opaque pointer to the MathPix-rendered image URL.

A nearby `equation_number` line (±3 lines around) provides the refnum.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization, Range, Alignment
from ..mathpix import crop_url, image_ref


_OUT_DOLLAR = re.compile(r"^\$\$([\s\S]*)\$\$$")
_OUT_INLDOL = re.compile(r"^\$([\s\S]*)\$$")
_OUT_PAREN = re.compile(r"^\\\(([\s\S]*)\\\)$")
_OUT_BRACK = re.compile(r"^\\\[([\s\S]*)\\\]$")
_BEGIN_EQ = re.compile(r"\\begin\{equation\}")
_END_EQ = re.compile(r"\\end\{equation\}")


def _normalize_latex(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    for rx in (_OUT_BRACK, _OUT_PAREN, _OUT_DOLLAR, _OUT_INLDOL):
        m = rx.match(s)
        if m:
            s = m.group(1)
            break
    s = _BEGIN_EQ.sub("", s)
    s = _END_EQ.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_MATH_WRAP = (("\\(", "\\)"), ("\\[", "\\]"), ("$$", "$$"), ("$", "$"))


def normalize_equation_number(raw) -> str:
    """The printed equation number, without its wrapping.

    MathPix emits the number bare — `(2.4)` — or wrapped in inline-math
    delimiters — `\\((2.5)\\)`. Stripping paren CHARACTERS turned the second
    into `\\2.5\\`, which `eqnums` then re-wrapped as `(\\2.5\\)`: a number
    with a backslash in it, matching nothing downstream. Remove the DELIMITER
    PAIR first, then the parens.
    """
    t = (raw or "").strip()
    if not t:
        return ""
    changed = True
    while changed:                       # `\(($x$)\)` style nesting
        changed = False
        for open_, close in _MATH_WRAP:
            # >=, not >: `\(\)` is an EMPTY wrapper and must collapse to "",
            # not leave its own backslashes behind as if they were a number.
            if len(t) >= len(open_) + len(close) and t.startswith(open_) and t.endswith(close):
                t = t[len(open_):-len(close)].strip()
                changed = True
    t = re.sub(r"[()]", "", t).strip()
    # An equation number never contains a backslash, so any left here is damage,
    # not content: models built before this fix hold `\\2.5\\` in `refnum`
    # (the old code deleted the parens and kept the delimiters' backslashes).
    # Stripping them repairs those in place, without a rebuild.
    return t.replace("\\", "").strip()


class EquationProcessor(BaseModule):
    EQ_TYPES = {"equation", "math"}

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        anchors = stream.anchors

        # Number equations by page + vertical position, not stream proximity.
        # MathPix often emits all of a page's `math` lines first and then all
        # its `equation_number` lines, so a +-N stream-index window only catches
        # the first equation per page (this left 12/13 equations of arXiv
        # 2312.11532 unnumbered, incl. eq 9, when running `model` alone).
        refnum_by_anchor = self._match_equation_numbers(anchors, stream)

        items: list[dict[str, Any]] = []
        for i, anchor in enumerate(anchors):
            payload = stream.payload[anchor]
            if payload.get("type") not in self.EQ_TYPES:
                continue
            refnum = (refnum_by_anchor.get(anchor)
                      or self._refnum_near(anchors, stream, i,
                                           used=set(refnum_by_anchor.values())))
            latex_raw = payload.get("text_display") or payload.get("text") or ""
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": payload.get("region"),
                "refnum": refnum,
                "latex_raw": latex_raw,
                "latex": _normalize_latex(latex_raw),
            })
        return items

    def _match_equation_numbers(self, anchors, stream) -> dict:
        """Pair each math/equation line with the same-page `equation_number`
        line whose region y-center is closest (greedy nearest-pair, each number
        used once). Returns {equation_anchor: "N"}."""
        def y_center(p):
            r = p.get("region") or {}
            top = r.get("top_left_y")
            return None if top is None else top + (r.get("height") or 0) / 2.0

        eqs_by_page: dict = {}
        nums_by_page: dict = {}
        for a in anchors:
            p = stream.payload[a]
            yc = y_center(p)
            if yc is None:
                continue
            pg = p.get("_page")
            if p.get("type") in self.EQ_TYPES:
                eqs_by_page.setdefault(pg, []).append((yc, a))
            elif p.get("type") == "equation_number":
                t = normalize_equation_number(p.get("text") or p.get("text_display"))
                if t:
                    nums_by_page.setdefault(pg, []).append((yc, t))

        out: dict = {}
        for pg, eqs in eqs_by_page.items():
            nums = nums_by_page.get(pg, [])
            pairs = sorted(
                ((abs(ey - ny), ea, ny, nt) for (ey, ea) in eqs for (ny, nt) in nums),
                key=lambda t: t[0],
            )
            used_num: set = set()
            for _d, ea, ny, nt in pairs:
                if ea in out or ny in used_num:
                    continue
                out[ea] = nt
                used_num.add(ny)
        return out

    @staticmethod
    def _refnum_near(anchors, stream, i: int, used: "set | None" = None) -> str:
        """Positional fallback: the nearest `equation_number` in a ±3 stream
        window, for an equation the geometric pass could not place.

        `used` is the set of numbers the geometric pass already assigned, and
        skipping them is the whole point: the two algorithms had no shared
        bookkeeping, so on a page with 3 equations and 2 numbers this handed
        (2.5) to a THIRD equation that already belonged to another — two
        equations printing the same number and the next one printing none.
        """
        used = used if used is not None else set()
        lo, hi = max(0, i - 3), min(len(anchors), i + 4)
        for j in range(lo, hi):
            p = stream.payload[anchors[j]]
            if p.get("type") == "equation_number":
                t = normalize_equation_number(p.get("text") or p.get("text_display"))
                if t and t not in used:
                    return t
        return ""

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        # 1) Build a per-equation char-level stream for the normalized LaTeX.
        eq_no = self.bump("equations_created")
        latex_stream_name = f"latex_eq_{eq_no:04d}"
        latex_stream = doc.ensure_stream(latex_stream_name)
        latex_anchors = [latex_stream.append(codepoint=ch) for ch in item["latex"]]

        obj = DocObject(
            type="Equation",
            props={
                "refnum": item["refnum"],
                "latex": item["latex"],          # convenient copy
                "latex_raw": item["latex_raw"],
                "page": item["page"],
                "image_id": item["image_id"],
                "region": item["region"],
                # source-aware crop: MathPix pixels via cdn.mathpix.com, or OUR
                # local pyramid in PDF points (pdfminer/DRILLPDFse) — never mixed.
                "cdn_url": image_ref(item["image_id"], item["region"],
                                     doc.meta.get("source", "mathpix")),
                "bibkey": self.bibkey,
            },
        )
        # surface in the OCR line stream
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        # latex source as a char-level realization
        if latex_anchors:
            obj.add_realization(Realization(
                stream=latex_stream_name,
                start=latex_anchors[0], end=latex_anchors[-1],
                role="latex_source",
            ))
        # rendered image (no anchor range, just a URL pointer)
        if obj.props["cdn_url"]:
            obj.add_realization(Realization(
                stream="cdn",
                role="image",
                props={"url": obj.props["cdn_url"]},
            ))

        # The rendering relationship "this latex source produces this CDN
        # image" is expressed both as the cdn-role Realization above AND as
        # an Alignment of kind 'render'. The cdn side of the Range has no
        # anchors (the URL is the substance), which is now a first-class
        # case the Range type supports.
        if latex_anchors and obj.props["cdn_url"]:
            doc.add_alignment(Alignment(
                kind="render",
                left=Range(latex_stream_name, latex_anchors[0], latex_anchors[-1]),
                right=Range("cdn", None, None),
                props={"target_url": obj.props["cdn_url"]},
            ))

        return obj
