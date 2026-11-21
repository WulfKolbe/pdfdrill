"""A lines.json `text` carries the page's text, not a note to the reader.

`span_text` renders an untypeable maths span as `<!-- DEFERRED <id> rect=[...]
reason=... -->`, which is right for `to_markdown`: it tells a person where the
reading gave up. Put into a lines.json `text` field the same string is read by
every consumer as the line's text. The ink judge TYPESETS it, so a line of
prose grows a run of visible angle brackets and flags every glyph in it, and a
CER against the page's own text layer is charged for the whole comment.

Measured on two board pages (drillgroup board 010a31b), by re-reading each page
with `pdfdrill glyphlines` before and after the change:

    lib:c9daf79960c3 p68   CER 0.7521 -> 0.1232   (MathPix 0.1799)
    1805.01788 p3          CER 0.2866 -> 0.0736   (MathPix 0.0621)

so `span_reading_text` returns the characters the page carries instead. The
deferral is not lost: the line record already states it three ways
(`deferred_glyphs`, `complete: false`, `confidence: 0.0`).

T-0156 — AND THE READING ALSO CARRIES THE FACE. `span_reading_text` wraps a
prose span in `\textbf`/`\textit`/`\texttt`/`\textsc` when every glyph of it
agrees, because the ink judge sets each line from this field and takes only
the font family from the page (`inkdrill judge.py:1269`). That makes the
reading and `span_text` differ for prose, which they did not before; the
equality test below now reads modulo those wrappers and still asserts the
thing this file is about, which is that a reading is not a projection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _glyph(text, x0, x1):
    """A glyph whose own LaTeX is unknown -- `tex.latex is None`."""
    return docmodel.GlyphNode(
        id="g%d" % int(x0), page=1, rect=(x0, 0.0, x1, 10.0), text=text,
        cid=0, glyphname=None, fontname="CMMI10", family="cm", size=10.0,
        tex=texmap.UNKNOWN)


def _span(kind, glyphs):
    xs = [g.rect[0] for g in glyphs] + [g.rect[2] for g in glyphs]
    return docmodel.Span(id="p1l0s3", kind=kind,
                         rect=(min(xs), 0.0, max(xs), 10.0), glyphs=glyphs)


def _untypeable():
    """Maths `span_latex` cannot express: every glyph's own LaTeX is None, so
    the structured route and the flat one both come back empty."""
    return _span("math", [_glyph("α", 0, 6), _glyph("β", 13, 19)])


def test_the_reading_keeps_the_characters_the_page_carries():
    out = docmodel.span_reading_text(_untypeable())
    assert "DEFERRED" not in out and "<!--" not in out, out
    assert "α" in out and "β" in out, out


def test_the_markdown_projection_still_says_where_it_gave_up():
    # span_text is the projection for people; it must NOT change.
    out = docmodel.span_text(_untypeable())
    assert out.startswith("<!-- DEFERRED "), out
    assert "reason=" in out


def test_prose_is_the_same_string_in_both_once_the_face_is_taken_off():
    r"""T-0156 — the two strings were IDENTICAL for prose, and are no longer.
    The reading now carries the face the page set a run in (`\textit{ab}`
    here, because the fixture's `CMMI10` is an italic face), because the ink
    judge sets each line from the reading and takes only the font family from
    the page; the markdown projection does not, because `**bold**` is what
    markdown would need and that is a separate change.

    THE INVARIANT THIS TEST EXISTS FOR IS UNCHANGED, and is what is asserted
    below: the reading is not a projection. It carries no `<!-- DEFERRED -->`
    comment and no note to a reader — only the page's characters, now with
    the page's face around them. Equality is therefore asserted modulo the
    wrappers, not abandoned.
    """
    sp = _span("text", [_glyph("a", 0, 6), _glyph("b", 7, 12)])
    reading = docmodel.span_reading_text(sp)
    assert texmap.unwrap_emphasis(reading) == docmodel.span_text(sp)
    assert "<!--" not in reading and "DEFERRED" not in reading, reading


def test_typed_maths_is_the_same_string_in_both():
    # Whatever span_latex CAN express stays `$...$` in the reading too, so the
    # change is confined to the spans that used to become a comment.
    sp = _span("math", [_glyph("x", 0, 6)])
    a, b = docmodel.span_reading_text(sp), docmodel.span_text(sp)
    if "DEFERRED" not in b:
        assert a == b


if __name__ == "__main__":
    for fn in (test_the_reading_keeps_the_characters_the_page_carries,
               test_the_markdown_projection_still_says_where_it_gave_up,
               test_prose_is_the_same_string_in_both_once_the_face_is_taken_off,
               test_typed_maths_is_the_same_string_in_both):
        fn()
    print("ok")
