"""
Math-font detection (font_image_layers._classify_font_family). Sandbox test
finding: the Adobe "Symbol" font — ubiquitous in ordinary Word/Office docs for
bullets, arrows, ™, and stray Greek — was flagged is_math, so a non-math manual
(the Axe-Fx II Owner's Manual) false-positived the math-bearing gate. Symbol is
NOT a reliable math signal; the real MathType companion "MT Extra" is.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.font_image_layers import _classify_font_family as clf


def _is_math(name):
    return clf(name)[1]


def test_symbol_font_is_not_math():
    assert _is_math("Symbol") is False
    assert _is_math("ABCDEF+Symbol") is False
    assert _is_math("SymbolMT") is False


def test_real_tex_math_fonts_still_math():
    for n in ("CMSY10", "CMMI12", "CMEX10", "ABCDEF+MSBM10", "MSAM10",
              "EUFM10", "RSFS10", "STIXMath", "XYZ+NewPXMathItalic"):
        assert _is_math(n) is True, n


def test_mathtype_mt_extra_is_math():
    # MathType / Word Equation Editor companion font — a reliable math signal
    assert _is_math("MTExtra") is True
    assert _is_math("ABCDEF+MT-Extra") is True


def test_plain_text_fonts_not_math():
    for n in ("Arial", "TimesNewRoman", "Calibri", "Helvetica", "CourierNew"):
        assert _is_math(n) is False, n


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
