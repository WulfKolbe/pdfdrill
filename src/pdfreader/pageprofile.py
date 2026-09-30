r"""pageprofile — WHAT IS ON THIS PAGE, and on what evidence. Not how much.

781o — COUNTING MAKES NO SENSE, AND A 132-PAGE MANUAL SHOWS WHY.

`pdftc_900k_1018.pdf` carries 10,368 monospace glyphs and 170 rows of
listing. Counting monospace glyphs calls it a code document; counting
listing rows calls it prose. Both are wrong about the same page, because
the monospace is mostly INLINE -- command names in running text -- and
inline code and a code block are different things that a count cannot
separate.

What a reader can say instead is WHICH PROPERTIES A PAGE HAS, each with
the measurement that decided it:

    p37   listing: 1 block, 22 rows, cell 5.52pt
          inline-math: 4 prose lines carrying maths

That is a triage instrument. Over those 132 pages it says listings are on
37 of them and a coloured frame on 13 -- so a paid OCR pass over the whole
document buys 132 pages of billing for content that lives on 37.

TWO RULES, both learned elsewhere in this reader.

  EVIDENCE, NOT A BOOLEAN. `listing: true` cannot be acted on;
  `listing: 3 blocks, 47 rows, cell 4.71pt, lang python` can.

  ABSTAIN RATHER THAN GUESS. A property that is not established is absent,
  not false. The language lookup already works this way -- 34 of 34
  correct when it speaks, silent 78 times of 112 -- because a guess is
  what sends a file to a paid API.

Everything here is computed from the glyph and rule model that `build()`
already produced. No rasterising, no key, no network.

NAMED `pageprofile` AND NOT `profile`: this folder is flat and every module
imports by bare name, so a file called `profile.py` SHADOWS THE STANDARD
LIBRARY'S. It did, for about an hour, and the symptom was `cProfile`
refusing to import at all --

    AttributeError: module 'profile' has no attribute 'run'

-- which means nobody could profile this reader while the module that
profiles PAGES was sitting in the path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import texmap

#: Below this many loose monospace glyphs, a page is not "inline code" --
#: a single `\texttt{n}` in a paragraph is not a property of the page.
INLINE_CODE_MIN = 8

#: A drawn rectangle shorter than this is a rule or a header bar, not a
#: box around content.
BOX_MIN_HEIGHT = 20.0


@dataclass
class PageProfile:
    """The properties of one page, each mapped to its evidence."""
    page: int = 0
    props: dict = field(default_factory=dict)

    def __contains__(self, key: str) -> bool:
        return key in self.props

    def __str__(self) -> str:
        return "p%-4d %s" % (self.page,
                             "; ".join("%s: %s" % kv for kv in self.props.items()))


def _display_and_inline_math(page) -> tuple:
    disp = inline = 0
    for ln in page.lines:
        kinds = {s.kind for s in ln.spans if s.glyphs}
        if not kinds:
            continue
        if kinds == {"math"}:
            disp += 1
        elif "math" in kinds:
            inline += 1
    return disp, inline


def page_profile(page) -> PageProfile:
    """Every property this page has, with what established it."""
    f: dict = {}
    out = PageProfile(page=getattr(page, "page", 0), props=f)
    glyphs = [g for ln in page.lines for g in ln.glyphs]
    if not glyphs:
        f["no-text-layer"] = "no glyphs — this page needs OCR"
        return out
    if getattr(page, "invisible", False):
        f["invisible-text"] = "every glyph invisible — an OCR layer already"

    listings = getattr(page, "listings", [])
    if listings:
        rows = sum(x.line_count for x in listings)
        lang = listings[0].language
        f["listing"] = ("%d block(s), %d rows, cell %.2fpt, %s"
                        % (len(listings), rows, listings[0].cell,
                           ("language %s (from %s)"
                            % (lang, listings[0].language_source)) if lang
                           else "language not established"))

    in_block = {id(g) for x in listings for ln in page.lines
                if ln.id in x.ids for g in ln.glyphs}
    loose = [g for g in glyphs
             if texmap.is_monospace(g.fontname) and id(g) not in in_block]
    if len(loose) >= INLINE_CODE_MIN:
        # 781o -- the property a COUNT cannot see. 10,368 monospace glyphs
        # on a page set with 170 rows of listing are not a listing.
        f["inline-code"] = ("%d monospace glyph(s) outside any block"
                            % len(loose))

    boxes = [r for r in getattr(page, "frames", ())
             if r[3] - r[1] > BOX_MIN_HEIGHT]
    if boxes:
        f["frame"] = "%d drawn box(es)" % len(boxes)
    fills = [x for x in getattr(page, "fills", ())
             if x.color and min(x.color) < 0.98]
    if fills:
        f["coloured-fill"] = ("%d filled area(s), e.g. rgb %s"
                              % (len(fills),
                                 ",".join("%.2f" % v for v in fills[0].color)))
    if boxes and fills:
        f["coloured-frame"] = "a drawn box with a fill behind it"
    if getattr(page, "diagrams", None):
        f["diagram"] = "%d region(s) of marks" % len(page.diagrams)

    disp, inline = _display_and_inline_math(page)
    if disp:
        f["equation"] = "%d display line(s)" % disp
    if inline:
        f["inline-math"] = "%d prose line(s) carrying maths" % inline
    if any(ln.rotated for ln in page.lines):
        f["rotated-text"] = "sideways glyphs present"
    # 781p — THE FONT WE CANNOT READ. pdfminer hands back `(cid:123)` for a
    # glyph no encoding resolves, and a page of those produces text, lines
    # and even listings that are all describing nothing.
    import re as _re
    txt = "".join(g.text for g in glyphs)
    ph = sum(len(m.group(0)) for m in _re.finditer(r"\(cid:\d+\)", txt))
    if txt and ph > 0.30 * len(txt):
        f["unmapped-glyphs"] = ("%d%% of the text is (cid:N) — the font's "
                                "encoding is unreadable" % (100 * ph // len(txt)))
    return out


def document_profile(pages) -> dict:
    """{property: [page numbers]} — where each property actually is.

    A roll-up to a boolean would hide the only thing worth knowing: a
    132-page manual whose listings live on 37 pages is not a 132-page
    listing problem.
    """
    where: dict = {}
    for p in pages:
        for k in page_profile(p).props:
            where.setdefault(k, []).append(getattr(p, "page", 0))
    return where


def summary(pages) -> list:
    """The document's properties, most widespread first, as plain lines."""
    n = len(pages) or 1
    where = document_profile(pages)
    out = ["%d page(s)" % n]
    for k, ps in sorted(where.items(), key=lambda kv: -len(kv[1])):
        span = ("p%d" % ps[0]) if len(ps) == 1 else \
               ("%d pages, first p%d" % (len(ps), ps[0]))
        out.append("  %-16s %4d  %3.0f%%   %s" % (k, len(ps), 100*len(ps)/n, span))
    return out
