"""The document tiddler says how much of the document the reading covers.

A reading can cover PART of a document. One 11,232-page volume in the library
has a reading of its first 5,000 pages -- the provider stopped there; no cap
exists in this code -- and the projection said "Pages: 5000" with nothing to
suggest the other 6,232 were missing. A wiki built from it looked complete at
44%, which is the failure this line exists to prevent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops.projectors.tiddlywiki import TiddlyWikiProjector as P


def _body(read: int, pdf_pages: int) -> str:
    return P._root_body("KEY", "KEY", [object()] * read, [], [], [], [],
                        {}, pdf_pages=pdf_pages)


def test_partial_reading_states_both_counts_and_the_share():
    out = _body(5000, 11232)
    assert "- Pages: 5000 of 11232 in the PDF (45% read)" in out


def test_complete_reading_keeps_the_plain_count():
    assert "- Pages: 12\n" in _body(12, 12)
    assert " of " not in _body(12, 12).split("\n")[2] + _body(12, 12)


def test_no_pdf_count_available_keeps_the_plain_count():
    # An old model projected without the PDF in hand: say what is known, not 0.
    assert "- Pages: 12" in _body(12, 0)
    assert "of 0" not in _body(12, 0)


def test_a_reading_longer_than_the_pdf_is_not_reported_as_partial():
    # Page objects can outnumber the PDF's pages (a reading that splits a
    # spread). Never print "9 of 7", and never a share above 100%.
    out = _body(9, 7)
    assert "- Pages: 9" in out
    assert "of 7" not in out


if __name__ == "__main__":
    for fn in (test_partial_reading_states_both_counts_and_the_share,
               test_complete_reading_keeps_the_plain_count,
               test_no_pdf_count_available_keeps_the_plain_count,
               test_a_reading_longer_than_the_pdf_is_not_reported_as_partial):
        fn()
        print("ok", fn.__name__)
