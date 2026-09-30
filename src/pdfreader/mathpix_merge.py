"""mathpix_merge - a MathPix lines.json as a SECOND SOURCE over our regions.

The two describe the same page from opposite directions. We know, per glyph,
what font it came from and where its pen was; MathPix knows what a region
looks like. Neither is complete. Where we defer a region to a crop, MathPix
usually has LaTeX for it -- and where MathPix is unsure, it says so.

That last part is what makes the merge worth doing rather than simply
preferring one source. Every line in a lines.json carries a `confidence`, and
a low one is the vendor pointing at its own weak spots: the table this module
was written against reports 0.60 for a `\\begin{tabular}` it produced, while
ordinary text on the same page reports 1.0.

Tables are the clearest case. MathPix emits table LaTeX in BOTH the `text`
and `text_display` fields, so a `tabular` is available for a region we can
only crop.

COORDINATE SPACE
    lines.json regions are pixels, top-left origin, at 250 dpi. That is the
    same space `docmodel.to_lines_json` writes and `crop_url` uses, so a
    rectangle from either side needs no rescaling. See `docmodel.PX_PER_PT`.

CONTRACT
    load(path) -> Reference
    Reference.covering(page, rect_pts, page_height_pts) -> list[Entry]
        Entries whose region overlaps the given rectangle, best overlap
        first. `rect_pts` is in PDF points, y up, as the docmodel holds it.
    Reference.best(page, rect_pts, page_height_pts, min_confidence)
        The single best entry at or above a confidence floor, or None.

Nothing here rewrites our output. It answers "what does the other source say
about this rectangle, and how sure is it?".
"""
from __future__ import annotations

import json
from dataclasses import dataclass

PX_PER_PT = 250.0 / 72.0


@dataclass
class Entry:
    """One line from a MathPix lines.json."""
    page: int
    kind: str                      # text, math, diagram, table, ...
    region: tuple[float, float, float, float]   # pixels, y down
    text: str                      # LaTeX for math and tables, else plain
    confidence: float

    @property
    def is_table(self) -> bool:
        return "\\begin{tabular}" in self.text or "\\begin{array}" in self.text

    @property
    def is_math(self) -> bool:
        return self.kind == "math" or self.text.strip().startswith("\\[")


@dataclass
class Reference:
    by_page: dict[int, list[Entry]]

    def covering(self, page: int, rect_pts, page_height_pts: float
                 ) -> list[Entry]:
        """Entries overlapping a PDF-point rectangle, best overlap first."""
        want = _to_px(rect_pts, page_height_pts)
        area = max((want[2] - want[0]) * (want[3] - want[1]), 1.0)
        hits: list[tuple[float, Entry]] = []
        for e in self.by_page.get(page, ()):
            ox = min(want[2], e.region[2]) - max(want[0], e.region[0])
            oy = min(want[3], e.region[3]) - max(want[1], e.region[1])
            if ox > 0 and oy > 0:
                hits.append((ox * oy / area, e))
        hits.sort(key=lambda t: -t[0])
        return [e for _, e in hits]

    def best(self, page: int, rect_pts, page_height_pts: float,
             min_confidence: float = 0.0) -> Entry | None:
        for e in self.covering(page, rect_pts, page_height_pts):
            if e.confidence >= min_confidence and e.text.strip():
                return e
        return None


def _to_px(rect_pts, page_height_pts: float):
    """PDF points, y up -> lines.json pixels, y down from the top."""
    x0, y0, x1, y1 = rect_pts
    k = PX_PER_PT
    return (x0 * k, (page_height_pts - y1) * k,
            x1 * k, (page_height_pts - y0) * k)


def load(path: str) -> Reference:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    by_page: dict[int, list[Entry]] = {}
    for page in doc.get("pages", []):
        pno = int(page.get("page", 0))
        entries: list[Entry] = []
        for line in page.get("lines", []):
            reg = line.get("region") or {}
            if not reg:
                continue
            x, y = float(reg["top_left_x"]), float(reg["top_left_y"])
            entries.append(Entry(
                page=pno,
                kind=str(line.get("type", "")),
                region=(x, y, x + float(reg["width"]),
                        y + float(reg["height"])),
                text=str(line.get("text") or ""),
                confidence=float(line.get("confidence") or 0.0)))
        if entries:
            by_page[pno] = entries
    return Reference(by_page=by_page)
