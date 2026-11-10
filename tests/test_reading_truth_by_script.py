r"""Rung 2 — the reading is scored against an INDEPENDENT reader, per script.

THE GAP THIS CLOSES (owner, 2026-11-10)
---------------------------------------
The owner opened a bilingual Chinese/English paper and found no Chinese on page
one. There was none in the reading; there is in the PDF. 216 glyphs — all 11
Chinese characters on that page, plus the labels `Fengshenbang Model` and
`Erlangshen` — were dropped silently.

NO TEST COULD HAVE CAUGHT IT. This repo had four CJK test files
(`test_cjk_validator`, `test_cjk_text_scope`, `test_glyph_fallback`,
`test_glyphcensus`), 122 tests, 0.65 s, and NOT ONE OPENED A PDF. All four
assert that CJK is a DEFECT SIGNAL — MathPix hallucinating ideographs into
mathematics, xelatex dropping glyphs, a symbol emitted as radicals. None asserts
that Chinese text is READ CORRECTLY. A corpus of defect-detectors cannot notice
that the content itself is gone.

WHY AN INDEPENDENT READER AND NOT A STORED EXPECTATION
------------------------------------------------------
A frozen per-page character count is a snapshot of our own behaviour; it would
have been written from the broken reading and passed forever. `pdftotext` is a
different implementation of the same job, shipped by poppler, already a core
dependency. Where the two disagree about whether text EXISTS on a page, one of
them is losing it — and that is a question neither can answer about itself.

The comparison is deliberately one-sided: we may read MORE than pdftotext (it
drops things too), but a page where pdftotext finds characters and we find none
is a loss. The assertion is on presence and on order of magnitude, never on
equality, because two readers legitimately differ on hyphenation, ligatures,
spacing and column order.
"""
import os
import re
import subprocess
import unicodedata
from pathlib import Path

import pytest


def _cjk(s: str) -> int:
    return sum(1 for c in s if "一" <= c <= "鿿")


def _latin(s: str) -> int:
    return sum(1 for c in s if c.isascii() and c.isalpha())


def _library_pdf(doc_id: str):
    """The library copy of a document, or None. The suite must pass on a base
    install and in CI, where there is no library at all."""
    try:
        from pdfdrill import config, sources
        return sources.library_pdf_for(
            sources.archive_stem("arxiv", doc_id), config.library_root())
    except Exception:                       # noqa: BLE001
        return None


def _pdftotext_page(pdf: Path, page: int) -> str:
    r = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True, text=True, timeout=120)
    return r.stdout if r.returncode == 0 else ""


def _our_page_text(pdf: Path, page: int) -> str:
    """What the free born-digital route yields for one page, through the same
    seam `pdfdrill model` uses (`pdfminer_layer.iter_page_records`)."""
    from pdfdrill import pdfminer_layer as PM
    for pno, _w, _h, recs in PM.iter_page_records(str(pdf)):
        if pno == page:
            return "".join(r.get("text") or "" for r in recs)
        if pno > page:
            break
    return ""


# ---------------------------------------------------------------------------
# the measured case: a bilingual paper whose page 1 lost its Chinese
# ---------------------------------------------------------------------------

BILINGUAL = "2209.02970"

#: RESOLVED ONCE, AT IMPORT, and the tests use this constant rather than calling
#: the lookup again. `library_pdf_for` reads `config.library_root()`, which is
#: global, mutable state that other tests in the suite change — so the
#: `skipif` (evaluated at import) and a second call inside the test body
#: disagreed: these two tests passed alone and failed in the full suite with
#: `FileNotFoundError: 'None'`. A test that depends on mutable global state
#: passes in isolation and lies in company, which is the same family as
#: HANDOVER-RULES 46.
BILINGUAL_PDF = _library_pdf(BILINGUAL)


@pytest.mark.skipif(not BILINGUAL_PDF,
                    reason=f"the library does not hold {BILINGUAL}")
def test_a_figures_text_is_not_dropped_from_the_reading():
    """D1. `pdfminer_layer.iter_page_records.walk()` descended only into
    `LTTextContainer`; `LTFigure` is not one, so every glyph inside a figure was
    never visited. MEASURED on page 1 of 2209.02970: 216 glyphs skipped
    (203 `BCDEEE+MicrosoftYaHei` + 13 `BCDFEE+MicrosoftYaHei`), pdfplumber's
    pdfminer yielding 3,438 chars where this route yielded 3,222.

    Nothing was recorded as dropped, which is why it was silent: the glyphs
    never reached `_resolve_glyph`, so no unmapped-glyph note could mention
    them either.
    """
    pdf = BILINGUAL_PDF
    ours = _our_page_text(pdf, 1)
    assert _cjk(ours) == 11, (
        f"page 1 carries 11 Chinese characters (二郎神 闻仲 燃灯 太乙 余元); "
        f"the reading has {_cjk(ours)}")
    for label in ("Erlangshen", "Fengshenbang Model"):
        assert label.replace(" ", "") in ours.replace(" ", ""), (
            f"the figure label {label!r} is missing from the reading")


@pytest.mark.skipif(not BILINGUAL_PDF,
                    reason=f"the library does not hold {BILINGUAL}")
def test_no_page_loses_text_that_an_independent_reader_finds():
    """The rung-2 rule, over every page of the document: where `pdftotext` finds
    characters of a script and we find none, we are losing content.

    Thresholds are deliberately loose — 60% of the independent reader's count —
    because two readers differ honestly on ligatures, hyphenation and spacing.
    The failure this catches is not a few characters; it is a whole block, a
    whole column or a whole script going missing, which is what happened.
    """
    pdf = BILINGUAL_PDF
    losses = []
    for page in range(1, 22):
        theirs = _pdftotext_page(pdf, page)
        if not theirs.strip():
            continue
        ours = _our_page_text(pdf, page)
        for name, count in (("CJK", _cjk), ("latin", _latin)):
            t, o = count(theirs), count(ours)
            if t >= 10 and o < 0.6 * t:
                losses.append(f"p{page} {name}: pdftotext {t}, ours {o}")
    assert not losses, "pages losing text an independent reader finds:\n  " + \
                       "\n  ".join(losses)


@pytest.mark.skipif(not BILINGUAL_PDF,
                    reason=f"the library does not hold {BILINGUAL}")
def test_the_document_really_is_bilingual_so_the_case_is_what_it_claims():
    """The fixture's own premise, asserted rather than assumed. If this paper
    stopped being English-then-Chinese the tests above would still pass while
    measuring something else — the way a stale `.bbl` or a wrong page mapping
    makes a green check meaningless.
    """
    pdf = BILINGUAL_PDF
    first = _pdftotext_page(pdf, 1)
    middle = _pdftotext_page(pdf, 11)
    assert _latin(first) > 1000 and _cjk(first) > 0, "page 1 is English with CJK names"
    assert _cjk(middle) > 500, "page 11 is the Chinese half"
