"""An equation number wrapped in math delimiters must not become `(\\2.5\\)`.

MathPix emits the printed number sometimes bare — `(2.4)` — and sometimes
wrapped in inline-math delimiters — `\\((2.5)\\)`. 64 bare and 8 wrapped in one
thesis. The normaliser stripped paren CHARACTERS:

    re.sub(r"[()]", "", r"\\((2.5)\\)")   ->   "\\2.5\\"

and `eqnums` then re-wrapped that as `(\\2.5\\)`. Six of 61 equations carried a
corrupted number, and because the TiddlyWiki prose substitution keys on the
DISPLAY STRING, a corrupted number matches nothing — so four in-text equation
references were never transcluded and went to the translator as literal prose.

External drillcheck audit round 3, findings 1 and 3; both reproduced here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.modules.equation import normalize_equation_number as norm


def test_a_bare_number_is_unchanged():
    assert norm("(2.4)") == "2.4"
    assert norm("2.4") == "2.4"
    assert norm(" (12) ") == "12"


def test_inline_math_delimiters_are_removed_not_their_parens():
    assert norm(r"\((2.5)\)") == "2.5"
    assert norm(r"\(2.5\)") == "2.5"
    assert norm("$(2.6)$") == "2.6"
    assert norm("$2.6$") == "2.6"
    assert norm(r"\[(2.7)\]") == "2.7"


def test_a_lettered_or_sectioned_number_survives():
    for raw, want in ((r"\((A.3)\)", "A.3"), ("(3.14a)", "3.14a"),
                      (r"\((B12)\)", "B12"), ("(2.5')", "2.5'")):
        assert norm(raw) == want, raw


def test_nothing_becomes_empty_rather_than_a_stray_backslash():
    for raw in ("", "   ", None, r"\(\)", "()"):
        assert norm(raw) == "", repr(raw)


def test_a_number_never_keeps_a_backslash():
    """The single property that would have caught this: whatever the input
    wrapping, the result is a NUMBER, and a number has no backslash in it."""
    for raw in ("(2.4)", r"\((2.5)\)", "$(2.6)$", r"\[(2.7)\]", r"\(2.8\)"):
        assert "\\" not in norm(raw), raw


# --------------------------------------------------------------------------
# one number, one equation — two algorithms were handing out the same one
# --------------------------------------------------------------------------

class _Stream:
    def __init__(self, payload):
        self.payload = payload


def _page(items):
    """anchors + a stream, in MathPix shape: y-positioned lines on one page."""
    payload, anchors = {}, []
    for i, (typ, y, text) in enumerate(items):
        a = f"a{i}"
        payload[a] = {"type": typ, "text": text, "_page": 1,
                      "region": {"top_left_y": y, "height": 10}}
        anchors.append(a)
    return anchors, _Stream(payload)


def test_a_number_already_paired_is_not_served_again_by_the_fallback():
    """Page 8 of the thesis: 3 equations, 2 number lines. The geometric pass
    assigned both; the ±3 stream-window fallback had no shared bookkeeping and
    re-served (2.5) to the third — so two equations claimed it and the one
    after had none."""
    from docmodel.modules.equation import EquationProcessor as EP
    anchors, stream = _page([
        ("math", 100, "a=b"), ("equation_number", 105, "(2.4)"),
        ("math", 200, "c=d"), ("equation_number", 205, r"\((2.5)\)"),
        ("math", 300, "e=f"),                      # no number of its own
    ])
    ep = EP.__new__(EP)
    paired = ep._match_equation_numbers(anchors, stream)
    assert sorted(paired.values()) == ["2.4", "2.5"], paired

    used = set(paired.values())
    third = anchors.index("a4")
    assert EP._refnum_near(anchors, stream, third, used=used) == "", \
        "the fallback re-served a number the geometric pass had already used"


def test_the_fallback_still_serves_a_number_nobody_has_taken():
    from docmodel.modules.equation import EquationProcessor as EP
    anchors, stream = _page([("math", 100, "a=b"), ("equation_number", 105, "(9.9)")])
    assert EP._refnum_near(anchors, stream, 0, used=set()) == "9.9"


def test_the_fallback_normalises_delimiters_too():
    from docmodel.modules.equation import EquationProcessor as EP
    anchors, stream = _page([("math", 100, "a=b"), ("equation_number", 105, r"\((3.1)\)")])
    assert EP._refnum_near(anchors, stream, 0, used=set()) == "3.1"


# --------------------------------------------------------------------------
# eqnums re-derives the display string — it must not re-wrap corruption
# --------------------------------------------------------------------------

def test_eqnums_normalises_a_stale_corrupt_refnum():
    """`refnum` is written at model-build time and `eqnums` wraps it for
    display. A model built before the delimiter fix carries `\\2.5\\` in
    `refnum`, and blind wrapping reproduced `(\\2.5\\)` on every re-run — so the
    corruption survived the fix until the whole model was rebuilt, which on a
    translated document costs the translation."""
    from pdfdrill.eqnums import display_number
    assert display_number("\\2.5\\") == "(2.5)"
    assert display_number("2.5") == "(2.5)"
    assert display_number("(2.5)") == "(2.5)"
    assert display_number(r"\((2.5)\)") == "(2.5)"


def test_eqnums_display_is_empty_for_an_empty_refnum():
    from pdfdrill.eqnums import display_number
    for raw in ("", "   ", None):
        assert display_number(raw) == ""


def _dn(x):
    from pdfdrill.eqnums import display_number
    return display_number(x)


def test_a_display_number_never_contains_a_backslash():
    for raw in ("\\2.5\\", r"\((2.5)\)", "(2.5)", "2.5", "A.3"):
        assert "\\" not in _dn(raw), raw
