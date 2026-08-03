"""The born-digital chars route must TYPE math, not flatten it into prose.

pdfminer hands us a per-character font. Math in a born-digital PDF is set in a
math font (CM* for TeX, OpenSymbol for OpenOffice/LibreOffice, MSAM/MSBM, MT
Extra for Word), so the math is right there in the dump — visible, attributed,
and previously thrown away: the assembler emitted `type: "text"` for every line,
so FormulaProcessor/EquationProcessor saw no math to build and the model came
out with zero formulas on a paper full of them.

The engine cannot be the reason math disappears. tesseract genuinely cannot read
math (it reads glyphs), but pdfminer CAN — the font tells it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.chars_to_lines import chars_to_lines_json, is_math_font


def test_math_fonts_recognised_across_producers():
    assert is_math_font("GAAAAA+OpenSymbol")        # OpenOffice / LibreOffice
    assert is_math_font("CMMI10") and is_math_font("CMSY10")   # TeX
    assert is_math_font("MSBM10")                   # AMS
    assert is_math_font("MTExtra")                  # Word equation editor
    assert not is_math_font("TimesNewRomanPSMT")    # body text
    assert not is_math_font("Helvetica")


def _page(chars, w=612.0, h=792.0, n=1):
    return {"page_number": n, "chars": chars, "width": w, "height": h}


def _c(t, x0, font, y0=700.0):
    """One pdfplumber char (PDF bottom-left origin, as the real dump gives us)."""
    return {"text": t, "x0": x0, "x1": x0 + 6, "y0": y0, "y1": y0 + 10,
            "fontname": font, "size": 10}


def test_display_math_line_is_typed_math_not_text():
    """A line set entirely in a math font is a display equation."""
    chars = [_c(ch, 100 + 7 * i, "GAAAAA+OpenSymbol")
             for i, ch in enumerate("y=∑x⋅z−q")]
    out = chars_to_lines_json({"pages": [_page(chars)], "source": "pdfminer-chars"})
    types = [l.get("type") for p in out["pages"] for l in p["lines"]]
    assert "math" in types, f"display math typed as {types}"


def test_prose_line_stays_text():
    chars = [_c(ch, 100 + 7 * i, "TimesNewRomanPSMT")
             for i, ch in enumerate("This is ordinary prose")]
    out = chars_to_lines_json({"pages": [_page(chars)], "source": "pdfminer-chars"})
    types = [l.get("type") for p in out["pages"] for l in p["lines"]]
    assert types and set(types) == {"text"}, types


def test_mostly_prose_line_with_one_symbol_stays_text():
    """A ™ or a stray bullet must NOT turn a sentence into an equation."""
    chars = [_c(ch, 100 + 7 * i, "TimesNewRomanPSMT")
             for i, ch in enumerate("The result is significant")]
    chars.append(_c("•", 100 + 7 * 40, "GAAAAA+OpenSymbol"))
    out = chars_to_lines_json({"pages": [_page(chars)], "source": "pdfminer-chars"})
    types = [l.get("type") for p in out["pages"] for l in p["lines"]]
    assert "math" not in types, types


def test_openoffice_mixed_font_equation_is_typed_math():
    """OpenOffice/LibreOffice sets operators in OpenSymbol but VARIABLES in
    Times-Italic, so a real equation is only ~40% math-font. A math-font-only
    threshold reads every OOo formula as prose — the shape measured on the live
    document 1012.3259, whose two equations were being dropped entirely.
    """
    chars, x = [], 100.0
    for ch in "At":                                    # italic variables
        chars.append(_c(ch, x, "CAAAAA+TimesNewRomanPS-ItalicMT")); x += 7
    for ch in "=":                                     # OpenSymbol operator
        chars.append(_c(ch, x, "GAAAAA+OpenSymbol")); x += 7
    for ch in "An":
        chars.append(_c(ch, x, "CAAAAA+TimesNewRomanPS-ItalicMT")); x += 7
    for ch in "⋅−⋅/⋅":
        chars.append(_c(ch, x, "GAAAAA+OpenSymbol")); x += 7
    for ch in "tT":
        chars.append(_c(ch, x, "CAAAAA+TimesNewRomanPS-ItalicMT")); x += 7

    out = chars_to_lines_json({"pages": [_page(chars)], "source": "pdfminer-chars"})
    types = [l.get("type") for p in out["pages"] for l in p["lines"]]
    assert "math" in types, f"OpenOffice equation typed as {types}"


def test_typing_counts_are_not_leaked_into_the_output():
    """The per-line glyph counters are working state, not payload — a consumer
    diffing lines.json must not see them."""
    chars = [_c(ch, 100 + 7 * i, "TimesNewRomanPSMT")
             for i, ch in enumerate("ordinary prose here")]
    out = chars_to_lines_json({"pages": [_page(chars)], "source": "pdfminer-chars"})
    for p in out["pages"]:
        for l in p["lines"]:
            assert "math_chars" not in l and "n_chars" not in l
            assert "italic_chars" not in l
