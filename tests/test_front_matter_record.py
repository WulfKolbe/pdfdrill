"""A scanned book's own title page is the record `bibtex` could not find.

`pdfdrill bibtex` on a 174-page scanned book (WDorg4) returned
`@misc{unknown, pages = {174}}`, because it reads the PDF's embedded metadata
and this book has none. Everything a real record needs was already in the OCR
and unused:

    p3  [authors] 'Walter Dröscher / Burkhard Heim'
    p3  [title  ] ''                       <- typed, but empty
    p3  [text   ] 'Strukturen' / 'der physikalischen Welt' / 'und'
                  / 'ihrer nichtmateriellen Seite'
    p4  [text   ] 'ISBN 3-85382-059-X'     <- already found by `identifiers`

Two reasons it was lost: the title scan stopped after page 2 (a book's title
page sits behind a half-title and a series page), and an empty typed title
line yielded nothing even though the title text is right beneath it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.modules.page import _extract_title, _extract_authors


def _lines(pages):
    return {"pages": [{"page": i + 1, "lines": ls} for i, ls in enumerate(pages)]}


def test_a_title_on_page_one_still_wins_unchanged():
    """The common case must not move: papers put the title on page 1."""
    doc = _lines([[{"type": "title", "text": "Auto-Encoding Variational Bayes"},
                   {"type": "authors", "text": "D. P. Kingma, M. Welling"}]])
    assert _extract_title(doc) == "Auto-Encoding Variational Bayes"


def test_a_books_title_page_is_found_behind_the_front_matter():
    """Half-title, series page, THEN the title page — page 3, not page 1."""
    doc = _lines([
        [{"type": "text", "text": "Walter Dröscher - Burkhard Heim"}],
        [{"type": "text", "text": "BURKHARD HEIM"}],
        [{"type": "authors", "text": "Walter Dröscher / Burkhard Heim"},
         {"type": "title", "text": ""},
         {"type": "text", "text": "Strukturen"},
         {"type": "text", "text": "der physikalischen Welt"},
         {"type": "text", "text": "und"},
         {"type": "text", "text": "ihrer nichtmateriellen Seite"},
         {"type": "page_info", "text": "RESCH VERLAG INNSBRUCK 1996"}],
    ])
    assert _extract_title(doc) == ("Strukturen der physikalischen Welt und "
                                   "ihrer nichtmateriellen Seite")


def test_the_publisher_line_is_not_part_of_the_title():
    doc = _lines([[{"type": "title", "text": ""},
                   {"type": "text", "text": "A Short Title"},
                   {"type": "page_info", "text": "RESCH VERLAG INNSBRUCK 1996"},
                   {"type": "text", "text": "printed in Austria"}]])
    assert _extract_title(doc) == "A Short Title"


def test_a_page_of_prose_is_not_read_as_a_title():
    """The empty-title fallback must stay on a real title page: bounded to a
    few short lines, so a text-heavy page cannot become a 300-character
    'title'."""
    prose = [{"type": "title", "text": ""}] + [
        {"type": "text", "text": "This is an ordinary sentence of body prose "
                                 "that runs on at some length indeed."}
        for _ in range(9)]
    assert _extract_title(_lines([prose])) == ""


def test_a_series_page_of_short_lines_is_not_a_title():
    """The char cap alone does not catch this: a front-matter series listing is
    many SHORT lines, well under 200 characters in total. Both caps are real."""
    page = [{"type": "title", "text": ""}] + [
        {"type": "text", "text": f"Bd. {i}"} for i in range(1, 9)]
    assert _extract_title(_lines([page])) == ""


def test_children_ids_still_resolve():
    doc = _lines([[{"type": "title", "text": "", "children_ids": ["a", "b"]},
                   {"id": "a", "type": "text", "text": "Split"},
                   {"id": "b", "type": "text", "text": "Title"}]])
    assert _extract_title(doc) == "Split Title"


# ------------------------------------------------------------------- authors
def test_the_typed_authors_line_is_captured():
    """MathPix types it. Nothing read it, so every scanned book was authorless."""
    doc = _lines([[{"type": "authors", "text": "Walter Dröscher / Burkhard Heim"}]])
    assert _extract_authors(doc) == "Walter Dröscher / Burkhard Heim"


def test_no_authors_line_is_not_an_error():
    assert _extract_authors(_lines([[{"type": "text", "text": "hello"}]])) == ""


# ------------------------------------------------------------ imprint page
from docmodel.modules.page import _extract_pub_year


def test_the_copyright_year_is_read_from_the_imprint_page():
    """`© 1996 by Andreas Resch Verlag` — the publication year a scanned book
    states about itself, which left the record as `@book{drscher}` with no
    year and so an unusable citekey."""
    doc = _lines([[{"type": "text", "text": "Alle Rechte vorbehalten."},
                   {"type": "text", "text": "© 1996 by Andreas Resch Verlag, Innsbruck"},
                   {"type": "text", "text": "ISBN 3-85382-059-X"}]])
    assert _extract_pub_year(doc) == "1996"


def test_the_copyright_symbol_may_be_spelled_out():
    doc = _lines([[{"type": "text", "text": "Copyright (c) 2004 by Springer"}]])
    assert _extract_pub_year(doc) == "2004"


def test_a_bare_year_in_prose_is_not_a_copyright_year():
    """A front-matter page mentioning a date must not supply the imprint."""
    doc = _lines([[{"type": "text", "text": "Written between 1975 and 1980."}]])
    assert _extract_pub_year(doc) == ""


def test_the_earliest_copyright_year_wins_over_a_later_reprint_line():
    """A reprint page lists both; the work's year is the first one."""
    doc = _lines([[{"type": "text", "text": "© 1996 by Andreas Resch Verlag"},
                   {"type": "text", "text": "© 2004 second printing"}]])
    assert _extract_pub_year(doc) == "1996"
