"""
Text-layer URL harvesting — the tomgruber.org/stanford-cs300.pdf case.

A PowerPoint→Distiller export has ZERO link annotations (0 /URI, 0 /Annots), so
`links`/`urls` (which read the annotation layer) correctly find nothing — yet the
slides carry 6 visible URLs as plain TEXT. These pure helpers recover those, incl.
URLs the PDF wrapped across a line break (`http://www-\nsul.stanford.edu/...`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.links_layer import join_wrapped_urls, urls_from_text, text_layer_links


def test_urls_from_plain_text():
    t = "See http://www.bootstrap.org/ and https://a.example/x?y=1 (also www.foo.org)."
    got = [u for u, _ in urls_from_text(t)]
    assert "http://www.bootstrap.org/" in got
    assert "https://a.example/x?y=1" in got
    assert "www.foo.org" in got                       # trailing ")." stripped


def test_trailing_punctuation_stripped_not_path():
    assert [u for u, _ in urls_from_text("at http://x.org/a.html.")] == ["http://x.org/a.html"]
    assert [u for u, _ in urls_from_text("(http://x.org/p)")] == ["http://x.org/p"]


def test_join_wrapped_url_across_a_line_break():
    """The real slide: `http://www-` / `sul.stanford.edu/...` on the next line.
    A URL line ending in `-` or `/` continues on the following line."""
    t = ("Whither Academic Information Services by Mike Keller. http://www-\n"
         "sul.stanford.edu/staff/pubs/keller_biconf06_finalpaper.pdf\n")
    joined = join_wrapped_urls(t)
    assert "http://www-sul.stanford.edu/staff/pubs/keller_biconf06_finalpaper.pdf" in joined
    got = [u for u, _ in urls_from_text(joined)]
    assert "http://www-sul.stanford.edu/staff/pubs/keller_biconf06_finalpaper.pdf" in got


def test_join_does_not_glue_unrelated_lines():
    """A line that merely ENDS with a URL (no hyphen/slash cut) must NOT absorb
    the next line's prose."""
    t = "Read http://x.org/paper\nThis is the next sentence.\n"
    joined = join_wrapped_urls(t)
    assert "http://x.org/paper" in [u for u, _ in urls_from_text(joined)]
    assert "http://x.org/paperThis" not in joined


def test_complete_root_url_does_not_absorb_following_title():
    """The real over-join: a COMPLETE site-root URL ending in `/` at end of line
    (`http://www.bootstrap.org/`) followed by a book title must stay intact —
    `http://www.bootstrap.org/Netizens` is a URL that never existed."""
    t = ("http://www.bootstrap.org/\n"
         "Netizens: On the History and Impact of Usenet\n"
         "http://fredturner.stanford.edu/\n"
         "Collective Knowledge Systems\n")
    got = [u for u, _ in urls_from_text(join_wrapped_urls(t))]
    assert "http://www.bootstrap.org/" in got
    assert "http://fredturner.stanford.edu/" in got
    assert not any("Netizens" in u or "Collective" in u for u in got)


def test_slash_cut_joins_only_a_path_like_continuation():
    """A genuine mid-path wrap (next line is a lowercase path fragment) IS
    joined; an uppercase prose word is not."""
    t = "http://example.org/very/long/\npath/to/file.pdf\n"
    assert "http://example.org/very/long/path/to/file.pdf" in \
        [u for u, _ in urls_from_text(join_wrapped_urls(t))]


def test_text_layer_links_pages_and_dedup():
    pages = ["intro http://a.org/one", "http://a.org/one again, plus http://b.org/two"]
    got = text_layer_links(pages)
    assert [(l["url"], l["page"]) for l in got] == [
        ("http://a.org/one", 1), ("http://b.org/two", 2)]      # dedup, earliest page
    assert all(l["kind"] == "text" for l in got)               # marked as text-layer
