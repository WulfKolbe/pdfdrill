"""T-0011 — a paragraph that runs over a page turn is one paragraph, and the
band of folio, running head, copyright line and licence stamp is not text.

The pdfplumber/md route has no `continues_line_*` subtype to read the join
off, so every statement here is geometric: a line's y against the band the
body text occupies, and whether the line before the turn ends a sentence.
These tests build that geometry directly rather than through a document, so
what is under test is the rule and not one PDF's luck.
"""
from __future__ import annotations

import pytest

from pdfdrill.context import (
    CharMeta, DocMeta, DocumentContext, FURNITURE, HEADING, PageMeta, PARAGRAPH,
)
from pdfdrill.nodes.lines_paragraphs import LinesParagraphsNode
from pdfdrill.projectors.markdown import MarkdownProjector

PAGE_H = 800.0
BODY_TOP = 100.0          # first body line of a page
BODY_BOTTOM = 700.0       # last body line of a page
LINE_H = 12.0
MARGIN = 78.0             # the body left margin the node learns


def _build(pages: list[list[tuple[float, str]]], *,
           x0: float = MARGIN, sizes: dict[str, float] | None = None,
           bold: frozenset[str] = frozenset()):
    """(text, char_meta, page_meta) from `[[(y, line_text), ...], ...]`.

    One entry per page; `y` is the line's top, in PDF points from the top of
    the page. Lines are emitted in the order given, separated by "\\n", with
    "\\f" between pages — the shape `IngestPdfplumberNode` produces.

    `sizes` and `bold` are keyed by the LINE'S TEXT: a test that wants one
    line in a heading font says so by naming the line, not by counting lines
    (which moves whenever the fixture gains a running head).
    """
    sizes = sizes or {}
    text_parts: list[str] = []
    meta: list[CharMeta] = []
    line_no = 0
    for p, lines in enumerate(pages):
        for y, body in lines:
            size = sizes.get(body, 10.0)
            klass = "bold" if body in bold else "text"
            for ch in body:
                meta.append(CharMeta(font_class=klass, size=size, x0=x0,
                                     y0=y, x1=x0 + 5, y1=y + LINE_H, page=p,
                                     line_idx=line_no))
            text_parts.append(body)
            meta.append(CharMeta(page=p, line_idx=line_no))      # the "\n"
            text_parts.append("\n")
            line_no += 1
        if p < len(pages) - 1:
            meta[-1] = CharMeta(page=p, line_idx=line_no)
            text_parts[-1] = "\f"
    text = "".join(text_parts)
    assert len(text) == len(meta), (len(text), len(meta))
    return text, meta, [PageMeta(width=600.0, height=PAGE_H) for _ in pages]


def _spans(pages, **kw):
    text, meta, pm = _build(pages, **kw)
    ctx = DocumentContext(meta=DocMeta(source="t.pdf", pages=pm))
    ctx.graphemes = text
    ctx.char_meta = meta
    LinesParagraphsNode().run(ctx)
    return text, ctx


BODY = "the sentence runs on and on across the width of the page, wrapping"
BODY2 = "again and again so that the band estimate has long lines to learn"
TAIL = "and it does not stop at the foot of this page but carries straight"
HEAD2 = "on to the next page where the reader expects to find its ending."


def _long_page(ys: list[float], texts: list[str]) -> list[tuple[float, str]]:
    return list(zip(ys, texts))


def _doc_with_turn(*, continuation: str, footer="© 2019 Some Body    12",
                   running_head="A Running Head", last_line=TAIL,
                   pages_before=2):
    """A document whose paragraph runs over the turn between the last two
    pages, with a footer below the body band and a running head above it.

    EVERY page carries the head and the footer, because that is what makes
    them furniture: the same string in the same band, page after page. A
    running head on one page alone is not evidence of anything, and the
    detector is meant to decline it (see the test below).
    """
    def page(lines):
        return [(40.0, running_head), *lines, (BODY_BOTTOM + 60, footer)]

    # the filler pages' body lines are DISTINCT: a long line that repeats on
    # three pages is excluded from the band sample, which is right for a
    # licence stamp and wrong for a fixture that pastes the same sentence
    filler = [page([(BODY_TOP, f"{BODY} ({n})"), (BODY_TOP + 16, f"{BODY2} ({n})"),
                    (BODY_TOP + 32, f"and filler page {n} ends its sentence.")])
              for n in range(pages_before)]
    left = page([(BODY_TOP, BODY + " (left)"), (BODY_TOP + 16, BODY2 + " (left)"),
                 (BODY_TOP + 32, last_line)])
    right = page([(BODY_TOP, continuation), (BODY_TOP + 16, BODY2 + " (right)")])
    return filler + [left, right]


# ---------------------------------------------------------------------------
# the band
# ---------------------------------------------------------------------------

def test_the_footer_and_the_running_head_are_furniture_not_text():
    text, ctx = _spans(_doc_with_turn(continuation=HEAD2))
    furn = [s for s in ctx.L2 if s.kind == FURNITURE]
    bodies = [text[s.start:s.end].strip() for s in furn]
    assert "A Running Head" in bodies
    assert any(b.startswith("© 2019 Some Body") for b in bodies)
    for s in furn:
        assert (s.props or {}).get("why") in ("repeats", "rights", "folio")


def test_a_line_inside_the_body_band_is_never_furniture():
    # "12" sits where the text sits; in this route a bare number mid-page may
    # be a cross-reference or a table cell, and nothing here can tell which.
    pages = _doc_with_turn(continuation=HEAD2)
    pages[-1].insert(2, (BODY_TOP + 40, "12"))
    text, ctx = _spans(pages)
    assert "12" not in [text[s.start:s.end].strip()
                        for s in ctx.L2 if s.kind == FURNITURE]


def test_a_long_line_in_the_band_is_text_the_band_estimate_got_wrong():
    long_in_band = ("a listing line that overflows the band and is far too "
                    "long to be a folio or a running head at all")
    pages = _doc_with_turn(continuation=HEAD2)
    pages[-1].append((BODY_BOTTOM + 40, long_in_band))
    text, ctx = _spans(pages)
    assert long_in_band not in [text[s.start:s.end].strip()
                                for s in ctx.L2 if s.kind == FURNITURE]


def test_a_band_line_on_too_few_pages_with_no_rights_words_is_not_furniture():
    # A line in the band that says nothing about rights, is no folio, and
    # appears on ONE page is not evidence of anything. The route has no tag
    # tree to ask, so it declines rather than guesses.
    once = "Printed by hand"
    pages = _doc_with_turn(continuation=HEAD2)
    pages[-1][0] = (40.0, once)
    text, ctx = _spans(pages)
    assert once not in [text[s.start:s.end].strip()
                        for s in ctx.L2 if s.kind == FURNITURE]


# ---------------------------------------------------------------------------
# the page turn
# ---------------------------------------------------------------------------

def test_a_paragraph_that_runs_over_the_turn_is_one_paragraph():
    text, ctx = _spans(_doc_with_turn(continuation=HEAD2))
    crossing = [s for s in ctx.L2
                if s.kind == PARAGRAPH and (s.props or {}).get(
                    "continued_over_page_turn")]
    assert len(crossing) == 1
    body = text[crossing[0].start:crossing[0].end]
    assert TAIL in body and HEAD2 in body


def test_the_band_between_the_halves_is_recorded_as_a_hole():
    text, ctx = _spans(_doc_with_turn(continuation=HEAD2))
    para = next(s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("furniture_holes"))
    holes = (para.props or {})["furniture_holes"]
    assert len(holes) == 2                      # the footer and the next head
    for a, b in holes:
        assert para.start <= a < b <= para.end
        assert text[a:b].strip()


def test_a_sentence_that_ends_before_the_turn_stays_two_paragraphs():
    text, ctx = _spans(_doc_with_turn(
        continuation=HEAD2, last_line="and here the sentence ends properly."))
    assert not [s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("continued_over_page_turn")]


def test_a_heading_after_the_turn_does_not_continue_the_paragraph():
    pages = _doc_with_turn(continuation="2  A New Section")
    # the first content line of the new page is a heading: bigger font
    text, meta, pm = _build(pages, sizes={"2  A New Section": 18.0})
    ctx = DocumentContext(meta=DocMeta(source="t.pdf", pages=pm))
    ctx.graphemes, ctx.char_meta = text, meta
    LinesParagraphsNode().run(ctx)
    assert [s for s in ctx.L2 if s.kind == HEADING]
    assert not [s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("continued_over_page_turn")]


def test_an_indented_first_line_after_the_turn_starts_its_own_paragraph():
    pages = _doc_with_turn(continuation=HEAD2)
    text, meta, pm = _build(pages)
    # indent the new page's first content line by 20pt — a \parindent
    for cm in meta:
        if cm.page == len(pages) - 1 and cm.y0 == BODY_TOP:
            cm.x0 = MARGIN + 20
    ctx = DocumentContext(meta=DocMeta(source="t.pdf", pages=pm))
    ctx.graphemes, ctx.char_meta = text, meta
    LinesParagraphsNode().run(ctx)
    assert not [s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("continued_over_page_turn")]


def test_a_paragraph_never_ends_on_a_furniture_line():
    text, ctx = _spans(_doc_with_turn(continuation=HEAD2))
    for s in ctx.L2:
        if s.kind != PARAGRAPH:
            continue
        tail = text[s.start:s.end].rstrip().splitlines()[-1].strip()
        assert not tail.startswith("© 2019 Some Body")
        assert tail != "A Running Head"


# ---------------------------------------------------------------------------
# what the reader gets
# ---------------------------------------------------------------------------

def _markdown(pages, **kw):
    text, meta, pm = _build(pages, **kw)
    ctx = DocumentContext(meta=DocMeta(source="t.pdf", pages=pm))
    ctx.graphemes, ctx.char_meta = text, meta
    LinesParagraphsNode().run(ctx)
    return MarkdownProjector().project(ctx)


def test_the_markdown_carries_neither_the_folio_nor_the_running_head():
    md = _markdown(_doc_with_turn(continuation=HEAD2))
    assert "© 2019 Some Body" not in md
    assert "A Running Head" not in md


def test_the_two_halves_meet_with_one_space_and_no_paragraph_break():
    md = _markdown(_doc_with_turn(continuation=HEAD2))
    assert f"{TAIL} {HEAD2}" in md


@pytest.mark.parametrize("ender", [".", "!", "?", ":", ";"])
def test_every_sentence_ender_closes_the_paragraph_at_the_turn(ender):
    text, ctx = _spans(_doc_with_turn(
        continuation=HEAD2, last_line="the sentence ends here" + ender))
    assert not [s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("continued_over_page_turn")]


def test_a_line_ending_in_a_hyphen_continues_however_it_is_punctuated():
    text, ctx = _spans(_doc_with_turn(
        continuation="tinuation of the broken word follows here on page two.",
        last_line="the word is broken across the turn with a soft hy-"))
    crossing = [s for s in ctx.L2 if s.kind == PARAGRAPH
                and (s.props or {}).get("continued_over_page_turn")]
    assert len(crossing) == 1
