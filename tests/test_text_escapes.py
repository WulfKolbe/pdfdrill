r"""662 — text_spans, promoted out of tools/audit_glyph_sites.py:91-103.

Pins the promoted function's original contract (unchanged for the default
`TEXT_IN_MATH` macro list) and the one bug fixed while promoting it: an
escaped backslash immediately before a REAL opening brace was mistaken for
an escaped brace, because the original walker looked exactly one character
back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.text_escapes import CJK_TEXT_MACROS, TEXT_IN_MATH, text_spans


def test_finds_a_single_text_macro_argument():
    s = r"\text{hi}"
    assert text_spans(s) == [(6, 8)]
    assert s[6:8] == "hi"


def test_finds_multiple_macro_arguments_by_default_list():
    s = r"\text{hi} \mbox{bye}"
    assert text_spans(s) == [(6, 8), (16, 19)]


def test_operatorname_is_in_the_default_font_audit_list():
    """TEXT_IN_MATH answers a FONT question (which face renders this glyph)
    for tools/audit_glyph_sites.py -- \\operatorname really does set its
    argument in the main/roman font, so it stays in this list."""
    assert text_spans(r"\operatorname{f}") == [(14, 15)]


def test_operatorname_is_not_in_the_cjk_text_macro_list():
    """CJK_TEXT_MACROS answers a CONTENT question for report_tex.cjk_defect
    (is this prose or a math-alphabet selector) -- deliberately narrower."""
    assert text_spans(r"\operatorname{f}", CJK_TEXT_MACROS) == []


def test_escaped_brace_is_not_counted():
    r"""`\{` -- one backslash, then a brace: the brace is ESCAPED (a literal
    `{` character), not a group delimiter, so it must not affect depth."""
    # \text{a\{b} -- the \{ is a literal brace inside the argument; the
    # argument's REAL closing brace is the final `}`.
    s = r"\text{a\{b}"
    assert text_spans(s) == [(6, 10)]
    assert s[6:10] == r"a\{b"


def test_escaped_backslash_before_brace_is_not_an_escaped_brace():
    r"""662's escape-walker fix. `\text{a\\{b}}` -- the argument is `a`, an
    ESCAPED BACKSLASH (`\\`, two characters, prints one literal `\`), then a
    REAL unescaped opening brace, `b`, a real closing brace. The old walker
    tested only `s[j-1] != "\\"`: at the real opening brace, the previous
    character IS a backslash (the second half of the escaped pair), so it
    was wrongly read as escaped and never counted -- depth then went to 0
    one character early, at the FIRST `}` instead of the second, returning
    a span one character short (`(6, 11)` instead of `(6, 12)`).
    """
    s = r"\text{a\\{b}}"
    spans = text_spans(s)
    assert spans == [(6, 12)], spans
    assert s[6:12] == "a\\\\{b}"     # a, \, \, {, b, } -- fully balanced
    # Demonstrate the old, unfixed behaviour is actually different, so this
    # test would have caught the regression it fixes:
    old_end = _old_buggy_end(s, 6)
    assert old_end == 11
    assert old_end != spans[0][1]


def _old_buggy_end(s, i):
    """The ORIGINAL walker from tools/audit_glyph_sites.py, reproduced
    inline (not by calling production code -- the buggy version no longer
    exists) so this test documents what was wrong, not just what is right."""
    depth, j = 1, i
    while j < len(s) and depth:
        if s[j] == "{" and s[j - 1] != "\\":
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
        j += 1
    return j - 1


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
