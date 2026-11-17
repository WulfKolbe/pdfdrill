r"""A float's rectangle from the PDF's own figure, for a source-built model.

WHY A SOURCE MODEL HAS NO FIGURE BOXES
--------------------------------------
`merge_page_geometry` places an object by matching its opening words against
the page's text, and a float has no text to match: an `\includegraphics` is a
file name. What it reaches instead is the CAPTION, so the box a float ends up
with is the caption's line -- measured on the owner's arxiv.2209.02970 page 9,
`top_left_x 127.38, top_left_y 195.17, width 340.51, height 9.96`, which is one
line of type under a figure 2001 x 502 pixels tall.

`_FLOAT_TYPES` therefore refuses to interpolate a float at all: "A float's
rectangle comes from a MEASUREMENT or not at all". This module is that
measurement for the commonest producer.

WHAT THE PDF STATES
-------------------
`pdflatex` embeds an `\includegraphics` figure as a form XObject, which
pdfminer reports as an `LTFigure` among the PAGE'S DIRECT CHILDREN. Measured
read-only over the library (`work/run-files/t2209-pictures`):

    arxiv.2009.07239   12 `.pdf` figures   12 top-level LTFigures   140 nested
    arxiv.2306.01527   16 `.pdf` figures   16 top-level LTFigures   127 nested
    arxiv.1006.2374    36 `.eps` figures  246 "LTFigures", all 1x1 stencil masks

so on the pdftex family the correspondence is one-to-one, and on dvips there is
nothing to find -- the figure is drawn straight into the content stream. The
NESTED forms are Type3 glyph forms inside the embedded figure, up to 65 on one
page, which is why only direct children count. No whole-page box appeared
anywhere in the corpus pass (0 of 1,798).

THE RULE, AND WHY IT IS THIS NARROW
-----------------------------------
A page qualifies when it carries exactly ONE float of this document and exactly
ONE top-level figure. Then the pairing is forced and needs no reasoning about
which figure belongs to which caption. Over 42 documents holding
`\includegraphics` floats, that rule reaches 43 of 265 floats on 18 documents;
the rest are ambiguous pages (41) or pages that offer nothing measurable (49,
of which 47 are dvips).

A float whose page came from a CJK caption is a known wrong-page case -- the
caption probe keeps only `[a-z0-9 ]`, so a Chinese caption reduces to its
embedded Latin fragment and can match body prose on another page. The
one-float-one-figure test rejects that for free: the wrongly matched page
carries no figure at all.

The box replaces a caption-line box or fills a missing one, and nothing else:
a float that already has a box taller than one line was measured, not matched,
and a measurement is not overwritten by this.
"""
from __future__ import annotations

import re
from pathlib import Path

#: The types `_FLOAT_TYPES` protects from interpolation, which are exactly the
#: ones with no text of their own to match.
FLOATS = ("Picture", "Diagram", "Figure", "Chart")

#: A figure small enough to be a rule, a logo or a stencil mask is not the
#: page's figure. 20 pt square, the same floor the corpus pass used.
MIN_PT = 20.0

#: Markup that carries no text on the page, dropped whole so a caption probe
#: is the words a reader sees.
_DROP = re.compile(
    r"\\(?:label|ref|eqref|cref|Cref|cite[a-zA-Z]*|footnote|protect)\s*\{[^{}]*\}")


def strip_markup(s: str) -> str:
    r"""A caption as its printed words: `\label{...}` and friends dropped whole,
    every other command name dropped but its argument text kept."""
    s = _DROP.sub(" ", s)
    s = re.sub(r"\\[a-zA-Z@]+\*?\s*", " ", s)
    for ch in "{}$\\":
        s = s.replace(ch, " ")
    return s


def top_level_figures(pdf: Path, want_pages: set[int] | None = None) -> dict:
    """{page number: [(x0, y0, x1, y1), ...]} for the page's own figures.

    Direct children only, and nothing under `MIN_PT` square. Returns {} when
    pdfminer cannot read the file, because a missing measurement must leave the
    model as it was.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams, LTFigure
    except Exception:                                        # noqa: BLE001
        return {}
    out: dict[int, list] = {}
    try:
        for pno, page in enumerate(extract_pages(str(pdf), laparams=LAParams()), 1):
            if want_pages is not None and pno not in want_pages:
                continue
            figs = []
            for o in (getattr(page, "_objs", []) or []):
                if not isinstance(o, LTFigure):
                    continue
                if o.x1 - o.x0 >= MIN_PT and o.y1 - o.y0 >= MIN_PT:
                    figs.append((o.x0, o.y0, o.x1, o.y1, page.height))
            if figs:
                out[pno] = figs
    except Exception:                                        # noqa: BLE001
        return out
    return out


def _median_line_height(doc) -> float:
    hs = []
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        r = (o.props or {}).get("region") or {}
        h = float(r.get("height") or 0)
        if 5.0 < h < 40.0:
            hs.append(h)
    hs.sort()
    return hs[len(hs) // 2] if hs else 11.0


def _page_frames(doc) -> dict:
    """{page number: (width, height)} in the frame the model's regions use.

    `merge_page_geometry` writes `page_width`/`page_height` on each Page object,
    taken from the reading. For a source-built model whose reading is the PDF's
    own text layer that frame is POINTS and the scale below is 1; for a MathPix
    reading it is pixels and the scale converts. Reading the frame off the model
    rather than assuming either is what makes the same rule right for both.
    """
    out = {}
    for o in doc.objects.values():
        if o.type != "Page":
            continue
        p = o.props or {}
        n = p.get("page_number")
        if n:
            out[int(n)] = (float(p.get("page_width") or 0),
                           float(p.get("page_height") or 0))
    return out


def page_from_caption(doc, lines_path, floats) -> int:
    r"""Give a float a page from its CAPTION, with the markup stripped.

    A float that `merge_page_geometry` could not place has no page at all --
    measured, 0 of 490 unboxed floats in a 300-document sample carry one -- so
    without this the figure rule can only ever REPLACE a caption-line box and
    never fill a missing one. The match fails on raw source because the
    caption's first words are commands: `\label{...}` and friends carry no
    text on the page, and every other command's name is not printed while its
    argument is. Stripping both fixed 63 of 195 unmatched captions over 26
    documents.

    Returns how many floats were given a page. A caption that matches no page
    leaves the float as it was: a float with no page is honest, a float on the
    wrong page is not.
    """
    if not lines_path:
        return 0
    try:
        import json
        from .commands import _norm_probe
        data = json.loads(Path(lines_path).read_text(encoding="utf-8",
                                                     errors="replace"))
    except Exception:                                        # noqa: BLE001
        return 0
    page_text = []
    for pg in (data.get("pages") or []):
        parts = [_norm_probe(str(l.get("text") or "")) for l in (pg.get("lines") or [])]
        page_text.append(" ".join(p for p in parts if p))
    placed = 0
    for o in floats:
        p = o.props or {}
        if p.get("page"):
            continue
        probe = " ".join(_norm_probe(strip_markup(str(p.get("caption") or ""))).split()[:8])
        if len(probe) < 12:
            continue
        hit = next((i for i, t in enumerate(page_text, 1) if t.find(probe) >= 0), None)
        if hit:
            p["page"] = hit
            p["page_via"] = "stripped_caption"
            placed += 1
    return placed


def figure_boxes(doc, pdf: Path, lines_path=None) -> dict:
    r"""Give a float the box of its page's figure, where the page states one.

    Only where the page carries exactly one float of this document and exactly
    one top-level figure, and only to replace a caption-line box or fill a
    missing one. Returns counters; the document is changed in place.
    """
    stats = {"figurebox_pages_offered": 0, "figurebox_filled": 0,
             "figurebox_replaced_caption_line": 0, "figurebox_kept_measured": 0,
             "figurebox_ambiguous": 0, "figurebox_page_from_caption": 0}
    floats = [o for o in doc.objects.values() if o.type in FLOATS]
    if not floats:
        return stats
    stats["figurebox_page_from_caption"] = page_from_caption(doc, lines_path, floats)
    by_page: dict[int, list] = {}
    for o in floats:
        pno = (o.props or {}).get("page")
        if pno:
            by_page.setdefault(int(pno), []).append(o)
    if not by_page:
        return stats
    figs = top_level_figures(Path(pdf), set(by_page))
    if not figs:
        return stats
    frames = _page_frames(doc)
    one_line = 1.8 * _median_line_height(doc)
    for pno, here in by_page.items():
        page_figs = figs.get(pno) or []
        if len(here) != 1 or len(page_figs) != 1:
            if page_figs:
                stats["figurebox_ambiguous"] += len(here)
            continue
        stats["figurebox_pages_offered"] += 1
        pw_px, ph_px = frames.get(pno, (0.0, 0.0))
        x0, y0, x1, y1, ph_pt = page_figs[0]
        if not (pw_px and ph_px and ph_pt):
            continue
        k = ph_px / ph_pt                     # the reading's pixels per point
        box = {"top_left_x": round(x0 * k, 2),
               "top_left_y": round((ph_pt - y1) * k, 2),
               "width": round((x1 - x0) * k, 2),
               "height": round((y1 - y0) * k, 2)}
        o = here[0]
        old = (o.props or {}).get("region")
        if old and float(old.get("height") or 0) > one_line:
            stats["figurebox_kept_measured"] += 1
            continue                           # a real measurement stands
        o.props["region"] = box
        o.props["region_via"] = "pdf_figure"
        if old:
            stats["figurebox_replaced_caption_line"] += 1
        else:
            stats["figurebox_filled"] += 1
    return stats
