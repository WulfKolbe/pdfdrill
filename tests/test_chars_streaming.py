"""The born-digital lane must not hold a whole book in memory.

`char_records` returns every glyph of every page as a dict, `_pdfminer_char_dump`
copies them into per-page lists, and `chars_to_lines_json` copies those again
into its own items — three live copies of the entire document.

Measured: 1,296,613 glyphs of a 491-page book = 2.2 GB RSS, ~1.7 KB per glyph.
The library holds a 6216-page manual and a 2909-page textbook, which scale to
tens of GB — the 54 GB the rebuild was seen holding.

Nothing about the work needs the whole document at once: columns, words and
lines are all decided WITHIN a page. So pages are processed one at a time and
their glyphs released, and the result must be byte-identical to the old path —
a faster/leaner route that changes the output is not the same route.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import chars_to_lines as C


def _page(n, texts, y0=700.0):
    """One page of chars: each string becomes a line of glyphs."""
    chars = []
    for li, t in enumerate(texts):
        for i, ch in enumerate(t):
            chars.append({"text": ch, "x0": 100.0 + 7 * i, "x1": 106.0 + 7 * i,
                          "y0": y0 - 20 * li, "y1": y0 + 10 - 20 * li,
                          "fontname": "TimesNewRomanPSMT"})
    return {"page_number": n, "width": 612.0, "height": 792.0, "chars": chars}


def _pages():
    return [_page(1, ["First page line one", "and a second line here"]),
            _page(2, ["Second page opening", "with more text on it"]),
            _page(3, ["Third page content", "trailing line of text"])]


def test_streaming_output_is_identical_to_whole_document():
    pages = _pages()
    whole = C.chars_to_lines_json({"pages": pages, "source": "pdfminer-chars"})
    streamed = C.lines_json_streaming(iter(_pages()), source="pdfminer-chars")
    assert json.dumps(streamed, sort_keys=True) == json.dumps(whole, sort_keys=True)


def test_streaming_releases_each_page():
    """The generator must be consumed lazily and each page dropped after use —
    holding them all is the bug, not an implementation detail."""
    seen = []

    def gen():
        for p in _pages():
            seen.append(p["page_number"])
            yield p

    out = C.lines_json_streaming(gen(), source="pdfminer-chars")
    assert seen == [1, 2, 3]
    assert [p["page"] for p in out["pages"]] == [1, 2, 3]
    # the caller's page dicts must not be retained by the result
    assert all("chars" not in p for p in out["pages"])


def test_math_typing_survives_streaming():
    """`math_lines_typed` is computed per page and summed, not over one big blob."""
    math = _page(1, ["x=y"])
    for c in math["chars"]:
        c["fontname"] = "GAAAAA+OpenSymbol"
    out = C.lines_json_streaming(iter([math]), source="pdfminer-chars")
    assert out["math_lines_typed"] == 1
    assert [l["type"] for p in out["pages"] for l in p["lines"]] == ["math"]


def test_chunked_reopen_keeps_absolute_page_numbers():
    """`extract_pages(page_numbers=…)` restarts ITS enumeration at 0 per call.

    Numbering pages from the chunk-local index would label page 101 as page 1,
    and every region, line id and page reference downstream would point at the
    wrong page — a silent corruption far worse than the memory it saves.
    """
    from pdfdrill.pdfminer_layer import _iter_layouts_chunked

    PAGES = [f"p{i}" for i in range(250)]

    def fake_extract(_path, page_numbers=None):
        for i in (page_numbers if page_numbers is not None else range(len(PAGES))):
            if i < len(PAGES):
                yield PAGES[i]

    got = list(_iter_layouts_chunked(fake_extract, "x.pdf", chunk=100))
    assert [i for i, _ in got] == list(range(250))
    assert [lay for _, lay in got] == PAGES


def test_chunking_stops_at_the_end_without_an_extra_pass():
    from pdfdrill.pdfminer_layer import _iter_layouts_chunked
    calls = []

    def fake_extract(_path, page_numbers=None):
        calls.append(tuple(page_numbers)[:1])
        for i in page_numbers:
            if i < 150:
                yield f"p{i}"

    got = list(_iter_layouts_chunked(fake_extract, "x.pdf", chunk=100))
    assert len(got) == 150
    assert len(calls) == 2, calls        # 0-99 full, 100-199 short -> stop
