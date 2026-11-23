"""T-0153 #3 — the maths-bearing flag, on the two gate pages.

`mathqc.is_math_bearing` answers one question: does this document carry
mathematics? `verdict.assess` asks it only when the model holds NO Formula and
NO Equation, so a wrong answer there is the difference between "REACHED" and
"DEGRADED - maths unread" on a document whose mathematics was never read.

MEASURED on the two board extracts (own copies under work/run-files):

  1805.01788-p0003        flag False   reading HAS `math` 12, `equation_number` 2
  lib_3c16fac66fdd-p0370  flag True    reading has NO math line at all

Both are defects, and NEITHER is the one the task description names.

(1) THE FONT REGISTRY MISSES THE WHOLE tx/newtx FAMILY. 1805.01788 p3 sets its
    mathematics in `rtxmi`, `rtxr`, `txsys`, `txexs`, `rtxmi7` and
    `ntxsyralt` -- newtxmath, one of the commonest math setups on arXiv -- and
    `_MATH_FONT_HINTS` knows cm, AMS, MathType, newpx, STIX, rsfs, mathpi and
    OpenSymbol but not tx. So `n_math` is 0 on a page carrying 225 math-font
    characters including the universal quantifier.

    This completes a REGISTRY OF FONT FAMILIES, which is a table of facts, not
    a tuned threshold: tx was missing data.

(2) THE FLAG NEVER LOOKS AT THE READING. Four signals, and every one of them
    is a property of the PDF (fonts, named destinations) or of a prior `md` or
    `geometry` pass. The glyph reader TYPES ITS LINES -- 1805.01788 p3's own
    `lines.json` carries `math` 12 and `equation_number` 2 -- and nothing
    asked. That is the strongest and most specific evidence available, and it
    is free: the file is already on disk.

    It is NOT circular with the verdict's own question. The verdict asks
    whether the OBJECT layer holds a Formula; this asks whether the LINE layer
    saw mathematics. A reading with `math` lines and no Formula object is
    exactly the mismatch worth reporting.

(3) AND THE TASK'S OWN EXAMPLE IS NOT A FALSE POSITIVE. The description calls
    lib:3c16fac66fdd p370 "a bibliography page whose bullets use a symbol
    font". It is not a bibliography page: its first third is displayed Dirac
    algebra with partial derivatives and Levi-Civita symbols, and
    `Literaturverzeichnis` begins two-thirds down. `MT2MIT` draws 142
    characters in 22 distinct shapes there, which is math italic, not bullets;
    the `!` glyphs that look like bullets are the arrows before each
    annotation. So flag=True is CORRECT, and the font signal is the only thing
    that catches what the reading did: 0 `math` lines on that page. Calling it
    a false positive and suppressing it would have hidden a reader defect.

These tests are HERMETIC on purpose -- font names are classified pure, and the
reading signal is driven from a lines.json written here. The board extracts
live outside this repo, so a test that needed them would SKIP silently on a
fresh clone, which is the failure mode that cost another project 2 of its 3
ratchet documents.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill.font_image_layers import _classify_font_family   # noqa: E402


# ------------------------------------------------- (1) the font registry
#: Every math font the two gate pages actually load, by its real name.
TX_MATH = ["rtxmi", "rtxmi7", "txsys", "txexs", "ntxsyralt",
           "txmi", "txsy", "txex", "ntxsy", "newtxmath"]
#: ...and the fonts that must NOT be called mathematical.
NOT_MATH = ["LinLibertineT", "LinLibertineTI", "LinBiolinumT", "Times-Roman",
            "Times-Italic", "MyriadPro-Regular", "Helvetica", "txr", "rtxr",
            "ptmr8t", "Arial", "Symbol", "ZapfDingbats"]


@pytest.mark.parametrize("name", TX_MATH)
def test_the_tx_math_fonts_are_in_the_registry(name):
    _base, is_math, _b, _i = _classify_font_family(f"ABCDEF+{name}")
    assert is_math, (
        f"{name} is a newtxmath/txfonts MATH font and the registry does not "
        f"know it -- 1805.01788 p3 sets its mathematics in these")


@pytest.mark.parametrize("name", NOT_MATH)
def test_a_text_font_is_not_called_mathematical(name):
    _base, is_math, _b, _i = _classify_font_family(f"ABCDEF+{name}")
    assert not is_math, (
        f"{name} is a TEXT font and the registry calls it mathematical")


def test_txr_is_excluded_on_purpose():
    r"""`txr` is the tx package's ROMAN text font. It also supplies `=` and `+`
    inside mathematics (39 characters of it on 1805.01788 p3), so it is
    tempting -- and it is the text face of every tx-set document, so a `txr`
    hint would call every such paper math-bearing whether or not it has a
    formula. The math-specific members (mi, sy, ex) carry the signal."""
    for n in ("txr", "rtxr", "txr8t"):
        _b, is_math, _x, _y = _classify_font_family(f"ABCDEF+{n}")
        assert not is_math, f"{n} would flag every tx-set text document"


# ------------------------------------------------ (2) the reading signal
def _pdf_with_lines(tmp_path: Path, types: list[str]) -> Path:
    """A document whose only evidence is its own reading."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    lines = {"source": "pdfminer-docmodel",
             "pages": [{"page": 1,
                        "lines": [{"type": t, "text": "x"} for t in types]}]}
    (tmp_path / "doc.lines.json").write_text(json.dumps(lines))
    return pdf


def test_a_reading_that_typed_math_lines_raises_the_flag(tmp_path):
    from pdfdrill import mathqc
    from pdfdrill.sidecar import Sidecar
    pdf = _pdf_with_lines(tmp_path, ["text"] * 20 + ["math"] * 12)
    flag, why = mathqc.is_math_bearing(pdf, Sidecar(pdf))
    assert flag is True, (
        "the reader typed 12 `math` lines and the flag said the document "
        "carries no mathematics")
    assert "math" in why.lower() and "read" in why.lower(), (
        f"the reason does not say the evidence came from the reading: {why!r}")


def test_an_equation_number_line_counts_too(tmp_path):
    """A right-margin equation number is a display's own tell, and the reader
    types it separately."""
    from pdfdrill import mathqc
    from pdfdrill.sidecar import Sidecar
    pdf = _pdf_with_lines(tmp_path, ["text"] * 20 + ["equation_number"])
    assert mathqc.is_math_bearing(pdf, Sidecar(pdf))[0] is True


def test_a_reading_with_no_math_lines_does_not_raise_it(tmp_path):
    """lib:3c16fac66fdd p370's shape: prose, list items, a header -- and no
    math line. The flag must not come from the reading here. (On the real page
    it is raised by the FONTS, which is correct, and that is the signal that
    catches the reader having missed the page's displayed algebra.)"""
    from pdfdrill import mathqc
    from pdfdrill.sidecar import Sidecar
    pdf = _pdf_with_lines(
        tmp_path, ["text"] * 95 + ["list_item"] * 3 + ["section_header"])
    flag, why = mathqc.is_math_bearing(pdf, Sidecar(pdf))
    assert flag is False, f"raised on a reading with no mathematics: {why!r}"


def test_a_missing_or_broken_reading_is_not_an_answer(tmp_path):
    """No lines.json, and a corrupt one, must both leave the flag to the other
    signals rather than raising or crashing."""
    from pdfdrill import mathqc
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    assert mathqc.is_math_bearing(pdf, Sidecar(pdf))[0] is False
    (tmp_path / "doc.lines.json").write_text("{not json")
    assert mathqc.is_math_bearing(pdf, Sidecar(pdf))[0] is False
