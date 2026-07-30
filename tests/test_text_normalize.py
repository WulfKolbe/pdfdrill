"""
Private-use-area normalisation — the arXiv 1012.3259 (OpenOffice.org 3.2) case.

Its embedded OpenSymbol subset maps stretchy math delimiters into the PUA via
/ToUnicode, so the text layer extracts "correctly" yet carries font-private
codepoints into the model, llmtext and embeddings.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.text_normalize import (normalize_pua, pua_report, is_pua,
                                     OPENSYMBOL_PUA)


def test_verified_opensymbol_glyphs_become_plain_text():
    """The real string from the paper: the trig identity round-trips to ASCII."""
    raw = ("sinXsinA2"
           "=-½⋅cos2X")
    out, unmapped = normalize_pua(raw)
    assert out == "(sin(X)+sin(A))2=-½⋅cos(2X)"
    assert not unmapped
    # the delimiters are paired, which is what made the mapping verifiable
    assert out.count("(") == out.count(")")


def test_each_verified_codepoint():
    assert OPENSYMBOL_PUA[0xE09E] == "("
    assert OPENSYMBOL_PUA[0xE09F] == ")"
    assert OPENSYMBOL_PUA[0xE083] == "+"
    for cp, ch in OPENSYMBOL_PUA.items():
        assert normalize_pua(chr(cp))[0] == ch


def test_unknown_pua_is_kept_and_counted_never_guessed():
    """A font-private codepoint we have NOT verified must survive untouched —
    inventing a meaning is worse than reporting an unknown."""
    out, unmapped = normalize_pua("ab")
    assert out == "ab"                      # unchanged, not dropped
    assert unmapped == {0xE500: 1}
    rep = pua_report(unmapped)
    assert "U+E500" in rep and "1 unmapped" in rep


def test_ordinary_text_untouched():
    for s in ("", "plain ASCII", "Grüße — π ⋅ ½", "(sin(X)+sin(A))"):
        out, unmapped = normalize_pua(s)
        assert out == s and not unmapped


def test_is_pua_boundaries():
    assert is_pua("") and is_pua("")
    assert not is_pua("\uDFFF") and not is_pua("豈") and not is_pua("A")


def test_pua_report_empty_when_clean():
    assert pua_report(normalize_pua("clean")[1]) == ""


def test_chars_to_lines_normalizes_pua_at_the_seam():
    """The born-digital converter must emit clean line text — this is the single
    seam where a PDF's own text layer becomes a model line."""
    from pdfdrill import chars_to_lines
    def ch(t, x):                       # PDF coords: bottom-left origin
        return {"text": t, "x0": x, "x1": x + 5, "y0": 780, "y1": 790,
                "size": 10, "fontname": "F"}
    data = {"pages": [{"page_number": 1, "width": 600, "height": 800,
                       "chars": [ch("A", 0), ch("", 5), ch("t", 10),
                                 ch("", 15)]}]}
    out = chars_to_lines.chars_to_lines_json(data)
    text = " ".join(ln.get("text", "")
                    for p in out.get("pages", []) for ln in p.get("lines", []))
    assert "" not in text and "" not in text
    assert "A(t)" in text.replace(" ", "")
