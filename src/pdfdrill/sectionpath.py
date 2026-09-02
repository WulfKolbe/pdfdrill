"""506 — the section path for a math object, behind the gate 505 measured.

493 found that a book's TOC carries the depth a section path needs and cannot
place it on a page. 503 found the PDF already carries the map — /PageLabels —
and 505 measured what that map is worth:

    7 books with a real /PageLabels     833 of 853 entries land on the page
                                        they name                     97.7%
    2 books without one                   7 of 168                     4.2%

pypdf returns a synthetic ``1..N`` when the PDF has no /PageLabels, so
"offset 0, constant" is what a MISSING label table looks like, not a tidy
one. That is the whole gate: ``"/PageLabels" in reader.trailer["/Root"]``.

WHAT THE GATE REFUSES, AND WHY EACH ONE IS REFUSED SEPARATELY

    no /PageLabels        the printed-to-PDF map would be fictional. Two
                          books; 4.2% of their entries land correctly, which
                          is worse than no path at all because a wrong
                          section reads exactly like a right one.
    no parsable TOC       cardona's entries are unnumbered and paginated in
                          roman ('Introduction ..... v'), so nothing parses
                          and there is nothing to place.
    a sparse TOC          johnston has 55 entries for 492 pages and every one
                          of them lands correctly — but 24.6% of its math
                          objects sit far enough from the entry that labels
                          them for the label to be a chapter rather than a
                          section. Marked coarse rather than dropped: the
                          path is true, and its resolution is not what an
                          unqualified section path implies.

A path is returned with the evidence for it, never bare, so a consumer can
decline it on its own terms.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: a TOC line: a dotted number, a title, leaders, a printed page
TOC_ENTRY = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.{2,120}?)\s*\.{2,}\s*(\d+)\s*$")

#: How far an object may sit from the heading that labels it and still be
#: described by it. MEASURED, not chosen: over the six gated books the median
#: gap is 0-2 pages and the p90 is 2-5, except seven-sketches (p90 45) and
#: johnston (median 9, p90 113, max 140).
#:
#: A first cut gated on TOC DENSITY — entries per page — and it put voloshin
#: on the wrong side of the line at 0.244 against a threshold of 0.25, while
#: voloshin scored 74 of 74 in 505. Density is a proxy for the distance and
#: the distance is measurable, so the distance is what is used, PER OBJECT:
#: a book is not uniformly coarse, it is coarse in the stretches where its
#: TOC is thin.
GAP_SECTION = 5
GAP_CHAPTER = 30


def has_page_labels(pdf_path) -> bool:
    """Does the PDF carry a real /PageLabels? THE GATE."""
    try:
        import pypdf
        r = pypdf.PdfReader(str(pdf_path))
        return "/PageLabels" in r.trailer["/Root"]
    except Exception:
        return False


def printed_to_pdf(pdf_path) -> dict:
    """{printed arabic page: 1-based PDF page}. Empty when there are no labels."""
    if not has_page_labels(pdf_path):
        return {}
    import pypdf
    r = pypdf.PdfReader(str(pdf_path))
    out: dict = {}
    for i, label in enumerate(r.page_labels):
        if str(label).isdigit():
            out.setdefault(int(label), i + 1)
    return out


def toc_rows(model_path) -> list:
    """(number, title, printed page) for every Toc entry that parses."""
    try:
        model = json.loads(Path(model_path).read_text(encoding="utf-8",
                                                      errors="replace"))
    except (OSError, ValueError):
        return []
    rows = []
    for o in model.get("objects", []):
        if o.get("type") != "Toc":
            continue
        for e in (o.get("props") or {}).get("entries") or []:
            m = TOC_ENTRY.match(e)
            if m:
                rows.append((m.group(1), m.group(2).strip(), int(m.group(3))))
    return rows


def build(pdf_path, model_path) -> dict:
    """The lookup table, or a refusal that says which gate closed."""
    pdf_path, model_path = Path(pdf_path), Path(model_path)
    if not has_page_labels(pdf_path):
        return {"usable": False, "reason": "no /PageLabels — the "
                "printed-to-PDF map would be synthetic (505: 4.2%)"}
    rows = toc_rows(model_path)
    if not rows:
        return {"usable": False, "reason": "no TOC entry parses"}
    inv = printed_to_pdf(pdf_path)
    mapped = sorted({(inv[p], num, title) for num, title, p in rows if p in inv})
    if not mapped:
        return {"usable": False, "reason": "no TOC entry maps to a PDF page"}
    import pypdf
    n_pages = len(pypdf.PdfReader(str(pdf_path)).pages)
    density = len(mapped) / max(1, n_pages)
    return {"usable": True, "entries": mapped, "pages": n_pages,
            "density": round(density, 3)}


def path_for(table: dict, page) -> "dict | None":
    """The deepest TOC entry at or before `page`, with its evidence."""
    if not table.get("usable") or page is None:
        return None
    prior = [e for e in table["entries"] if e[0] <= int(page)]
    if not prior:
        return None
    pdf_page, num, title = prior[-1]
    gap = int(page) - pdf_page
    return {"number": num, "title": title, "starts_on_pdf_page": pdf_page,
            "pages_since_heading": gap,
            "granularity": ("section" if gap <= GAP_SECTION
                            else "chapter" if gap <= GAP_CHAPTER
                            else "distant")}
