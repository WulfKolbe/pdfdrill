r"""770 — two defects the keyless `md` route had, both found on 2609.16055v1.

The user drilled an arXiv paper with no MathPix data and reported "a Markdown
with some pdf stream data". It was not stream data: arXiv stamps every
preprint sideways down the left margin of page 1, and those 40 characters were
interleaved into the abstract, reading bottom-to-top as
`arXiv:2609.16055v1 [cs.CL] 13 Sep 2026`.

The second is in the same file: `62$.$6%`. In math mode TeX takes `.` and `,`
from the math italic font, not from the roman the digits come from, so a
percentage written `$62.6\%$` arrives as CMR digits with one CMMI character
between them — and `.` is a BREAK_CHAR, so the span that survives is a lone
period.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.nodes.ingest_pdfplumber import IngestPdfplumberNode
from pdfdrill.nodes.math_detector import _absorb_decimal, _is_only_punctuation
from pdfdrill.context import DocMeta, DocumentContext


# --- sideways text --------------------------------------------------------

def _char(text, x0, top, upright=True):
    return {"text": text, "x0": x0, "x1": x0 + 6.0, "top": top,
            "bottom": top + 10, "y0": 700 - top, "y1": 710 - top,
            "width": 6.0, "height": 10.0, "size": 10.0,
            "fontname": "AAA+CMR10", "upright": upright}


def _page(body: str, stamp: str = ""):
    chars = [_char(c, 100 + 7 * i, 100) for i, c in enumerate(body)]
    # the stamp: one column of characters down the left margin, each on its
    # own `top`, exactly as pdfplumber reports a 90-degree run
    chars += [_char(c, 20, 60 + 11 * i, upright=False) for i, c in enumerate(stamp)]
    return {"page_number": 1, "width": 612, "height": 792, "chars": chars}


def _run(tmp_path, page):
    p = tmp_path / "chars.json"
    p.write_text(json.dumps({"source": "t.pdf", "total_pages": 1,
                             "pages": [page]}), encoding="utf-8")
    node = IngestPdfplumberNode(p)
    ctx = node.run(DocumentContext(meta=DocMeta(source="t.pdf")))
    return node, ctx


def test_the_arxiv_stamp_does_not_reach_the_text(tmp_path):
    node, ctx = _run(tmp_path, _page("Test-time compute", "arXiv:2609.16055v1"))
    assert "Test-time" in ctx.graphemes
    assert "arXiv" not in ctx.graphemes
    assert "2609" not in ctx.graphemes


def test_the_set_aside_characters_are_counted(tmp_path):
    """Counted is not shown, and shown is not silent: `md` prints this."""
    node, _ = _run(tmp_path, _page("Test-time compute", "arXiv:2609"))
    assert node.sideways_chars == len("arXiv:2609")
    assert node.sideways_pages == {1}


def test_an_upright_page_sets_nothing_aside(tmp_path):
    node, ctx = _run(tmp_path, _page("Test-time compute"))
    assert node.sideways_chars == 0
    assert "Test-time" in ctx.graphemes


def test_a_page_that_is_only_sideways_is_skipped_not_crashed(tmp_path):
    node, ctx = _run(tmp_path, _page("", "arXiv:2609"))
    assert node.sideways_chars == len("arXiv:2609")


# --- the math-font period -------------------------------------------------

def test_a_span_of_nothing_but_punctuation_is_not_maths():
    assert _is_only_punctuation(".") is True
    assert _is_only_punctuation(",") is True
    assert _is_only_punctuation(". ") is True


def test_a_span_with_any_content_survives():
    for s in ("62.6", "x", r"\alpha", "1"):
        assert _is_only_punctuation(s) is False


def test_an_empty_span_is_not_refused_here():
    """`s < e` already dropped it; this test pins that the refusal does not
    also claim empty spans, which would hide a different defect."""
    assert _is_only_punctuation("") is False


def test_a_decimal_point_pulls_in_its_number():
    r"""`38$.2%/36.$5%` — the span opens on the period after 38 and closes on
    the one before 5, because a digit scores zero and only bridges."""
    t = "38.2%/36.5%"
    assert t[slice(*_absorb_decimal(2, 9, t))] == "38.2%/36.5"


def test_absorption_leaves_an_ordinary_span_alone():
    t = "x+1"
    assert _absorb_decimal(0, 3, t) == (0, 3)


def test_absorption_does_not_run_past_a_non_digit():
    t = "see .5 here"
    assert t[slice(*_absorb_decimal(4, 6, t))] == ".5"


def test_a_comma_is_a_decimal_point_too():
    """German and French decimals, and TeX takes the comma from CMMI as well."""
    t = "38,2%"
    assert t[slice(*_absorb_decimal(2, 4, t))] == "38,2"
